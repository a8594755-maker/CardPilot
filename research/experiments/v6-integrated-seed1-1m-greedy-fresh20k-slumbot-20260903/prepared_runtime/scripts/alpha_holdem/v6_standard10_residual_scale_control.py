"""Frozen residual-regret deployment-scale dose and disjoint confirmation."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import time

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.legacy_observation_bridge_v6 import load_policy
from alpha_holdem.v6_standard10_residual_regret_smoke import (
    EXPECTED_STANDARD10_SHA,
    _evaluate,
    _snapshot_networks,
)


EXPECTED_BUNDLE_SHA = "0748af53a24b4836079e6806e16420d4dd741c7c4f953410bd9af875348684be"
ANCHORS = ("standard10", "call_station", "uniform", "min_bet")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _panel(networks, policy, decks, scale, seed, raw_path):
    with gzip.open(raw_path, "wt", encoding="utf-8") as stream:
        cells = [
            _evaluate(
                networks, policy, decks, anchor, scale,
                seed + index * 100_000, stream,
            )
            for index, anchor in enumerate(ANCHORS)
        ]
    max_disagreement = max(cell["greedy_disagreement_from_base"] for cell in cells)
    positive = sum(cell["paired_delta_bb100"] > 0 for cell in cells)
    standard10 = cells[0]
    qualifies = (
        0.01 <= max_disagreement <= 0.25
        and standard10["paired_delta_bb100"] > 0
        and positive >= 3
    )
    return {
        "residual_scale": scale,
        "cells": cells,
        "positive_anchor_points": positive,
        "max_greedy_disagreement": max_disagreement,
        "mean_paired_delta_bb100": float(np.mean([
            cell["paired_delta_bb100"] for cell in cells
        ])),
        "qualifies": qualifies,
        "raw_path": str(raw_path),
        "raw_sha256": _sha256(raw_path),
    }


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    bundle_sha = _sha256(args.bundle)
    if bundle_sha != EXPECTED_BUNDLE_SHA:
        raise ValueError(f"residual bundle hash mismatch: {bundle_sha}")
    policy = load_policy(args.standard10, "cpu")
    if policy.sha256 != EXPECTED_STANDARD10_SHA:
        raise ValueError(f"Standard10 hash mismatch: {policy.sha256}")
    checkpoint = torch.load(args.bundle, map_location="cpu", weights_only=False)
    networks = _snapshot_networks([
        checkpoint["strategy_buffer_0"], checkpoint["strategy_buffer_1"]
    ])
    development_rng = np.random.default_rng(args.development_seed)
    confirmation_rng = np.random.default_rng(args.confirmation_seed)
    development_decks = [
        development_rng.permutation(52).tolist() for _ in range(args.development_pairs)
    ]
    confirmation_decks = [
        confirmation_rng.permutation(52).tolist() for _ in range(args.confirmation_pairs)
    ]
    deck_path = args.output_dir / "decks.json"
    deck_path.write_text(json.dumps({
        "development_seed": args.development_seed,
        "confirmation_seed": args.confirmation_seed,
        "development": development_decks,
        "confirmation": confirmation_decks,
    }) + "\n")
    development = []
    for index, scale in enumerate(args.scales):
        development.append(_panel(
            networks, policy, development_decks, scale,
            args.development_seed + 1_000_000 + index * 1_000_000,
            args.output_dir / f"development_scale_{scale:g}.jsonl.gz",
        ))
    qualified = [arm for arm in development if arm["qualifies"]]
    selected = min(qualified, key=lambda arm: arm["residual_scale"]) if qualified else None
    confirmation = None
    if selected is not None:
        confirmation = _panel(
            networks, policy, confirmation_decks, selected["residual_scale"],
            args.confirmation_seed + 9_000_000,
            args.output_dir / "confirmation.jsonl.gz",
        )
    dev_hands = len(args.scales) * args.development_pairs * 2 * len(ANCHORS) * 2
    confirmation_hands = (
        args.confirmation_pairs * 2 * len(ANCHORS) * 2 if confirmation else 0
    )
    gates = {
        "disjoint_deck_seeds": args.development_seed != args.confirmation_seed,
        "a_development_scale_qualified": selected is not None,
        "confirmation_preservation_band": bool(
            confirmation and 0.01 <= confirmation["max_greedy_disagreement"] <= 0.25
        ),
        "confirmation_standard10_point_positive": bool(
            confirmation and confirmation["cells"][0]["paired_delta_bb100"] > 0
        ),
        "confirmation_at_least_three_anchor_points_positive": bool(
            confirmation and confirmation["positive_anchor_points"] >= 3
        ),
    }
    result = {
        "schema_version": 1,
        "config": {
            "scales": args.scales,
            "development_pairs": args.development_pairs,
            "confirmation_pairs": args.confirmation_pairs,
            "development_seed": args.development_seed,
            "confirmation_seed": args.confirmation_seed,
        },
        "source": {
            "bundle": str(args.bundle),
            "bundle_sha256": bundle_sha,
            "standard10": str(args.standard10),
            "standard10_sha256": policy.sha256,
        },
        "accounting": {
            "environment_training_hands": 0,
            "evaluation_hands": dev_hands + confirmation_hands,
            "development_evaluation_hands": dev_hands,
            "confirmation_evaluation_hands": confirmation_hands,
        },
        "decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "development": development,
        "selected_scale": selected["residual_scale"] if selected else None,
        "confirmation": confirmation,
        "gates": gates,
        "elapsed_seconds": time.time() - started,
    }
    result["admit_selected_scale"] = all(gates.values())
    result["decision"] = (
        "ADMIT_PRESERVATION_COMPATIBLE_RESIDUAL_SCALE"
        if result["admit_selected_scale"]
        else "REJECT_FROZEN_RESIDUAL_SCALE_TRANSFER"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument(
        "--scales", type=float, nargs="+", default=[0.003, 0.01, 0.03, 0.1, 0.3, 1.0]
    )
    parser.add_argument("--development-pairs", type=int, default=256)
    parser.add_argument("--confirmation-pairs", type=int, default=1024)
    parser.add_argument("--development-seed", type=int, default=60912)
    parser.add_argument("--confirmation-seed", type=int, default=160912)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.scales != sorted(args.scales) or len(set(args.scales)) != len(args.scales):
        raise ValueError("scales must be unique and ascending")
    torch.set_num_threads(1)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
