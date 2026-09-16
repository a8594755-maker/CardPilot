#!/usr/bin/env python3
"""Audit one immutable counterfactual replay dataset through the live loader."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.counterfactual_q_replay import load_counterfactual_q_replay


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--expected-rows", type=int, required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    replay = load_counterfactual_q_replay(
        args.dataset,
        expected_sha256=args.sha256,
        device="cpu",
        effective_stack_divisor=200.0,
        split_seed=20260824,
        validation_fraction=0.2,
        test_fraction=0.2,
        uncertainty_floor_bb=0.25,
        max_weight_ratio=20.0,
        target_mode="advantage_lcb",
        lcb_z=1.96,
        stratify_trajectory_opponent=True,
    )
    metadata = dict(replay["metadata"])
    coverage = metadata["position_street_coverage"]
    trajectory_coverage = metadata["position_street_trajectory_coverage"]
    errors: list[str] = []
    if metadata["total_rows"] != args.expected_rows:
        errors.append("total row count mismatch")
    if set(coverage) != {"bb_flop", "bb_turn", "sb_flop", "sb_turn"}:
        errors.append("position/street coverage mismatch")
    if metadata["trajectory_opponent_styles"] != [0, 1, 2, 3, 4]:
        errors.append("trajectory style coverage mismatch")
    if len(trajectory_coverage or {}) != 20:
        errors.append("expected 20 position/street/trajectory strata")
    for label, counts in (trajectory_coverage or {}).items():
        if min(counts["train"], counts["validation"], counts["test"]) <= 0:
            errors.append(f"empty split in {label}")
    if metadata["split_stratification"] != "position_street_trajectory":
        errors.append("trajectory stratification is not active")
    if metadata["uncertainty_target_basis"] != (
        "paired_action_minus_anchor_common_random_numbers"
    ):
        errors.append("paired common-random-number uncertainty is absent")
    target = metadata["target"]
    if target["mode"] != "advantage_lcb" or target["lcb_z"] != 1.96:
        errors.append("advantage LCB target contract mismatch")

    report = {
        "schema": "cardpilot.counterfactual_replay_dataset_audit.v1",
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "dataset": str(Path(args.dataset).resolve()),
        "metadata": metadata,
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
