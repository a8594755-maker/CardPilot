#!/usr/bin/env python3
"""Recompute cross-seed river-CFR stability at every saved solver dose."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_river_public_belief_cfr_feasibility import (
    compare_seed_strategies,
    sha256_path,
)


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def monotone(values: list[float], *, decreasing: bool) -> bool:
    pairs = zip(values, values[1:])
    return all(right < left if decreasing else right >= left for left, right in pairs)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)

    summary_path = args.run_dir / "summary.json"
    snapshots_path = args.run_dir / "solver_snapshots.jsonl"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if sha256_path(snapshots_path) != summary["snapshots_sha256"]:
        raise RuntimeError("solver snapshot hash differs from the completed summary")
    rows = load_jsonl(snapshots_path)
    iterations = sorted({int(row["iteration"]) for row in rows})
    state_count = int(summary["states"])
    seed_count = len(summary["solver_seeds"])
    curve = []
    for iteration in iterations:
        cohort = [row for row in rows if row["iteration"] == iteration]
        if len(cohort) != state_count * seed_count:
            raise RuntimeError(f"incomplete snapshot cohort at iteration {iteration}")
        by_state = [
            sorted(
                [row for row in cohort if row["state_index"] == state_index],
                key=lambda row: row["solver_seed"],
            )
            for state_index in range(state_count)
        ]
        comparisons = [compare_seed_strategies(state_rows) for state_rows in by_state]
        weights = [row["comparisons"] for row in comparisons]
        curve.append(
            {
                "iteration": iteration,
                "cells": len(cohort),
                "minimum_root_strategy_hands": min(
                    row["root_strategy_hands"] for row in cohort
                ),
                "mean_root_regret_proxy_bb": float(
                    np.mean([row["root_regret_proxy_bb"] for row in cohort])
                ),
                "pooled_cross_seed_mean_total_variation": float(
                    np.average(
                        [row["mean_total_variation"] for row in comparisons],
                        weights=weights,
                    )
                ),
                "pooled_cross_seed_greedy_agreement": float(
                    np.average(
                        [row["greedy_agreement"] for row in comparisons],
                        weights=weights,
                    )
                ),
                "state_comparisons": comparisons,
            }
        )

    regrets = [row["mean_root_regret_proxy_bb"] for row in curve]
    televisions = [
        row["pooled_cross_seed_mean_total_variation"] for row in curve
    ]
    agreements = [row["pooled_cross_seed_greedy_agreement"] for row in curve]
    matched_left, matched_right = curve[-2], curve[-1]
    dose_ratio = matched_right["iteration"] / matched_left["iteration"]
    tv_log_slope = math.log(
        matched_right["pooled_cross_seed_mean_total_variation"]
        / matched_left["pooled_cross_seed_mean_total_variation"]
    ) / math.log(dose_ratio)
    regret_log_slope = math.log(
        matched_right["mean_root_regret_proxy_bb"]
        / matched_left["mean_root_regret_proxy_bb"]
    ) / math.log(dose_ratio)
    projected_iteration = matched_right["iteration"] * 4
    projected_tv = matched_right[
        "pooled_cross_seed_mean_total_variation"
    ] * 4**tv_log_slope
    gates = {
        "raw_snapshot_hash_matches": True,
        "regret_decreases_at_both_geometric_steps": monotone(
            regrets, decreasing=True
        ),
        "cross_seed_tv_decreases_at_both_geometric_steps": monotone(
            televisions, decreasing=True
        ),
        "greedy_agreement_nondecreasing_at_both_geometric_steps": monotone(
            agreements, decreasing=False
        ),
        "matched_512_and_2048_full_root_coverage": (
            matched_left["minimum_root_strategy_hands"]
            == summary["range_hands_per_player"]
            == matched_right["minimum_root_strategy_hands"]
        ),
    }
    output = {
        "schema": "cardpilot.v6_river_public_belief_cfr_curve_audit.v1",
        "source_summary": str(summary_path.resolve()),
        "source_summary_sha256": sha256_path(summary_path),
        "snapshots_sha256": sha256_path(snapshots_path),
        "curve": curve,
        "matched_512_to_2048_tv_log_log_slope": tv_log_slope,
        "matched_512_to_2048_regret_log_log_slope": regret_log_slope,
        "naive_projected_iteration": projected_iteration,
        "naive_projected_cross_seed_tv": projected_tv,
        "gate_components": gates,
        "admit_deeper_convergence_control": all(gates.values()),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.output.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, sort_keys=True))


if __name__ == "__main__":
    main()
