#!/usr/bin/env python3
"""Package two compatible frozen actors as one pure dual-seat checkpoint."""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import datetime, timezone
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from alpha_holdem.environment import NUM_ACTIONS
from alpha_holdem.network_dual_seat import DualSeatAlphaHoldemNet
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_actor(checkpoint: dict) -> AlphaHoldemNet:
    state = checkpoint["model"]
    model = AlphaHoldemNet(
        num_actions=NUM_ACTIONS,
        norm_layer=str(checkpoint.get("norm_layer", "bn")),
        critic_contract=str(checkpoint.get("critic_contract", "critic_v1")),
        separate_preflop_head=bool(
            checkpoint.get("separate_preflop_head")
            or "preflop_policy_head.weight" in state
        ),
        preflop_adapter_hidden=int(
            state["preflop_policy_adapter.0.weight"].shape[0]
            if "preflop_policy_adapter.0.weight" in state
            else 0
        ),
        preflop_raw_adapter_hidden=int(
            state["preflop_raw_policy_adapter.0.weight"].shape[0]
            if "preflop_raw_policy_adapter.0.weight" in state
            else 0
        ),
        flop_adapter_hidden=int(
            state["flop_policy_adapter.0.weight"].shape[0]
            if "flop_policy_adapter.0.weight" in state
            else 0
        ),
        postflop_adapter_hidden=int(
            state["postflop_policy_adapter.0.weight"].shape[0]
            if "postflop_policy_adapter.0.weight" in state
            else 0
        ),
        position_adapter_hidden=int(
            state["position_policy_adapters.0.0.weight"].shape[0]
            if "position_policy_adapters.0.0.weight" in state
            else 0
        ),
    )
    extra_width = 3 if model.position_adapter_hidden > 0 else 2
    with torch.no_grad():
        model(
            torch.zeros(1, 6, 4, 13),
            torch.zeros(1, 25, 4, 5),
            torch.zeros(1, extra_width),
        )
    model.load_state_dict(state, strict=True)
    model.eval()
    return model


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sb-checkpoint", type=Path, required=True)
    parser.add_argument("--bb-checkpoint", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    sb_path = args.sb_checkpoint.resolve()
    bb_path = args.bb_checkpoint.resolve()
    out_path = args.out.resolve()
    if out_path.exists():
        raise FileExistsError(f"refusing to overwrite {out_path}")

    sb_checkpoint = torch.load(sb_path, map_location="cpu", weights_only=False)
    bb_checkpoint = torch.load(bb_path, map_location="cpu", weights_only=False)
    compatibility_keys = (
        "norm_layer",
        "critic_contract",
        "separate_preflop_head",
        "env_version",
        "obs_version",
        "action_space_version",
        "raise_action_mapping",
    )
    mismatches = {
        key: (sb_checkpoint.get(key), bb_checkpoint.get(key))
        for key in compatibility_keys
        if sb_checkpoint.get(key) != bb_checkpoint.get(key)
    }
    if mismatches:
        raise ValueError(f"incompatible seat checkpoints: {mismatches}")

    sb_model = build_actor(sb_checkpoint)
    bb_model = build_actor(bb_checkpoint)
    dual = DualSeatAlphaHoldemNet(sb_model=sb_model, bb_model=bb_model)
    dual.eval()
    payload = {
        "architecture": "dual_seat_v1",
        "model": dual.state_dict(),
        "num_actions": NUM_ACTIONS,
        "norm_layer": sb_checkpoint.get("norm_layer", "bn"),
        "critic_contract": sb_checkpoint.get("critic_contract", "critic_v1"),
        "separate_preflop_head": bool(
            sb_checkpoint.get("separate_preflop_head")
        ),
        "env_version": sb_checkpoint.get("env_version"),
        "obs_version": sb_checkpoint.get("obs_version", "v4"),
        "action_space_version": sb_checkpoint.get("action_space_version"),
        "raise_action_mapping": sb_checkpoint.get("raise_action_mapping"),
        "requires_position_feature": True,
        "pure_weight_policy": True,
        "evaluator_side_overrides": False,
        "sb_source_path": str(sb_path),
        "sb_source_sha256": sha256_path(sb_path),
        "bb_source_path": str(bb_path),
        "bb_source_sha256": sha256_path(bb_path),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    out_path.parent.mkdir(parents=True, exist_ok=False)
    torch.save(payload, out_path)
    print(f"saved={out_path}")
    print(f"sha256={sha256_path(out_path)}")


if __name__ == "__main__":
    main()
