"""Aggregate two-lineage matched evaluation of an integrated policy update."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    parse_named_path,
    sha256_path,
)


def mean_ci95(values) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array))
    return mean, half


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval", action="append", type=parse_named_path, required=True)
    parser.add_argument("--drift", action="append", type=parse_named_path, required=True)
    parser.add_argument("--update-summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    eval_paths = dict(args.eval)
    drift_paths = dict(args.drift)
    if set(eval_paths) != set(drift_paths) or len(eval_paths) != 2:
        parser.error("exactly two matching eval and drift lineage names are required")
    update = json.loads(args.update_summary.read_text(encoding="utf-8"))
    if not update["admit_untouched_evaluation"]:
        raise ValueError("update summary did not admit untouched evaluation")

    all_deltas = []
    by_anchor = defaultdict(list)
    by_seat = defaultdict(list)
    lineages = {}
    eval_seeds = set()
    raw_gates = []
    for lineage, summary_path in sorted(eval_paths.items()):
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        raw_path = summary_path.parent / "common_deck_pairs.jsonl.gz"
        raw_gates.append(
            sha256_path(raw_path) == summary["raw_pairs_sha256"]
        )
        expected = update["candidates"][lineage]["arms"]
        raw_gates.append(
            summary["input_sha256"]["control"]
            == expected["control"]["checkpoint"]["sha256"]
        )
        raw_gates.append(
            summary["input_sha256"]["treatment"]
            == expected["treatment"]["checkpoint"]["sha256"]
        )
        rows = 0
        lineage_deltas = []
        with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
            for line in handle:
                row = json.loads(line)
                rows += 1
                eval_seeds.add(int(row["anchor_seed"]))
                delta = float(row["treatment_minus_control_pair_mean_bb"])
                all_deltas.append(delta)
                lineage_deltas.append(delta)
                by_anchor[str(row["anchor"])].append(delta)
                for seat, value in enumerate(
                    row["treatment_minus_control_rewards_bb"]
                ):
                    by_seat[seat].append(float(value))
        raw_gates.append(rows == summary["pairs_per_anchor"] * summary["anchor_count"])
        mean, half = mean_ci95(lineage_deltas)
        lineages[lineage] = {
            "eval_summary": str(summary_path.resolve()),
            "eval_summary_sha256": sha256_path(summary_path),
            "raw_path": str(raw_path.resolve()),
            "raw_sha256": sha256_path(raw_path),
            "pairs": rows,
            "pooled_delta_bb100": mean * 100.0,
            "pooled_delta_ci95_bb100": half * 100.0,
            "gates": summary["gates"],
        }

    anchor_rows = {}
    for anchor, values in sorted(by_anchor.items()):
        mean, half = mean_ci95(values)
        anchor_rows[anchor] = {
            "pairs": len(values),
            "delta_bb100": mean * 100.0,
            "delta_ci95_bb100": half * 100.0,
        }
    seat_rows = {}
    for seat, values in sorted(by_seat.items()):
        mean, half = mean_ci95(values)
        seat_rows[f"seat{seat}"] = {
            "hands": len(values),
            "delta_bb100": mean * 100.0,
            "delta_ci95_bb100": half * 100.0,
        }
    pooled_mean, pooled_half = mean_ci95(all_deltas)

    drift_rows = {}
    for lineage, path in sorted(drift_paths.items()):
        drift = json.loads(path.read_text(encoding="utf-8"))
        expected_sha = update["candidates"][lineage]["arms"]["treatment"][
            "checkpoint"
        ]["sha256"]
        drift_rows[lineage] = {
            "path": str(path.resolve()),
            "sha256": sha256_path(path),
            "status": drift["status"],
            "treatment_sha256": drift["treatment"]["sha256"],
            "expected_treatment_sha256": expected_sha,
            "overall": drift["overall"],
            "raw_sha256": drift["raw_sha256"],
            "passed": drift["status"] == "PASS"
            and drift["treatment"]["sha256"] == expected_sha,
        }

    combined_breadth = {
        "pooled_delta_positive": pooled_mean > 0.0,
        "both_lineage_pooled_deltas_nonnegative": all(
            row["pooled_delta_bb100"] >= 0.0 for row in lineages.values()
        ),
        "at_least_three_of_four_combined_anchor_deltas_nonnegative": len(anchor_rows) == 4
        and sum(row["delta_bb100"] >= 0.0 for row in anchor_rows.values()) >= 3,
        "combined_standard10_delta_nonnegative": anchor_rows["standard10"][
            "delta_bb100"
        ]
        >= 0.0,
        "both_combined_seat_deltas_nonnegative": all(
            row["delta_bb100"] >= 0.0 for row in seat_rows.values()
        ),
    }
    gates = {
        "raw_evidence_and_checkpoint_hashes_exact": all(raw_gates),
        "independent_lineage_eval_seeds": len(eval_seeds) == 8,
        "both_treatment_standard10_drift_audits_pass": all(
            row["passed"] for row in drift_rows.values()
        ),
        **combined_breadth,
    }
    promote = all(gates.values())
    result = {
        "schema": "cardpilot.integrated_update_two_lineage_evaluation.v1",
        "status": "COMPLETED",
        "update_summary": str(args.update_summary.resolve()),
        "update_summary_sha256": sha256_path(args.update_summary),
        "lineages": lineages,
        "combined": {
            "pairs": len(all_deltas),
            "evaluation_hands": len(all_deltas) * 4,
            "pooled_delta_bb100": pooled_mean * 100.0,
            "pooled_delta_ci95_bb100": pooled_half * 100.0,
            "anchors": anchor_rows,
            "seats": seat_rows,
        },
        "drift": drift_rows,
        "gates": gates,
        "promote_to_on_policy_trainer_contract": promote,
        "decision": (
            "IMPLEMENT_MATCHED_ON_POLICY_SEVEN_OBJECTIVE_TRAINER_SMOKE"
            if promote
            else "HOLD_SEVEN_OBJECTIVE_EXTERNAL_TRANSLATION"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
