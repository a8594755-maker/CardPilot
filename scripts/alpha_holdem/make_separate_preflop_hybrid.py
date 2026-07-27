#!/usr/bin/env python3
"""Build one checkpoint with a source postflop policy and a donor preflop head."""

from __future__ import annotations

import argparse
import copy
from pathlib import Path

import torch


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--preflop-donor", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    source_path = Path(args.source)
    donor_path = Path(args.preflop_donor)
    out_path = Path(args.out)
    if out_path.exists() and not args.overwrite:
        raise FileExistsError(out_path)

    source = torch.load(source_path, map_location="cpu", weights_only=False)
    donor = torch.load(donor_path, map_location="cpu", weights_only=False)
    source_state = source["model"]
    donor_state = donor["model"]
    for key in ("policy_head.weight", "policy_head.bias"):
        if key not in source_state or key not in donor_state:
            raise KeyError(f"required key missing: {key}")
        if source_state[key].shape != donor_state[key].shape:
            raise ValueError(
                f"shape mismatch for {key}: "
                f"source={tuple(source_state[key].shape)} "
                f"donor={tuple(donor_state[key].shape)}"
            )

    result = copy.deepcopy(source)
    result["model"]["preflop_policy_head.weight"] = (
        donor_state["policy_head.weight"].detach().clone()
    )
    result["model"]["preflop_policy_head.bias"] = (
        donor_state["policy_head.bias"].detach().clone()
    )
    result["separate_preflop_head"] = True
    result["config"] = dict(result.get("config") or {})
    result["config"]["separate_preflop_head"] = True
    result["preflop_head_source"] = {
        "checkpoint": str(donor_path.resolve()),
        "run_id": donor.get("run_id"),
        "iteration": donor.get("iteration"),
        "total_hands": donor.get("total_hands"),
        "keys": ["policy_head.weight", "policy_head.bias"],
    }
    result["postflop_policy_source"] = {
        "checkpoint": str(source_path.resolve()),
        "run_id": source.get("run_id"),
        "iteration": source.get("iteration"),
        "total_hands": source.get("total_hands"),
        "preserved_model_keys_except_preflop_head": True,
    }
    result["run_id"] = out_path.parent.name
    result["resume"] = str(source_path)
    result["lineage_parent_checkpoint"] = str(source_path)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    torch.save(result, out_path)
    print(out_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
