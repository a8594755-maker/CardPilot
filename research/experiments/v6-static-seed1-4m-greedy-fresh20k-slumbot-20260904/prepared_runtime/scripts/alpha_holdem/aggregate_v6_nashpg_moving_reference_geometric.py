#!/usr/bin/env python3
"""Audit and aggregate the preregistered moving-reference geometric pilot."""
from __future__ import annotations

import argparse
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys
import time

import numpy as np


COMPARISONS = ("static_slope", "moving_slope", "early_delta", "final_delta")
ANCHORS = ("standard10", "cfr4", "legacy_iter16", "legacy_mixed65k")
EXPECTED_EVAL_SEEDS = {1: 20263011, 2: 20263012, 3: 20263013}
EXPECTED_DRIFT_SEEDS = {
    (1, "static"): 20263031,
    (1, "moving"): 20263032,
    (2, "static"): 20263033,
    (2, "moving"): 20263034,
    (3, "static"): 20263035,
    (3, "moving"): 20263036,
}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def read_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mean_ci95_bb100(values_bb: list[float]) -> dict:
    values = np.asarray(values_bb, dtype=np.float64)
    mean = float(values.mean()) if len(values) else 0.0
    std = float(values.std(ddof=1)) if len(values) > 1 else 0.0
    half = 1.96 * std / math.sqrt(max(len(values), 1))
    return {
        "bb100": mean * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
        "ci95_halfwidth_bb100": half * 100.0,
        "samples": int(len(values)),
    }


def row_key(row: dict) -> tuple[str, int]:
    return str(row["anchor"]), int(row["pair_index"])


