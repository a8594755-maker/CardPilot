"""Independently audit raw frozen breadth evidence for online MGDA."""
from __future__ import annotations

import argparse
from collections import defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

import numpy as np


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def mean_ci95(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    return (
        float(array.mean()),
        1.96 * float(array.std(ddof=1)) / math.sqrt(len(array)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--eval-summary", type=Path, required=True)
    parser.add_argument("--drift-summary", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    summary = json.loads(args.eval_summary.read_text(encoding="utf-8"))
    drift = json.loads(args.drift_summary.read_text(encoding="utf-8"))
    raw_path = args.eval_summary.parent / "common_deck_pairs.jsonl.gz"
    drift_raw_path = args.drift_summary.parent / "drift_raw.jsonl.gz"
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]

    by_anchor: dict[str, list[dict]] = defaultdict(list)
    pair_deltas = []
    seat_deltas: dict[int, list[float]] = defaultdict(list)
    row_arithmetic = []
    for row in rows:
        by_anchor[str(row["anchor"])].append(row)
        control = [float(value) for value in row["control_rewards_bb"]]
        treatment = [float(value) for value in row["treatment_rewards_bb"]]
        differences = [right - left for left, right in zip(control, treatment)]
        delta = sum(differences) / 2.0
        pair_deltas.append(delta)
        for seat, value in enumerate(differences):
            seat_deltas[seat].append(value)
        row_arithmetic.append(
            np.allclose(differences, row["treatment_minus_control_rewards_bb"])
            and math.isclose(delta, float(row["treatment_minus_control_pair_mean_bb"]))
            and math.isclose(sum(control) / 2.0, float(row["control_pair_mean_bb"]))
            and math.isclose(sum(treatment) / 2.0, float(row["treatment_pair_mean_bb"]))
        )

    pooled_mean, pooled_half = mean_ci95(pair_deltas)
    reconstructed_anchors = {}
    anchor_summary_matches = []
    summary_by_anchor = {row["anchor"]: row for row in summary["anchors"]}
    for anchor, anchor_rows in sorted(by_anchor.items()):
        values = [float(row["treatment_minus_control_pair_mean_bb"]) for row in anchor_rows]
        mean, half = mean_ci95(values)
        reconstructed_anchors[anchor] = {
            "pairs": len(values),
            "delta_bb100": mean * 100.0,
            "ci95_half_bb100": half * 100.0,
        }
        recorded = summary_by_anchor[anchor]
        anchor_summary_matches.append(
            math.isclose(mean * 100.0, recorded["treatment_minus_control_bb100"])
            and math.isclose(half * 100.0, recorded["treatment_minus_control_ci95_bb100"])
        )
    reconstructed_seats = {}
    seat_summary_matches = []
    for seat, values in sorted(seat_deltas.items()):
        mean, half = mean_ci95(values)
        reconstructed_seats[f"seat{seat}"] = {
            "hands": len(values),
            "delta_bb100": mean * 100.0,
            "ci95_half_bb100": half * 100.0,
        }
        recorded = summary["pooled_seat_deltas"][seat]
        seat_summary_matches.append(
            math.isclose(mean * 100.0, recorded["delta_bb100"])
            and math.isclose(half * 100.0, recorded["delta_ci95_bb100"])
        )

    pairs_per_anchor = int(summary["pairs_per_anchor"])
    gates = {
        "raw_sha_exact": sha256_path(raw_path) == summary["raw_pairs_sha256"],
        "row_count_exact": len(rows)
        == pairs_per_anchor * int(summary["anchor_count"]),
        "anchor_set_exact": set(by_anchor) == set(summary_by_anchor),
        "pair_indices_complete": all(
            sorted(int(row["pair_index"]) for row in anchor_rows)
            == list(range(pairs_per_anchor))
            for anchor_rows in by_anchor.values()
        ),
        "decks_are_permutations": all(
            sorted(int(card) for card in row["deck"]) == list(range(52))
            for row in rows
        ),
        "decks_unique_within_anchor": all(
            len({tuple(row["deck"]) for row in anchor_rows}) == pairs_per_anchor
            for anchor_rows in by_anchor.values()
        ),
        "row_arithmetic_exact": all(row_arithmetic),
        "anchor_summaries_recomputed": all(anchor_summary_matches),
        "seat_summaries_recomputed": all(seat_summary_matches),
        "pooled_summary_recomputed": math.isclose(
            pooled_mean * 100.0, summary["pooled_treatment_minus_control_bb100"]
        ) and math.isclose(
            pooled_half * 100.0,
            summary["pooled_treatment_minus_control_ci95_bb100"],
        ),
        "evaluation_checkpoint_hashes_bound": all(
            len(value) == 64 for value in summary["input_sha256"].values()
        ),
        "drift_status_pass": drift["status"] == "PASS",
        "drift_raw_sha_exact": sha256_path(drift_raw_path) == drift["raw_sha256"],
        "drift_treatment_matches_eval": (
            drift["treatment"]["sha256"] == summary["input_sha256"]["treatment"]
        ),
    }
    if not all(gates.values()):
        raise RuntimeError(f"online MGDA breadth audit failed: {gates}")
    upper = (pooled_mean + pooled_half) * 100.0
    result = {
        "schema": "cardpilot.online_mgda_breadth_audit.v1",
        "gates": gates,
        "passed": all(gates.values()),
        "evaluation_hands": len(rows) * 4,
        "pairs": len(rows),
        "pooled_delta_bb100": pooled_mean * 100.0,
        "pooled_ci95_half_bb100": pooled_half * 100.0,
        "pooled_ci95_upper_bb100": upper,
        "anchors": reconstructed_anchors,
        "seats": reconstructed_seats,
        "standard10_preservation": drift["overall"],
        "strong_negative_translation": upper < 0.0,
        "decision": (
            "REJECT_UNIT_NORMALIZED_ONLINE_MGDA_DOSE"
            if upper < 0.0 else "HOLD_FOR_GEOMETRIC_REPLICATION"
        ),
        "hashes": {
            "eval_summary": sha256_path(args.eval_summary),
            "eval_raw": sha256_path(raw_path),
            "drift_summary": sha256_path(args.drift_summary),
            "drift_raw": sha256_path(drift_raw_path),
        },
        "command": [sys.executable, *sys.argv],
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
