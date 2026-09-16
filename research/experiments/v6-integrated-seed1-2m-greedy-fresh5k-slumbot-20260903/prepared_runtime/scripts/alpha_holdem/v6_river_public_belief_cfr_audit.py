#!/usr/bin/env python3
"""Hash-verify and recompute a completed river-belief CFR feasibility run."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(args.output)

    summary_path = args.run_dir / "summary.json"
    states_path = args.run_dir / "states.jsonl"
    snapshots_path = args.run_dir / "solver_snapshots.jsonl"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    states = load_jsonl(states_path)
    snapshots = load_jsonl(snapshots_path)
    if sha256_path(states_path) != summary["states_sha256"]:
        raise RuntimeError("states JSONL hash differs from completed summary")
    if sha256_path(snapshots_path) != summary["snapshots_sha256"]:
        raise RuntimeError("snapshot JSONL hash differs from completed summary")

    first_iteration = min(row["iteration"] for row in snapshots)
    final_iteration = max(row["iteration"] for row in snapshots)
    initial = [row for row in snapshots if row["iteration"] == first_iteration]
    final = [row for row in snapshots if row["iteration"] == final_iteration]
    state_count = int(summary["states"])
    seed_count = len(summary["solver_seeds"])
    expected_cells = state_count * seed_count
    if len(initial) != expected_cells or len(final) != expected_cells:
        raise RuntimeError("snapshot grid is incomplete")

    final_by_state = [
        sorted(
            [row for row in final if row["state_index"] == state_index],
            key=lambda row: row["solver_seed"],
        )
        for state_index in range(state_count)
    ]
    comparisons = [compare_seed_strategies(rows) for rows in final_by_state]
    weights = [row["comparisons"] for row in comparisons]
    pooled_tv = float(
        np.average([row["mean_total_variation"] for row in comparisons], weights=weights)
    )
    pooled_agreement = float(
        np.average([row["greedy_agreement"] for row in comparisons], weights=weights)
    )
    initial_regret = float(np.mean([row["root_regret_proxy_bb"] for row in initial]))
    final_regret = float(np.mean([row["root_regret_proxy_bb"] for row in final]))
    range_hands = int(summary["range_hands_per_player"])
    gates = {
        "checkpoint_unchanged_at_run_end": bool(
            summary["gate_components"]["checkpoint_unchanged"]
        ),
        "raw_artifact_hashes_match": True,
        "all_terminal_payoffs_zero_sum": all(
            row["zero_sum_failures"] == 0 for row in snapshots
        ),
        "no_illegal_action_probability": all(
            row["illegal_probability_events"] == 0 for row in snapshots
        ),
        "all_final_root_ranges_covered": all(
            row["root_strategy_hands"] == range_hands for row in final
        ),
        "mean_root_regret_proxy_decreased": final_regret < initial_regret,
        "pooled_cross_seed_mean_tv_at_most_0p10": pooled_tv <= 0.10,
        "pooled_cross_seed_greedy_agreement_at_least_0p80": (
            pooled_agreement >= 0.80
        ),
    }
    recomputed = {
        "schema": "cardpilot.v6_river_public_belief_cfr_audit.v1",
        "source_summary": str(summary_path.resolve()),
        "source_summary_sha256": sha256_path(summary_path),
        "states_sha256": sha256_path(states_path),
        "snapshots_sha256": sha256_path(snapshots_path),
        "states": len(states),
        "initial_iteration": first_iteration,
        "final_iteration": final_iteration,
        "initial_cells": len(initial),
        "final_cells": len(final),
        "minimum_final_root_strategy_hands": min(
            row["root_strategy_hands"] for row in final
        ),
        "mean_initial_root_regret_proxy_bb": initial_regret,
        "mean_final_root_regret_proxy_bb": final_regret,
        "root_regret_proxy_ratio": final_regret / initial_regret,
        "pooled_cross_seed_mean_total_variation": pooled_tv,
        "pooled_cross_seed_greedy_agreement": pooled_agreement,
        "state_comparisons": comparisons,
        "gate_components": gates,
        "admit_target_distillation": all(gates.values()),
        "original_coverage_gate": summary["gate_components"].get(
            "all_root_ranges_covered"
        ),
        "correction": (
            "The original coverage gate incorrectly required every geometric "
            "checkpoint to cover every root hand. The preregistered target "
            "stability gate is evaluated at the final 2048-iteration checkpoint."
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.output.write_text(
        json.dumps(recomputed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(recomputed, sort_keys=True))


if __name__ == "__main__":
    main()