def command_value(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return str(command[index + 1])


def summarize_rows(rows: list[dict]) -> dict:
    pooled = [float(row["treatment_minus_control_pair_mean_bb"]) for row in rows]
    by_anchor: dict[str, list[float]] = defaultdict(list)
    by_seat = [[], []]
    for row in rows:
        by_anchor[str(row["anchor"])].append(
            float(row["treatment_minus_control_pair_mean_bb"])
        )
        for seat in (0, 1):
            by_seat[seat].append(
                float(row["treatment_minus_control_rewards_bb"][seat])
            )
    return {
        "pooled": mean_ci95_bb100(pooled),
        "by_anchor": {
            name: mean_ci95_bb100(by_anchor[name]) for name in sorted(by_anchor)
        },
        "by_seat": {
            str(seat): mean_ci95_bb100(by_seat[seat]) for seat in (0, 1)
        },
        "positive_anchor_count": sum(
            mean_ci95_bb100(values)["bb100"] > 0.0
            for values in by_anchor.values()
        ),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    root = args.experiment_dir.resolve()

    integrity: dict[str, bool] = {}
    input_sha256: dict[str, str] = {}
    training_audit_path = root / "training_audit.json"
    training_audit = read_json(training_audit_path)
    input_sha256[str(training_audit_path)] = sha256_path(training_audit_path)
    integrity["training_audit_passed"] = (
        training_audit.get("passed") is True
        and int(training_audit.get("passed_runs", -1)) == 6
        and int(training_audit.get("total_physical_environment_hands", -1)) == 407507
    )
    summaries: dict[tuple[int, str], dict] = {}
    rows_by_run: dict[tuple[int, str], list[dict]] = {}
    row_maps: dict[tuple[int, str], dict[tuple[str, int], dict]] = {}
    comparison_rows: dict[str, list[dict]] = defaultdict(list)
    comparison_by_seed: dict[str, dict[str, dict]] = defaultdict(dict)
    total_evaluation_hands = 0

    for seed in range(1, 4):
        for comparison in COMPARISONS:
            directory = root / f"eval_seed{seed}_{comparison}"
            summary_path = directory / "summary.json"
            raw_path = directory / "common_deck_pairs.jsonl.gz"
            summary = read_json(summary_path)
            rows = read_rows(raw_path)
            key = (seed, comparison)
            summaries[key] = summary
            rows_by_run[key] = rows
            row_maps[key] = {row_key(row): row for row in rows}
            comparison_rows[comparison].extend(rows)
            comparison_by_seed[comparison][str(seed)] = summarize_rows(rows)
            input_sha256[str(summary_path)] = sha256_path(summary_path)
            input_sha256[str(raw_path)] = sha256_path(raw_path)
            integrity[f"seed{seed}_{comparison}_status"] = (
                summary.get("status") == "COMPLETED"
            )
            integrity[f"seed{seed}_{comparison}_raw_hash"] = (
                sha256_path(raw_path) == summary.get("raw_pairs_sha256")
            )
            integrity[f"seed{seed}_{comparison}_row_count"] = (
                len(rows) == 2048 * len(ANCHORS)
                and len(row_maps[key]) == len(rows)
            )
            integrity[f"seed{seed}_{comparison}_accounting"] = (
                int(summary.get("evaluation_hands", -1)) == 32768
                and int(summary.get("pairs_per_anchor", -1)) == 2048
                and int(summary.get("anchor_count", -1)) == len(ANCHORS)
            )
            integrity[f"seed{seed}_{comparison}_anchors"] = (
                tuple(row["anchor"] for row in summary.get("anchors", [])) == ANCHORS
            )
            total_evaluation_hands += int(summary["evaluation_hands"])

        base = summaries[(seed, "static_slope")]
        expected_seed = EXPECTED_EVAL_SEEDS[seed]
        integrity[f"seed{seed}_matched_base_seed"] = all(
            int(command_value(summaries[(seed, comparison)]["command"], "--seed"))
            == expected_seed
            for comparison in COMPARISONS
        )
        integrity[f"seed{seed}_matched_anchor_hashes"] = all(
            summaries[(seed, comparison)]["input_sha256"][f"anchor:{anchor}"]
            == base["input_sha256"][f"anchor:{anchor}"]
            for comparison in COMPARISONS
            for anchor in ANCHORS
        )
        hashes = {name: summaries[(seed, name)]["input_sha256"] for name in COMPARISONS}
        integrity[f"seed{seed}_checkpoint_relation"] = (
            hashes["static_slope"]["control"] == hashes["early_delta"]["control"]
            and hashes["static_slope"]["treatment"]
            == hashes["final_delta"]["control"]
            and hashes["moving_slope"]["control"]
            == hashes["early_delta"]["treatment"]
            and hashes["moving_slope"]["treatment"]
            == hashes["final_delta"]["treatment"]
        )
        keys = set(row_maps[(seed, "static_slope")])
        integrity[f"seed{seed}_matched_row_keys"] = all(
            set(row_maps[(seed, comparison)]) == keys for comparison in COMPARISONS
        )
        max_pair_error = 0.0
        max_seat_error = 0.0
        decks_match = True
        for key in keys:
            quartet = {
                comparison: row_maps[(seed, comparison)][key]
                for comparison in COMPARISONS
            }
            decks_match &= all(
                quartet[comparison]["deck"] == quartet["static_slope"]["deck"]
                and int(quartet[comparison]["anchor_seed"])
                == int(quartet["static_slope"]["anchor_seed"])
                for comparison in COMPARISONS
            )
            algebra = (
                float(quartet["final_delta"]["treatment_minus_control_pair_mean_bb"])
                - float(quartet["early_delta"]["treatment_minus_control_pair_mean_bb"])
                - float(quartet["moving_slope"]["treatment_minus_control_pair_mean_bb"])
                + float(quartet["static_slope"]["treatment_minus_control_pair_mean_bb"])
            )
            max_pair_error = max(max_pair_error, abs(algebra))
            for seat in (0, 1):
                seat_algebra = (
                    float(quartet["final_delta"]["treatment_minus_control_rewards_bb"][seat])
                    - float(quartet["early_delta"]["treatment_minus_control_rewards_bb"][seat])
                    - float(quartet["moving_slope"]["treatment_minus_control_rewards_bb"][seat])
                    + float(quartet["static_slope"]["treatment_minus_control_rewards_bb"][seat])
                )
                max_seat_error = max(max_seat_error, abs(seat_algebra))
        integrity[f"seed{seed}_matched_decks"] = decks_match
        integrity[f"seed{seed}_pair_algebra"] = max_pair_error < 1e-10
        integrity[f"seed{seed}_seat_algebra"] = max_seat_error < 1e-10

    first_deck_fingerprints = []
    for seed in range(1, 4):
        first = rows_by_run[(seed, "static_slope")][0]["deck"]
        first_deck_fingerprints.append(
            hashlib.sha256(json.dumps(first, separators=(",", ":")).encode()).hexdigest()
        )
    integrity["cross_seed_eval_seeds_unique"] = len(set(EXPECTED_EVAL_SEEDS.values())) == 3
    integrity["cross_seed_first_decks_unique"] = len(set(first_deck_fingerprints)) == 3

    aggregate = {
        comparison: {
            "combined": summarize_rows(comparison_rows[comparison]),
            "by_seed": comparison_by_seed[comparison],
        }
        for comparison in COMPARISONS
    }

    drift: dict[str, dict] = {}
    drift_integrity: dict[str, bool] = {}
    for seed in range(1, 4):
        for arm in ("static", "moving"):
            name = f"{arm}_seed{seed}"
            directory = root / f"drift_{name}"
            analysis_path = directory / "drift_analysis.json"
            raw_path = directory / "drift_raw.jsonl.gz"
            analysis = read_json(analysis_path)
            drift[name] = {
                "mean_tv": float(analysis["overall"]["mean_tv"]),
                "greedy_disagreement_rate": float(
                    analysis["overall"]["greedy_disagreement_rate"]
                ),
                "changed_parameter_scope": analysis["tensor_scope"]["status"],
                "metadata_mismatch_count": len(
                    analysis["checkpoint_metadata_mismatches"]
                ),
                "states": int(analysis["overall"]["states"]),
                "analysis_sha256": sha256_path(analysis_path),
                "raw_sha256": sha256_path(raw_path),
            }
            input_sha256[str(analysis_path)] = sha256_path(analysis_path)
            input_sha256[str(raw_path)] = sha256_path(raw_path)
            expected_seed = EXPECTED_DRIFT_SEEDS[(seed, arm)]
            drift_integrity[f"{name}_contract"] = (
                int(analysis["design"]["states"]) == 20000
                and int(analysis["design"]["seed"]) == expected_seed
                and analysis["tensor_scope"]["status"] == "PASS"
                and not analysis["checkpoint_metadata_mismatches"]
            )
            drift_integrity[f"{name}_raw_hash"] = (
                sha256_path(raw_path) == analysis["raw_sha256"]
            )

    moving_slopes = [
        comparison_by_seed["moving_slope"][str(seed)]["pooled"]["bb100"]
        for seed in range(1, 4)
    ]
    final_deltas = [
        comparison_by_seed["final_delta"][str(seed)]["pooled"]["bb100"]
        for seed in range(1, 4)
    ]

    def collapse_seed(seed: int, comparison: str) -> bool:
        stats = comparison_by_seed[comparison][str(seed)]
        both_seats_negative = all(
            stats["by_seat"][str(seat)]["bb100"] < 0.0 for seat in (0, 1)
        )
        broad_anchor_reversal = sum(
            row["bb100"] < 0.0 for row in stats["by_anchor"].values()
        ) >= 3
        return both_seats_negative and broad_anchor_reversal

    collapse_seeds = [
        seed
        for seed in range(1, 4)
        if collapse_seed(seed, "moving_slope") or collapse_seed(seed, "final_delta")
    ]
    mechanics_pass = all(integrity.values()) and all(drift_integrity.values())
    catastrophic_drift = any(
        row["mean_tv"] > 0.08 or row["greedy_disagreement_rate"] > 0.12
        for row in drift.values()
    )
    replicated_proxy_reversal = len(collapse_seeds) >= 2
    gates = {
        "mechanically_sound": mechanics_pass,
        "moving_slope_positive_at_least_two_seeds": sum(x > 0.0 for x in moving_slopes) >= 2,
        "moving_slope_median_positive": statistics.median(moving_slopes) > 0.0,
        "no_replicated_both_seat_broad_anchor_collapse": not replicated_proxy_reversal,
        "final_moving_minus_static_nonnegative_at_least_two_seeds": (
            sum(x >= 0.0 for x in final_deltas) >= 2
        ),
        "all_final_source_drift_below_preregistered_limits": not catastrophic_drift,
    }
    promote = all(gates.values())
    clear_reject = (not mechanics_pass) or catastrophic_drift or replicated_proxy_reversal
    if promote:
        decision = "PROMOTE_MOVING_REFERENCE_TO_262K_GEOMETRIC_SCALE"
        interpretation = "directional mechanism evidence supports scaling"
    elif clear_reject:
        decision = "REJECT_SPECIFIC_REFRESH_EVERY_UPDATE_MECHANISM"
        interpretation = "replicated mechanism, integrity, or catastrophic-drift gate failed"
    else:
        decision = "INSUFFICIENT_SCALE_OR_MIXED_DIRECTIONAL_EVIDENCE"
        interpretation = "do not infer method failure from this 65k-scale pilot"

    result = {
        "schema": "cardpilot.nashpg_moving_reference_geometric_aggregate.v1",
        "status": "COMPLETED",
        "design": {
            "training_seeds": 3,
            "comparisons_per_seed": len(COMPARISONS),
            "pairs_per_anchor": 2048,
            "anchors": list(ANCHORS),
            "policy_mode": "greedy",
            "evaluation_contract": "untouched_common_deck_both_seats",
            "slumbot_hands": 0,
        },
        "evaluation_hands": total_evaluation_hands,
        "aggregate": aggregate,
        "drift": drift,
        "integrity": {**integrity, **drift_integrity},
        "gates": gates,
        "collapse_seeds": collapse_seeds,
        "promote": promote,
        "clear_reject": clear_reject,
        "decision": decision,
        "interpretation": interpretation,
        "input_sha256": input_sha256,
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
