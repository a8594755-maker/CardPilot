#!/usr/bin/env python3
"""Verify and aggregate a preregistered static current-KL geometric test."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import statistics
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parent))
from aggregate_v6_static_current_kl_262k import (
    ANCHORS,
    command_value,
    read_json,
    read_rows,
    row_key,
    sha256_path,
    summarize_rows,
)


EXPECTED_EVAL_SEEDS = {1: 20263081, 2: 20263082, 3: 20263083}
EXPECTED_DRIFT_SEEDS = {1: 20263091, 2: 20263092, 3: 20263093}
STANDARD10_SHA256 = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def deck_key(row: dict) -> tuple[str, str]:
    payload = json.dumps(row["deck"], separators=(",", ":"), sort_keys=True)
    return str(row["anchor"]), hashlib.sha256(payload.encode()).hexdigest()


def collapse(summary: dict) -> bool:
    return summary["both_seats_negative"] and sum(
        row["bb100"] < 0.0 for row in summary["by_anchor"].values()
    ) >= 3


def breadth(summary: dict) -> bool:
    return (
        summary["both_seats_nonnegative"]
        and summary["positive_anchor_count"] >= 3
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--prior-dir", type=Path, action="append", required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--eval-seed-base", type=int, default=20263080)
    parser.add_argument("--drift-seed-base", type=int, default=20263090)
    parser.add_argument("--expected-prior-raw-rows", type=int, default=73728)
    parser.add_argument("--scale-label", default="1M")
    parser.add_argument(
        "--schema", default="cardpilot.static_current_kl_1m_aggregate.v1"
    )
    parser.add_argument("--breadth-informational-only", action="store_true")
    parser.add_argument(
        "--require-positive-combined",
        action="store_true",
        help="Require the pooled cross-seed point estimate to be positive for promotion.",
    )
    parser.add_argument(
        "--require-improved-breadth",
        action="store_true",
        help=(
            "Require at least one breadth-qualified seed or no combined seat with "
            "a confidence interval wholly below zero."
        ),
    )
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    root = args.experiment_dir.resolve()
    expected_eval_seeds = {
        seed: args.eval_seed_base + seed for seed in range(1, 4)
    }
    expected_drift_seeds = {
        seed: args.drift_seed_base + seed for seed in range(1, 4)
    }

    integrity: dict[str, bool] = {}
    input_sha256: dict[str, str] = {}
    training_path = root / "training_audit.json"
    training = read_json(training_path)
    input_sha256[str(training_path)] = sha256_path(training_path)
    integrity["training_audit_passed"] = (
        training.get("passed") is True
        and int(training.get("passed_runs", -1)) == 3
        and int(training.get("total_new_environment_hands", -1)) > 0
    )

    seed_summaries: dict[str, dict] = {}
    all_rows: list[dict] = []
    first_deck_hashes: list[str] = []
    control_hashes: list[str] = []
    treatment_hashes: list[str] = []
    current_deck_keys: list[tuple[str, str]] = []
    total_evaluation_hands = 0
    for seed in range(1, 4):
        directory = root / f"eval_seed{seed}"
        summary_path = directory / "summary.json"
        raw_path = directory / "common_deck_pairs.jsonl.gz"
        summary = read_json(summary_path)
        rows = read_rows(raw_path)
        row_map = {row_key(row): row for row in rows}
        input_sha256[str(summary_path)] = sha256_path(summary_path)
        input_sha256[str(raw_path)] = sha256_path(raw_path)
        integrity[f"seed{seed}_completed"] = summary.get("status") == "COMPLETED"
        integrity[f"seed{seed}_raw_hash"] = (
            sha256_path(raw_path) == summary.get("raw_pairs_sha256")
        )
        integrity[f"seed{seed}_row_count_unique"] = (
            len(rows) == len(row_map) == 2048 * len(ANCHORS)
        )
        integrity[f"seed{seed}_accounting"] = (
            int(summary.get("evaluation_hands", -1)) == 32768
            and int(summary.get("pairs_per_anchor", -1)) == 2048
            and int(summary.get("anchor_count", -1)) == len(ANCHORS)
        )
        integrity[f"seed{seed}_anchors"] = (
            tuple(row["anchor"] for row in summary.get("anchors", [])) == ANCHORS
            and set(anchor for anchor, _ in row_map) == set(ANCHORS)
        )
        integrity[f"seed{seed}_eval_seed"] = (
            int(command_value(summary["command"], "--seed"))
            == expected_eval_seeds[seed]
        )
        training_row = training["runs"][seed - 1]
        integrity[f"seed{seed}_checkpoint_relation"] = (
            summary["input_sha256"]["control"]
            == training_row["parent"]["sha256"]
            and summary["input_sha256"]["treatment"]
            == training_row["hashes"]["checkpoint"]
        )
        integrity[f"seed{seed}_anchor_hashes_complete"] = all(
            f"anchor:{anchor}" in summary["input_sha256"] for anchor in ANCHORS
        )
        seed_summaries[str(seed)] = summarize_rows(rows)
        all_rows.extend(rows)
        current_deck_keys.extend(deck_key(row) for row in rows)
        total_evaluation_hands += int(summary["evaluation_hands"])
        first_deck_hashes.append(
            hashlib.sha256(
                json.dumps(rows[0]["deck"], separators=(",", ":")).encode()
            ).hexdigest()
        )
        control_hashes.append(summary["input_sha256"]["control"])
        treatment_hashes.append(summary["input_sha256"]["treatment"])

    integrity["cross_seed_eval_seeds_unique"] = len(set(expected_eval_seeds.values())) == 3
    integrity["cross_seed_first_decks_unique"] = len(set(first_deck_hashes)) == 3
    integrity["cross_seed_control_checkpoints_unique"] = len(set(control_hashes)) == 3
    integrity["cross_seed_treatment_checkpoints_unique"] = len(set(treatment_hashes)) == 3
    integrity["all_current_decks_unique_within_anchor"] = (
        len(current_deck_keys) == len(set(current_deck_keys))
    )

    prior_deck_keys: set[tuple[str, str]] = set()
    prior_rows_total = 0
    for prior_root_arg in args.prior_dir:
        prior_root = prior_root_arg.resolve()
        for seed in range(1, 4):
            prior_raw = prior_root / f"eval_seed{seed}" / "common_deck_pairs.jsonl.gz"
            rows = read_rows(prior_raw)
            input_sha256[str(prior_raw)] = sha256_path(prior_raw)
            prior_rows_total += len(rows)
            prior_deck_keys.update(deck_key(row) for row in rows)
    integrity["prior_raw_row_count"] = (
        prior_rows_total == args.expected_prior_raw_rows
    )
    integrity["all_current_decks_disjoint_from_prior"] = not (
        set(current_deck_keys) & prior_deck_keys
    )

    drift: dict[str, dict] = {}
    for seed in range(1, 4):
        directory = root / f"drift_seed{seed}"
        analysis_path = directory / "drift_analysis.json"
        raw_path = directory / "drift_raw.jsonl.gz"
        analysis = read_json(analysis_path)
        input_sha256[str(analysis_path)] = sha256_path(analysis_path)
        input_sha256[str(raw_path)] = sha256_path(raw_path)
        drift[str(seed)] = {
            "states": int(analysis["overall"]["states"]),
            "mean_tv": float(analysis["overall"]["mean_tv"]),
            "greedy_disagreement_rate": float(analysis["overall"]["greedy_disagreement_rate"]),
            "changed_parameter_scope": analysis["tensor_scope"]["status"],
            "metadata_mismatch_count": len(analysis["checkpoint_metadata_mismatches"]),
            "analysis_sha256": sha256_path(analysis_path),
            "raw_sha256": sha256_path(raw_path),
        }
        integrity[f"drift_seed{seed}_contract"] = (
            int(analysis["design"]["states"]) == 20000
            and int(analysis["design"]["seed"]) == expected_drift_seeds[seed]
            and analysis["tensor_scope"]["status"] == "PASS"
            and not analysis["checkpoint_metadata_mismatches"]
        )
        integrity[f"drift_seed{seed}_raw_hash"] = (
            sha256_path(raw_path) == analysis["raw_sha256"]
        )
        integrity[f"drift_seed{seed}_checkpoint_relation"] = (
            analysis["treatment"]["sha256"] == treatment_hashes[seed - 1]
            and analysis["parent"]["sha256"] == STANDARD10_SHA256
        )

    slopes = [seed_summaries[str(seed)]["pooled"]["bb100"] for seed in range(1, 4)]
    breadth_seeds = [seed for seed in range(1, 4) if breadth(seed_summaries[str(seed)])]
    collapse_seeds = [seed for seed in range(1, 4) if collapse(seed_summaries[str(seed)])]
    combined_summary = summarize_rows(all_rows)
    no_significantly_negative_combined_seat = all(
        row["ci95_high_bb100"] >= 0.0
        for row in combined_summary["by_seat"].values()
    )
    improved_breadth = (
        len(breadth_seeds) >= 1 or no_significantly_negative_combined_seat
    )
    mechanics_pass = all(integrity.values())
    catastrophic_drift = any(
        row["mean_tv"] > 0.08 or row["greedy_disagreement_rate"] > 0.12
        for row in drift.values()
    )
    replicated_proxy_reversal = len(collapse_seeds) >= 2
    gates = {
        "mechanically_sound": mechanics_pass,
        "positive_slope_at_least_two_seeds": sum(x > 0.0 for x in slopes) >= 2,
        "median_slope_positive": statistics.median(slopes) > 0.0,
        "breadth_qualified_at_least_two_seeds": len(breadth_seeds) >= 2,
        "combined_slope_positive": combined_summary["pooled"]["bb100"] > 0.0,
        "improved_breadth": improved_breadth,
        "no_significantly_negative_combined_seat": (
            no_significantly_negative_combined_seat
        ),
        "all_final_source_drift_below_limits": not catastrophic_drift,
        "no_replicated_broad_proxy_reversal": not replicated_proxy_reversal,
    }
    promotion_gate_names = {
        "mechanically_sound",
        "positive_slope_at_least_two_seeds",
        "median_slope_positive",
        "all_final_source_drift_below_limits",
        "no_replicated_broad_proxy_reversal",
    }
    if not args.breadth_informational_only:
        promotion_gate_names.add("breadth_qualified_at_least_two_seeds")
    if args.require_positive_combined:
        promotion_gate_names.add("combined_slope_positive")
    if args.require_improved_breadth:
        promotion_gate_names.add("improved_breadth")
    promote = all(gates[name] for name in promotion_gate_names)
    clear_reject = (not mechanics_pass) or catastrophic_drift or replicated_proxy_reversal
    if promote:
        decision = f"PROMOTE_STATIC_CURRENT_KL_BEYOND_{args.scale_label.upper()}"
        interpretation = (
            "multi-seed directional gate passed without replicated broad reversal; "
            "breadth remains mixed and must be monitored at the next scale"
            if args.breadth_informational_only
            and not gates["breadth_qualified_at_least_two_seeds"]
            else "multi-seed directional and breadth evidence supports additional geometric scaling"
        )
    elif clear_reject:
        decision = "REJECT_STATIC_CURRENT_KL_SCALE_MECHANISM"
        interpretation = "integrity, catastrophic drift, or independently replicated broad reversal failed"
    else:
        decision = (
            "INSUFFICIENT_SCALE_OR_MIXED_DIRECTIONAL_EVIDENCE"
            if args.scale_label.upper() == "1M"
            else f"STOP_FOR_DIAGNOSIS_MIXED_{args.scale_label.upper()}_EVIDENCE"
        )
        interpretation = (
            "do not infer long-horizon method failure from a noisy geometric-scale result"
        )

    result = {
        "schema": args.schema,
        "status": "COMPLETED",
        "design": {
            "training_seeds": 3,
            "pairs_per_anchor": 2048,
            "anchors": list(ANCHORS),
            "policy_mode": "greedy",
            "evaluation_contract": "untouched_common_deck_both_seats",
            "slumbot_hands": 0,
        },
        "training": {
            "total_new_environment_hands": training["total_new_environment_hands"],
            "total_cumulative_environment_hands": training["total_physical_environment_hands"],
        },
        "evaluation_hands": total_evaluation_hands,
        "offline_drift_states": 60000,
        "aggregate": {"combined": combined_summary, "by_seed": seed_summaries},
        "drift": drift,
        "integrity": integrity,
        "gates": gates,
        "promotion_gate_names": sorted(promotion_gate_names),
        "breadth_qualified_seeds": breadth_seeds,
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
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    if not mechanics_pass:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
