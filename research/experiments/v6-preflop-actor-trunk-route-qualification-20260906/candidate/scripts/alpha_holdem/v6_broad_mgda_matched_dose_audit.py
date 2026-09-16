"""Read-only matched optimizer-dose audit for two broad-MGDA runs."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import time

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from alpha_holdem.v6_broad_league_domain_feasibility import sha256_path
from alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95


def _load_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle]


def align_evidence(half_rows: list[dict], full_rows: list[dict]) -> list[dict]:
    """Align half-dose chunk 8 with full-dose chunk 4 on untouched paired deals."""
    half = [row for row in half_rows if row["chunk_index"] == 8]
    full = [row for row in full_rows if row["chunk_index"] == 4]
    key_fields = ("seed_index", "holdout_label", "pair_index")

    def indexed(rows: list[dict], label: str) -> dict[tuple, dict]:
        result: dict[tuple, dict] = {}
        for row in rows:
            key = tuple(row[field] for field in key_fields)
            if key in result:
                raise ValueError(f"duplicate {label} evidence key: {key}")
            result[key] = row
        return result

    half_index = indexed(half, "half-dose")
    full_index = indexed(full, "full-dose")
    if set(half_index) != set(full_index):
        raise ValueError("matched evidence keys differ")
    aligned = []
    for key in sorted(half_index):
        half_row = half_index[key]
        full_row = full_index[key]
        for field in ("deck", "holdout_index", "holdout_sha256", "control_rewards_bb"):
            if half_row[field] != full_row[field]:
                raise ValueError(f"matched evidence {field} differs for {key}")
        aligned.append({
            "seed_index": half_row["seed_index"],
            "holdout_label": half_row["holdout_label"],
            "pair_index": half_row["pair_index"],
            "half_minus_full_bb": half_row["delta_bb"] - full_row["delta_bb"],
            "seat_half_minus_full_bb": [
                half_row["seat_delta_bb"][seat] - full_row["seat_delta_bb"][seat]
                for seat in (0, 1)
            ],
        })
    return aligned


def _estimate(values: list[float]) -> dict:
    mean, half = mean_ci95(values)
    return {
        "samples": len(values),
        "half_minus_full_bb100": mean * 100.0,
        "ci95_half_bb100": half * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def summarize_matches(rows: list[dict]) -> dict:
    seeds = []
    seed_holdouts = []
    seed_seats = []
    for seed in sorted({row["seed_index"] for row in rows}):
        seed_rows = [row for row in rows if row["seed_index"] == seed]
        seeds.append({"seed_index": seed, **_estimate([row["half_minus_full_bb"] for row in seed_rows])})
        for holdout in sorted({row["holdout_label"] for row in seed_rows}):
            selected = [row for row in seed_rows if row["holdout_label"] == holdout]
            seed_holdouts.append({
                "seed_index": seed,
                "holdout_label": holdout,
                **_estimate([row["half_minus_full_bb"] for row in selected]),
            })
        for seat in (0, 1):
            seed_seats.append({
                "seed_index": seed,
                "seat": seat,
                **_estimate([row["seat_half_minus_full_bb"][seat] for row in seed_rows]),
            })
    seed_values = [row["half_minus_full_bb100"] for row in seeds]
    gates = {
        "all_three_seed_point_estimates_nonnegative": all(value >= 0.0 for value in seed_values),
        "at_least_two_thirds_seed_holdout_partitions_nonnegative": sum(
            row["half_minus_full_bb100"] >= 0.0 for row in seed_holdouts
        ) >= int(np.ceil(len(seed_holdouts) * 2.0 / 3.0)),
        "at_least_two_thirds_seed_seat_partitions_nonnegative": sum(
            row["half_minus_full_bb100"] >= 0.0 for row in seed_seats
        ) >= int(np.ceil(len(seed_seats) * 2.0 / 3.0)),
    }
    return {
        "matched_pairs": len(rows),
        "seeds": seeds,
        "seed_holdouts": seed_holdouts,
        "seed_seats": seed_seats,
        "median_seed_half_minus_full_bb100": float(np.median(seed_values)),
        "positive_seed_point_estimates": sum(value > 0.0 for value in seed_values),
        "nonnegative_seed_holdout_partitions": sum(
            row["half_minus_full_bb100"] >= 0.0 for row in seed_holdouts
        ),
        "nonnegative_seed_seat_partitions": sum(
            row["half_minus_full_bb100"] >= 0.0 for row in seed_seats
        ),
        "uniform_improvement_gates": gates,
        "uniform_improvement": all(gates.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--half-run-dir", type=Path, required=True)
    parser.add_argument("--full-run-dir", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.out_dir.exists():
        raise FileExistsError(args.out_dir)
    args.out_dir.mkdir(parents=True)
    started = time.time()

    half_dir = args.half_run_dir.resolve()
    full_dir = args.full_run_dir.resolve()
    half_summary_path = half_dir / "summary.json"
    full_summary_path = full_dir / "summary.json"
    half_summary = json.loads(half_summary_path.read_text(encoding="utf-8"))
    full_summary = json.loads(full_summary_path.read_text(encoding="utf-8"))
    half_manifest = json.loads((half_dir / "run_manifest.json").read_text(encoding="utf-8"))
    full_manifest = json.loads((full_dir / "run_manifest.json").read_text(encoding="utf-8"))

    identity_checks = {
        "base_sha256_matches": half_summary["base_sha256"] == full_summary["base_sha256"],
        "spec_sha256_matches": half_summary["spec_sha256"] == full_summary["spec_sha256"],
        "training_policies_match": half_summary["training_policies"] == full_summary["training_policies"],
        "holdout_policies_match": half_summary["holdout_policies"] == full_summary["holdout_policies"],
        "seed_matches": half_manifest["seed"] == full_manifest["seed"],
        "seed_count_matches": half_manifest["seeds"] == full_manifest["seeds"] == 3,
        "pairs_per_holdout_matches": half_manifest["pairs_per_holdout"] == full_manifest["pairs_per_holdout"],
        "equal_optimizer_steps": half_manifest["steps_per_chunk"] * 8 == full_manifest["steps_per_chunk"] * 4 == 256,
        "half_endpoint_is_65536_hands": half_manifest["hands_per_chunk"] * 8 == 65536,
        "full_endpoint_is_32768_hands": full_manifest["hands_per_chunk"] * 4 == 32768,
    }
    if not all(identity_checks.values()):
        raise ValueError(f"source run identity mismatch: {identity_checks}")

    half_evidence = half_dir / "evaluation_pairs.jsonl.gz"
    full_evidence = full_dir / "evaluation_pairs.jsonl.gz"
    evidence_checks = {
        "half_evidence_hash_matches": sha256_path(half_evidence) == half_summary["evaluation_evidence_sha256"],
        "full_evidence_hash_matches": sha256_path(full_evidence) == full_summary["evaluation_evidence_sha256"],
    }
    if not all(evidence_checks.values()):
        raise ValueError(f"source evidence hash mismatch: {evidence_checks}")

    matched = align_evidence(_load_rows(half_evidence), _load_rows(full_evidence))
    comparison = summarize_matches(matched)
    expected_pairs = half_manifest["seeds"] * len(half_summary["holdout_policies"]) * half_manifest["pairs_per_holdout"]
    evidence_checks["matched_pair_count_exact"] = len(matched) == expected_pairs
    if not evidence_checks["matched_pair_count_exact"]:
        raise ValueError(f"expected {expected_pairs} matched pairs, found {len(matched)}")

    result = {
        "schema": "cardpilot.broad_mgda_matched_dose_audit.v1",
        "status": "COMPLETED",
        "half_run": str(half_dir),
        "full_run": str(full_dir),
        "half_summary_sha256": sha256_path(half_summary_path),
        "full_summary_sha256": sha256_path(full_summary_path),
        "half_evidence_sha256": sha256_path(half_evidence),
        "full_evidence_sha256": sha256_path(full_evidence),
        "identity_checks": identity_checks,
        "evidence_checks": evidence_checks,
        "comparison": comparison,
        "decision": (
            "MATCHED_DOSE_UNIFORMLY_IMPROVES_BUT_CURVE_GATE_REMAINS_CLOSED"
            if comparison["uniform_improvement"]
            else "MATCHED_DOSE_HETEROGENEOUS_CLOSE_BROAD_HALF_DOSE_RECIPE"
        ),
        "wall_time_seconds": time.time() - started,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "command": [sys.executable, *sys.argv],
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "matched_pairs": comparison["matched_pairs"],
        "seed_differences_bb100": [row["half_minus_full_bb100"] for row in comparison["seeds"]],
        "gates": comparison["uniform_improvement_gates"],
        "decision": result["decision"],
    }, sort_keys=True))


if __name__ == "__main__":
    main()
