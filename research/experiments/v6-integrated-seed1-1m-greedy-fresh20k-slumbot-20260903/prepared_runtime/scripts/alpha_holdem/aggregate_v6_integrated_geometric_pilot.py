"""Recompute and aggregate multi-seed geometric-pilot evidence from raw rows."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics

import numpy as np


T95_DF2 = 4.302652729696142


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_gzip_jsonl(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mean_ci95(values: list[float]) -> tuple[float, float]:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array))
    return mean, half


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--promote-decision",
        default="SCALE_INTEGRATED_RECIPE_TO_262K_MULTI_SEED",
    )
    parser.add_argument(
        "--reject-decision",
        default="DO_NOT_SCALE_INTEGRATED_RECIPE",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    root = args.experiment_dir.resolve()
    training_audit_path = root / "training_audit.json"
    training_audit = load_json(training_audit_path)
    seed_rows = []
    all_pair_deltas: list[float] = []
    all_seat_deltas = [[], []]

    for seed in (1, 2, 3):
        eval_dir = root / f"eval_seed{seed}"
        summary_path = eval_dir / "summary.json"
        raw_path = eval_dir / "common_deck_pairs.jsonl.gz"
        drift_dir = root / f"drift_seed{seed}"
        drift_analysis_path = drift_dir / "drift_analysis.json"
        drift_raw_path = drift_dir / "drift_raw.jsonl.gz"
        summary = load_json(summary_path)
        raw = load_gzip_jsonl(raw_path)
        drift = load_json(drift_analysis_path)
        drift_raw = load_gzip_jsonl(drift_raw_path)

        anchor_counts = Counter(row["anchor"] for row in raw)
        pair_keys = [(row["anchor"], int(row["pair_index"])) for row in raw]
        deltas = [float(row["treatment_minus_control_pair_mean_bb"]) for row in raw]
        seat_deltas = [
            [float(row["treatment_minus_control_rewards_bb"][seat]) for row in raw]
            for seat in (0, 1)
        ]
        pooled_bb100 = statistics.fmean(deltas) * 100.0
        pooled_seats = [statistics.fmean(values) * 100.0 for values in seat_deltas]
        drift_tv = [float(row["tv"]) for row in drift_raw]
        drift_disagreement = [bool(row["greedy_disagreement"]) for row in drift_raw]
        raw_gates = {
            "eval_raw_sha_exact": sha256_path(raw_path) == summary["raw_pairs_sha256"],
            "eval_row_count_exact": len(raw) == 8192,
            "eval_anchor_counts_exact": set(anchor_counts.values()) == {2048}
            and len(anchor_counts) == 4,
            "eval_pair_keys_unique": len(pair_keys) == len(set(pair_keys)),
            "eval_pooled_delta_recomputed": math.isclose(
                pooled_bb100,
                float(summary["pooled_treatment_minus_control_bb100"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            "eval_seat_deltas_recomputed": all(
                math.isclose(
                    pooled_seats[seat],
                    float(summary["pooled_seat_deltas"][seat]["delta_bb100"]),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                for seat in (0, 1)
            ),
            "drift_raw_sha_exact": sha256_path(drift_raw_path) == drift["raw_sha256"],
            "drift_row_count_exact": len(drift_raw) == 20_000,
            "drift_rows_sequential": [int(row["row"]) for row in drift_raw]
            == list(range(20_000)),
            "drift_mean_tv_recomputed": math.isclose(
                statistics.fmean(drift_tv),
                float(drift["overall"]["mean_tv"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            "drift_disagreement_recomputed": math.isclose(
                statistics.fmean(drift_disagreement),
                float(drift["overall"]["greedy_disagreement_rate"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
        }
        all_pair_deltas.extend(deltas)
        for seat in (0, 1):
            all_seat_deltas[seat].extend(seat_deltas[seat])
        seed_rows.append(
            {
                "seed": seed,
                "pooled_slope_bb100": pooled_bb100,
                "pooled_slope_ci95_half_bb100": float(
                    summary["pooled_treatment_minus_control_ci95_bb100"]
                ),
                "positive_anchor_count": int(summary["positive_anchor_count"]),
                "pooled_seat_slopes_bb100": pooled_seats,
                "drift_mean_tv": statistics.fmean(drift_tv),
                "drift_greedy_disagreement": statistics.fmean(drift_disagreement),
                "summary_promote": bool(summary["promote"]),
                "drift_status": drift["status"],
                "raw_gates": raw_gates,
                "passed": all(raw_gates.values()),
                "artifacts": {
                    "summary": {"path": str(summary_path), "sha256": sha256_path(summary_path)},
                    "eval_raw": {"path": str(raw_path), "sha256": sha256_path(raw_path)},
                    "drift_analysis": {
                        "path": str(drift_analysis_path),
                        "sha256": sha256_path(drift_analysis_path),
                    },
                    "drift_raw": {
                        "path": str(drift_raw_path),
                        "sha256": sha256_path(drift_raw_path),
                    },
                },
            }
        )

    slopes = [row["pooled_slope_bb100"] for row in seed_rows]
    seed_mean = statistics.fmean(slopes)
    seed_sem = statistics.stdev(slopes) / math.sqrt(len(slopes))
    seed_t_half = T95_DF2 * seed_sem
    pair_mean, pair_half = mean_ci95(all_pair_deltas)
    pair_seats = []
    for seat in (0, 1):
        mean, half = mean_ci95(all_seat_deltas[seat])
        pair_seats.append({"seat": seat, "delta_bb100": mean * 100.0, "ci95_half_bb100": half * 100.0})
    gates = {
        "training_audit_passed": bool(training_audit["passed"]),
        "all_raw_evidence_recomputed": all(row["passed"] for row in seed_rows),
        "at_least_two_positive_seed_slopes": sum(value > 0 for value in slopes) >= 2,
        "median_seed_slope_positive": statistics.median(slopes) > 0,
        "at_least_two_seeds_three_of_four_positive_anchors": sum(
            row["positive_anchor_count"] >= 3 for row in seed_rows
        ) >= 2,
        "at_least_two_seeds_both_seats_nonnegative": sum(
            all(value >= 0 for value in row["pooled_seat_slopes_bb100"])
            for row in seed_rows
        ) >= 2,
        "all_source_preservation_gates_passed": all(
            row["drift_status"] == "PASS"
            and row["drift_mean_tv"] < 0.03
            and row["drift_greedy_disagreement"] < 0.05
            for row in seed_rows
        ),
    }
    output = {
        "schema": "cardpilot.integrated_alphaholdem_geometric_aggregate.v1",
        "training_audit": {
            "path": str(training_audit_path),
            "sha256": sha256_path(training_audit_path),
            "physical_environment_hands": training_audit["total_physical_environment_hands"],
        },
        "evaluation_hands": 98_304,
        "offline_drift_states": 60_000,
        "seed_results": seed_rows,
        "seed_slope_summary": {
            "values_bb100": slopes,
            "positive_count": sum(value > 0 for value in slopes),
            "mean_bb100": seed_mean,
            "median_bb100": statistics.median(slopes),
            "student_t95_low_bb100": seed_mean - seed_t_half,
            "student_t95_high_bb100": seed_mean + seed_t_half,
            "student_t_df": 2,
        },
        "all_pair_summary": {
            "pairs": len(all_pair_deltas),
            "delta_bb100": pair_mean * 100.0,
            "ci95_half_bb100": pair_half * 100.0,
            "seat_deltas": pair_seats,
        },
        "gates": gates,
        "promote": all(gates.values()),
        "decision": (
            args.promote_decision
            if all(gates.values())
            else args.reject_decision
        ),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not output["promote"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
