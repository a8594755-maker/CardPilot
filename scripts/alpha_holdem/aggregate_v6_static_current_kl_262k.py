#!/usr/bin/env python3
"""Verify and aggregate the preregistered static current-KL 262k scale test."""

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


ANCHORS = ("standard10", "cfr4", "legacy_iter16", "legacy_mixed65k")
EXPECTED_EVAL_SEEDS = {1: 20263041, 2: 20263042, 3: 20263043}
EXPECTED_DRIFT_SEEDS = {1: 20263051, 2: 20263052, 3: 20263053}


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


def command_value(command: list[str], flag: str) -> str:
    index = command.index(flag)
    return str(command[index + 1])


def row_key(row: dict) -> tuple[str, int]:
    return str(row["anchor"]), int(row["pair_index"])


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
    result = {
        "pooled": mean_ci95_bb100(pooled),
        "by_anchor": {
            anchor: mean_ci95_bb100(by_anchor[anchor]) for anchor in ANCHORS
        },
        "by_seat": {
            str(seat): mean_ci95_bb100(by_seat[seat]) for seat in (0, 1)
        },
    }
    result["positive_anchor_count"] = sum(
        row["bb100"] >= 0.0 for row in result["by_anchor"].values()
    )
    result["both_seats_nonnegative"] = all(
        row["bb100"] >= 0.0 for row in result["by_seat"].values()
    )
    result["both_seats_negative"] = all(
        row["bb100"] < 0.0 for row in result["by_seat"].values()
    )
    return result


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
    first_deck_hashes = []
    control_hashes = []
    treatment_hashes = []
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
            == EXPECTED_EVAL_SEEDS[seed]
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
        total_evaluation_hands += int(summary["evaluation_hands"])
        first_deck_hashes.append(
            hashlib.sha256(
                json.dumps(rows[0]["deck"], separators=(",", ":")).encode()
            ).hexdigest()
        )
        control_hashes.append(summary["input_sha256"]["control"])
        treatment_hashes.append(summary["input_sha256"]["treatment"])

    integrity["cross_seed_eval_seeds_unique"] = (
        len(set(EXPECTED_EVAL_SEEDS.values())) == 3
    )
    integrity["cross_seed_first_decks_unique"] = len(set(first_deck_hashes)) == 3
    integrity["cross_seed_control_checkpoints_unique"] = len(set(control_hashes)) == 3
    integrity["cross_seed_treatment_checkpoints_unique"] = (
        len(set(treatment_hashes)) == 3
    )

    drift = {}
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
            "greedy_disagreement_rate": float(
                analysis["overall"]["greedy_disagreement_rate"]
            ),
            "changed_parameter_scope": analysis["tensor_scope"]["status"],
            "metadata_mismatch_count": len(
                analysis["checkpoint_metadata_mismatches"]
            ),
            "analysis_sha256": sha256_path(analysis_path),
            "raw_sha256": sha256_path(raw_path),
        }
        integrity[f"drift_seed{seed}_contract"] = (
            int(analysis["design"]["states"]) == 20000
            and int(analysis["design"]["seed"]) == EXPECTED_DRIFT_SEEDS[seed]
            and analysis["tensor_scope"]["status"] == "PASS"
            and not analysis["checkpoint_metadata_mismatches"]
        )
        integrity[f"drift_seed{seed}_raw_hash"] = (
            sha256_path(raw_path) == analysis["raw_sha256"]
        )
        integrity[f"drift_seed{seed}_checkpoint_relation"] = (
            analysis["treatment"]["sha256"] == treatment_hashes[seed - 1]
            and analysis["parent"]["sha256"]
            == "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"
        )

    slopes = [seed_summaries[str(seed)]["pooled"]["bb100"] for seed in range(1, 4)]
    breadth_qualified_seeds = [
        seed
        for seed in range(1, 4)
        if seed_summaries[str(seed)]["both_seats_nonnegative"]
        and seed_summaries[str(seed)]["positive_anchor_count"] >= 3
    ]
    collapse_seeds = [
        seed
        for seed in range(1, 4)
        if seed_summaries[str(seed)]["both_seats_negative"]
        and sum(
            row["bb100"] < 0.0
            for row in seed_summaries[str(seed)]["by_anchor"].values()
        )
        >= 3
    ]
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
        "breadth_qualified_at_least_two_seeds": len(breadth_qualified_seeds) >= 2,
        "all_final_source_drift_below_limits": not catastrophic_drift,
        "no_replicated_broad_proxy_reversal": not replicated_proxy_reversal,
    }
    promote = all(gates.values())
    clear_reject = (not mechanics_pass) or catastrophic_drift or replicated_proxy_reversal
    if promote:
        decision = "PROMOTE_STATIC_CURRENT_KL_BEYOND_262K"
        interpretation = "multi-seed directional and breadth evidence supports scaling"
    elif clear_reject:
        decision = "REJECT_STATIC_CURRENT_KL_SCALE_MECHANISM"
        interpretation = "integrity, catastrophic drift, or replicated broad reversal gate failed"
    else:
        decision = "INSUFFICIENT_SCALE_OR_MIXED_DIRECTIONAL_EVIDENCE"
        interpretation = "do not infer method failure from noisy 262k-scale evidence"

    result = {
        "schema": "cardpilot.static_current_kl_262k_aggregate.v1",
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
            "total_cumulative_environment_hands": training[
                "total_physical_environment_hands"
            ],
        },
        "evaluation_hands": total_evaluation_hands,
        "offline_drift_states": 60000,
        "aggregate": {
            "combined": summarize_rows(all_rows),
            "by_seed": seed_summaries,
        },
        "drift": drift,
        "integrity": integrity,
        "gates": gates,
        "breadth_qualified_seeds": breadth_qualified_seeds,
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
