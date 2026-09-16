"""Independent raw-evidence breadth audit for contextual three-arm evaluation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
import math
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_dual_contract_residual_training_smoke import sha256_path


def mean_ci95(values) -> dict:
    array = np.asarray(values, dtype=np.float64)
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array)) if len(array) > 1 else 0.0
    return {"units": len(array), "bb100": float(array.mean()) * 100.0, "ci95_half_bb100": half * 100.0}


def load_evaluation(path: Path, seed_index: int) -> list[dict]:
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            if "correct_minus_base_bb" in row:
                row["seed_index"] = seed_index
                rows.append(row)
    return rows


def deck_units(rows: list[dict]) -> list[dict]:
    grouped = {}
    for row in rows:
        key = (row["seed_index"], row["opponent_label"], row["pair_index"])
        grouped.setdefault(key, []).append(row)
    units = []
    for (seed, opponent, pair), selected in sorted(grouped.items()):
        if sorted(row["hero_seat"] for row in selected) != [0, 1]:
            raise ValueError(f"paired deck unit lacks both seats: {(seed, opponent, pair)}")
        if selected[0]["deck"] != selected[1]["deck"] or selected[0]["split"] != selected[1]["split"]:
            raise ValueError("paired deck evidence mismatch")
        units.append({
            "seed_index": seed, "opponent_label": opponent, "pair_index": pair,
            "split": selected[0]["split"],
            "correct_minus_base_bb": float(np.mean([row["correct_minus_base_bb"] for row in selected])),
            "correct_minus_wrong_bb": float(np.mean([row["correct_minus_wrong_bb"] for row in selected])),
        })
    return units


def metrics(rows: list[dict], key: str) -> dict:
    return mean_ci95([row[key] for row in rows])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, action="append", required=True)
    parser.add_argument("--expected-sha256", action="append", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if len(args.evidence) != len(args.expected_sha256) or len(args.evidence) < 2:
        parser.error("evidence and hash lists must match and contain at least two seeds")
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    started = time.time()
    rows = []
    evidence = []
    for index, path in enumerate(args.evidence):
        digest = sha256_path(path)
        if digest != args.expected_sha256[index]:
            raise ValueError(f"seed {index} evaluation SHA mismatch")
        selected = load_evaluation(path, index)
        rows.extend(selected)
        evidence.append({"seed_index": index, "path": str(path.resolve()), "sha256": digest, "arm_hand_rows": len(selected)})
    units = deck_units(rows)
    expected_units = len(args.evidence) * 9 * 64
    if len(units) != expected_units:
        raise ValueError(f"expected {expected_units} paired-deck units, got {len(units)}")
    keys = ("correct_minus_base_bb", "correct_minus_wrong_bb")
    pooled = {key: metrics(units, key) for key in keys}
    seeds = []
    for seed in sorted({row["seed_index"] for row in units}):
        selected = [row for row in units if row["seed_index"] == seed]
        seeds.append({"seed_index": seed, **{key: metrics(selected, key) for key in keys}})
    splits = {}
    for split in ("training", "holdout"):
        selected = [row for row in units if row["split"] == split]
        splits[split] = {key: metrics(selected, key) for key in keys}
    opponents = []
    for label in sorted({row["opponent_label"] for row in units}):
        selected = [row for row in units if row["opponent_label"] == label]
        opponents.append({"label": label, "split": selected[0]["split"], **{key: metrics(selected, key) for key in keys}})
    seats = {}
    for seat in (0, 1):
        selected = [row for row in rows if row["hero_seat"] == seat]
        seats[str(seat)] = {key: metrics(selected, key) for key in keys}
    holdout_opponents = [row for row in opponents if row["split"] == "holdout"]
    gates = {
        "evidence_hashes_exact": True,
        "paired_deck_units_exact": len(units) == expected_units,
        "both_seed_correct_minus_base_positive": all(row["correct_minus_base_bb"]["bb100"] > 0 for row in seeds),
        "pooled_correct_minus_base_positive": pooled["correct_minus_base_bb"]["bb100"] > 0,
        "both_seats_correct_minus_base_nonnegative": all(row["correct_minus_base_bb"]["bb100"] >= 0 for row in seats.values()),
        "holdout_correct_minus_base_nonnegative": splits["holdout"]["correct_minus_base_bb"]["bb100"] >= 0,
        "at_least_two_holdout_opponents_correct_minus_base_nonnegative": sum(row["correct_minus_base_bb"]["bb100"] >= 0 for row in holdout_opponents) >= 2,
        "training_and_holdout_correct_minus_wrong_nonnegative": all(splits[split]["correct_minus_wrong_bb"]["bb100"] >= 0 for split in ("training", "holdout")),
    }
    broad_admitted = all(gates.values())
    summary = {
        "schema": "cardpilot.contextual_breadth_audit.v1", "status": "COMPLETED",
        "claim_scope": "INTERNAL_BROAD_LEAGUE_BREADTH_NOT_SLUMBOT_STRENGTH", "new_environment_hands": 0,
        "evidence": evidence, "paired_deck_units": len(units), "pooled": pooled, "seeds": seeds,
        "splits": splits, "opponents": opponents, "seats": seats, "gates": gates,
        "broad_admitted": broad_admitted,
        "decision": "ADMIT_CONTEXTUAL_GEOMETRIC_SCALE" if broad_admitted else "HOLD_CONTEXTUAL_SCALE_FOR_OOD_SHRINKAGE",
        "wall_time_seconds": time.time() - started, "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
