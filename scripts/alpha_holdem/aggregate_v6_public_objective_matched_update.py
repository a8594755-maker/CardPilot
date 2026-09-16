"""Aggregate two-lineage seven-versus-nine untouched paired evaluations."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.audit_v6_integrated_gradient_conflict import (
    parse_named_path,
    sha256_path,
)
from alpha_holdem.v6_public_opponent_matched_policy_eval import mean_ci95


def read_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--learned", action="append", type=parse_named_path, required=True)
    parser.add_argument("--public", action="append", type=parse_named_path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    learned_dirs = dict(args.learned)
    public_dirs = dict(args.public)
    if set(learned_dirs) != set(public_dirs) or len(learned_dirs) < 2:
        parser.error("learned and public lineage names must match and number at least two")
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()

    input_hashes = {}
    learned_all = []
    learned_seats = [[], []]
    learned_by_anchor = defaultdict(list)
    learned_by_lineage = {}
    public_all = []
    public_seats = [[], []]
    public_by_lineage = {}
    integrity = {}
    total_evaluation_hands = 0
    for lineage in sorted(learned_dirs):
        learned_dir = learned_dirs[lineage].resolve()
        learned_summary_path = learned_dir / "summary.json"
        learned_raw_path = learned_dir / "common_deck_pairs.jsonl.gz"
        learned_summary = json.loads(learned_summary_path.read_text(encoding="utf-8"))
        input_hashes[str(learned_summary_path)] = sha256_path(learned_summary_path)
        input_hashes[str(learned_raw_path)] = sha256_path(learned_raw_path)
        integrity[f"{lineage}_learned_raw_hash"] = (
            sha256_path(learned_raw_path) == learned_summary["raw_pairs_sha256"]
        )
        learned_rows = read_rows(learned_raw_path)
        expected_learned_rows = (
            int(learned_summary["pairs_per_anchor"])
            * int(learned_summary["anchor_count"])
        )
        integrity[f"{lineage}_learned_row_count"] = (
            len(learned_rows) == expected_learned_rows
        )
        lineage_values = []
        for row in learned_rows:
            value = float(row["treatment_minus_control_pair_mean_bb"])
            lineage_values.append(value)
            learned_all.append(value)
            learned_by_anchor[str(row["anchor"])].append(value)
            for seat in (0, 1):
                learned_seats[seat].append(
                    float(row["treatment_minus_control_rewards_bb"][seat])
                )
        learned_by_lineage[lineage] = mean_ci95(lineage_values)
        total_evaluation_hands += int(learned_summary["evaluation_hands"])

        public_dir = public_dirs[lineage].resolve()
        public_summary_path = public_dir / "summary.json"
        public_raw_path = public_dir / "common_deck_pairs.jsonl.gz"
        public_summary = json.loads(public_summary_path.read_text(encoding="utf-8"))
        input_hashes[str(public_summary_path)] = sha256_path(public_summary_path)
        input_hashes[str(public_raw_path)] = sha256_path(public_raw_path)
        integrity[f"{lineage}_public_raw_hash"] = (
            sha256_path(public_raw_path) == public_summary["raw_pairs_sha256"]
        )
        public_rows = read_rows(public_raw_path)
        integrity[f"{lineage}_public_row_count"] = (
            len(public_rows) == int(public_summary["pairs"])
        )
        lineage_public_values = []
        for row in public_rows:
            value = float(row["treatment_minus_control_pair_mean_bb"])
            lineage_public_values.append(value)
            public_all.append(value)
            for seat in (0, 1):
                public_seats[seat].append(
                    float(row["treatment_rewards_bb"][seat])
                    - float(row["control_rewards_bb"][seat])
                )
        public_by_lineage[lineage] = mean_ci95(lineage_public_values)
        total_evaluation_hands += int(public_summary["evaluation_hands"])

    learned_aggregate = mean_ci95(learned_all)
    public_aggregate = mean_ci95(public_all)
    learned_anchor_stats = {
        name: mean_ci95(values) for name, values in sorted(learned_by_anchor.items())
    }
    learned_seat_stats = [mean_ci95(values) for values in learned_seats]
    public_seat_stats = [mean_ci95(values) for values in public_seats]
    gates = {
        "all_integrity_checks_pass": all(integrity.values()),
        "learned_panel_combined_delta_positive": learned_aggregate["bb100"] > 0.0,
        "learned_panel_both_seats_nonnegative": all(
            row["bb100"] >= 0.0 for row in learned_seat_stats
        ),
        "learned_panel_at_least_three_of_four_anchors_positive": (
            len(learned_anchor_stats) == 4
            and sum(row["bb100"] > 0.0 for row in learned_anchor_stats.values()) >= 3
        ),
        "public_combined_delta_positive": public_aggregate["bb100"] > 0.0,
        "public_positive_in_both_lineages": all(
            row["bb100"] > 0.0 for row in public_by_lineage.values()
        ),
    }
    result = {
        "schema": "cardpilot.public_objective_matched_update_aggregate.v1",
        "status": "COMPLETED",
        "lineages": sorted(learned_dirs),
        "evaluation_hands": total_evaluation_hands,
        "learned_panel": {
            "combined": learned_aggregate,
            "by_lineage": learned_by_lineage,
            "by_anchor": learned_anchor_stats,
            "by_seat": learned_seat_stats,
        },
        "public_opponent": {
            "combined": public_aggregate,
            "by_lineage": public_by_lineage,
            "by_seat": public_seat_stats,
        },
        "integrity": integrity,
        "gates": gates,
        "promote": all(gates.values()),
        "decision": (
            "PROMOTE_NINE_OBJECTIVE_UPDATE"
            if all(gates.values())
            else "REJECT_NINE_OBJECTIVE_UPDATE_PROMOTION"
        ),
        "input_sha256": input_hashes,
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
