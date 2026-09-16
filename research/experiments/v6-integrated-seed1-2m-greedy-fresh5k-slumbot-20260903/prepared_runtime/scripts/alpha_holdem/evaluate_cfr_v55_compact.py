"""Evaluate a frozen AlphaHoldem adapter on compact CFR decision rows."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import torch

THIS_DIR = Path(__file__).resolve().parent
SCRIPTS_DIR = THIS_DIR.parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from alpha_holdem.distill_cfr_v55_compact import (
    _sha256,
    init_model,
    load_tensors,
    metrics_for_indices,
    precompute_frozen_features,
)


def resolve_paths(values: list[Path]) -> list[Path]:
    paths: list[Path] = []
    for value in values:
        paths.extend(sorted(value.glob("flop_*.jsonl")) if value.is_dir() else [value])
    resolved = sorted({path.resolve() for path in paths})
    missing = [str(path) for path in resolved if not path.is_file()]
    if missing:
        raise FileNotFoundError(f"missing compact inputs: {missing}")
    if not resolved:
        raise ValueError("no compact CFR inputs")
    return resolved


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--data", type=Path, nargs="+", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--batch-size", type=int, default=2048)
    parser.add_argument("--max-samples", type=int, default=0)
    parser.add_argument("--obs-version", choices=("auto", "v4", "v55"), default="auto")
    args = parser.parse_args()

    paths = resolve_paths(args.data)
    checkpoint = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    state = checkpoint["model"]
    adapter_hidden = (
        int(state["postflop_policy_adapter.0.weight"].shape[0])
        if "postflop_policy_adapter.0.weight" in state
        else 0
    )
    obs_version = (
        str(checkpoint.get("obs_version") or "v55").lower()
        if args.obs_version == "auto"
        else args.obs_version
    )
    tensors = load_tensors(paths, args.max_samples, obs_version)
    board_ids = sorted(int(value) for value in torch.unique(tensors[7]).tolist())
    model = init_model(checkpoint, adapter_hidden, args.device)
    features = precompute_frozen_features(
        model, tensors, args.batch_size, args.device
    )
    indices = torch.arange(len(features[0]))
    metrics = metrics_for_indices(
        model, features, indices, args.batch_size, args.device
    )
    report = {
        "schema": "cardpilot.cfr_compact_evaluation.v1",
        "checkpoint": str(args.checkpoint.resolve()),
        "checkpoint_sha256": _sha256(args.checkpoint),
        "data_files": [str(path) for path in paths],
        "board_ids": board_ids,
        "obs_version": obs_version,
        "metrics": metrics,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["metrics"], sort_keys=True))


if __name__ == "__main__":
    main()
