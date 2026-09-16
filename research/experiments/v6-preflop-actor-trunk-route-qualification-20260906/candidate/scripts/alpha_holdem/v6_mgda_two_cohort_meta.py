"""Combine independent matched MGDA cohorts from raw evaluation evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def describe(values: list[float]) -> dict[str, float | int]:
    mean = statistics.mean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {
        "pairs": len(values),
        "bb100": mean * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", action="append", type=Path, required=True)
    parser.add_argument("--summary", action="append", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if len(args.evidence) != 2 or len(args.summary) != 2:
        parser.error("exactly two evidence and two summary paths are required")
    if args.output.exists():
        raise FileExistsError(args.output)

    cohorts = []
    all_rows = []
    deck_sets: list[set[tuple[int, tuple[int, ...]]]] = []
    for evidence_path, summary_path in zip(args.evidence, args.summary):
        rows = [
            json.loads(line)
            for line in gzip.open(evidence_path, "rt", encoding="utf-8")
        ]
        source_summary = json.loads(summary_path.read_text(encoding="utf-8"))
        if len(rows) != 3072:
            raise ValueError(f"unexpected pair count in {evidence_path}: {len(rows)}")
        delta = [row["treatment_minus_control_pair_mean_bb"] for row in rows]
        cohorts.append(
            {
                "evidence": str(evidence_path.resolve()),
                "evidence_sha256": sha256_path(evidence_path),
                "summary": str(summary_path.resolve()),
                "summary_sha256": sha256_path(summary_path),
                "pooled": describe(delta),
                "robust_positive_worst_alignment_fraction": source_summary[
                    "robust_positive_worst_alignment_fraction"
                ],
                "policy_gate": source_summary[
                    "admit_independent_new_hand_replication"
                ],
            }
        )
        deck_sets.append(
            {(row["anchor_index"], tuple(row["deck"])) for row in rows}
        )
        all_rows.extend(rows)

    pooled = describe(
        [row["treatment_minus_control_pair_mean_bb"] for row in all_rows]
    )
    anchors = []
    for anchor in range(3):
        selected = [row for row in all_rows if row["anchor_index"] == anchor]
        anchors.append(
            {
                "anchor_index": anchor,
                **describe(
                    [row["treatment_minus_control_pair_mean_bb"] for row in selected]
                ),
            }
        )
    seats = []
    for seat in (0, 1):
        seats.append(
            {
                "seat": seat,
                **describe(
                    [
                        row["treatment_rewards_bb"][seat]
                        - row["control_rewards_bb"][seat]
                        for row in all_rows
                    ]
                ),
            }
        )
    overlap = len(deck_sets[0] & deck_sets[1])
    gates = {
        "two_independent_raw_cohorts": len(cohorts) == 2,
        "zero_anchor_deck_overlap": overlap == 0,
        "mechanism_positive_in_both_cohorts": all(
            row["robust_positive_worst_alignment_fraction"] >= 0.75
            for row in cohorts
        ),
        "at_least_one_cohort_passed_policy_gate": any(
            row["policy_gate"] for row in cohorts
        ),
        "combined_pooled_point_positive": pooled["bb100"] > 0,
        "all_combined_anchor_points_positive": all(
            row["bb100"] > 0 for row in anchors
        ),
        "both_combined_seat_points_positive": all(
            row["bb100"] > 0 for row in seats
        ),
    }
    admit = all(gates.values())
    result = {
        "schema": "cardpilot.mgda_two_cohort_meta.v1",
        "status": "COMPLETED",
        "cohorts": cohorts,
        "combined_pairs": len(all_rows),
        "combined_evaluation_hands": len(all_rows) * 4,
        "cross_cohort_anchor_deck_overlap": overlap,
        "pooled": pooled,
        "anchors": anchors,
        "seats": seats,
        "gates": gates,
        "admit_modest_new_hand_multi_seed_scale": admit,
        "decision": (
            "ADMIT_MODEST_NEW_HAND_MULTI_SEED_SCALE"
            if admit
            else "DO_NOT_SCALE_MGDA_YET"
        ),
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
