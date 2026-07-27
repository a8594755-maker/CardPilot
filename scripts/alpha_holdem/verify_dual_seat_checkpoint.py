#!/usr/bin/env python3
"""Independently verify a packaged dual-seat checkpoint and exact routing."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alpha_holdem.build_dual_seat_checkpoint import build_actor
from alpha_holdem.network_dual_seat import DualSeatAlphaHoldemNet


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dual-checkpoint", type=Path, required=True)
    parser.add_argument("--sb-checkpoint", type=Path, required=True)
    parser.add_argument("--bb-checkpoint", type=Path, required=True)
    parser.add_argument("--rows", type=int, default=1024)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--seed", type=int, default=20260727)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    if args.rows <= 0 or args.batch_size <= 0:
        raise ValueError("rows and batch-size must be positive")

    dual_path = args.dual_checkpoint.resolve()
    sb_path = args.sb_checkpoint.resolve()
    bb_path = args.bb_checkpoint.resolve()
    dual_checkpoint = torch.load(
        dual_path, map_location="cpu", weights_only=False
    )
    sb_checkpoint = torch.load(sb_path, map_location="cpu", weights_only=False)
    bb_checkpoint = torch.load(bb_path, map_location="cpu", weights_only=False)
    if dual_checkpoint.get("architecture") != "dual_seat_v1":
        raise ValueError("checkpoint is not dual_seat_v1")

    sb_model = build_actor(sb_checkpoint)
    bb_model = build_actor(bb_checkpoint)
    dual_model = DualSeatAlphaHoldemNet(
        sb_model=build_actor(sb_checkpoint),
        bb_model=build_actor(bb_checkpoint),
    )
    dual_model.load_state_dict(dual_checkpoint["model"], strict=True)
    dual_model.eval()

    expected_keys = {
        **{f"sb_model.{key}": value for key, value in sb_checkpoint["model"].items()},
        **{f"bb_model.{key}": value for key, value in bb_checkpoint["model"].items()},
    }
    observed_state = dual_checkpoint["model"]
    keyset_exact = set(expected_keys) == set(observed_state)
    unequal_tensors = [
        key
        for key in sorted(set(expected_keys) & set(observed_state))
        if not torch.equal(expected_keys[key], observed_state[key])
    ]

    generator = torch.Generator().manual_seed(args.seed)
    checked = 0
    logits_exact = True
    values_exact = True
    while checked < args.rows:
        size = min(args.batch_size, args.rows - checked)
        cards = torch.randn(size, 6, 4, 13, generator=generator)
        actions = torch.randn(size, 25, 4, 5, generator=generator)
        base_extra = torch.rand(size, 2, generator=generator)
        seats = torch.randint(0, 2, (size,), generator=generator)
        extra = torch.cat([base_extra, seats.float().unsqueeze(1)], dim=1)
        legal = torch.ones(size, 9)
        with torch.no_grad():
            dual_logits, dual_values = dual_model(
                cards, actions, extra, legal
            )
            sb_logits, sb_values = sb_model(
                cards, actions, base_extra, legal
            )
            bb_logits, bb_values = bb_model(
                cards, actions, base_extra, legal
            )
        expected_logits = torch.where(
            seats.bool().unsqueeze(1), sb_logits, bb_logits
        )
        expected_values = torch.where(
            seats.bool().unsqueeze(1), sb_values, bb_values
        )
        logits_exact &= torch.equal(dual_logits, expected_logits)
        values_exact &= torch.equal(dual_values, expected_values)
        checked += size

    source_sha_match = (
        dual_checkpoint.get("sb_source_sha256") == sha256_path(sb_path)
        and dual_checkpoint.get("bb_source_sha256") == sha256_path(bb_path)
    )
    passed = bool(
        keyset_exact
        and not unequal_tensors
        and logits_exact
        and values_exact
        and source_sha_match
        and dual_checkpoint.get("pure_weight_policy") is True
        and dual_checkpoint.get("evaluator_side_overrides") is False
    )
    report = {
        "schema": "cardpilot.dual_seat_checkpoint_verification.v1",
        "passed": passed,
        "dual_checkpoint": str(dual_path),
        "dual_checkpoint_sha256": sha256_path(dual_path),
        "sb_checkpoint_sha256": sha256_path(sb_path),
        "bb_checkpoint_sha256": sha256_path(bb_path),
        "source_sha_match": source_sha_match,
        "expected_tensor_count": len(expected_keys),
        "observed_tensor_count": len(observed_state),
        "keyset_exact": keyset_exact,
        "unequal_tensors": unequal_tensors,
        "random_forward_rows": checked,
        "random_forward_seed": args.seed,
        "logits_bitwise_exact": logits_exact,
        "values_bitwise_exact": values_exact,
        "pure_weight_policy": dual_checkpoint.get("pure_weight_policy"),
        "evaluator_side_overrides": dual_checkpoint.get(
            "evaluator_side_overrides"
        ),
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
