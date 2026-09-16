"""Audit and localize frozen multi-seed AlphaHoldem archive curves."""
from __future__ import annotations

import argparse
from collections import Counter
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import numpy as np


T95_DF2 = 4.302652729696142
ENDPOINTS = ("iter32", "iter48", "final")
ANCHORS = ("standard10", "cfr4")


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_raw(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def parse_hands(value: str) -> tuple[int, list[int]]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("hands must be SEED=PARENT,I32,I48,FINAL")
    raw_seed, raw_values = value.split("=", 1)
    values = [int(item) for item in raw_values.split(",")]
    if len(values) != 4 or any(item <= 0 for item in values):
        raise argparse.ArgumentTypeError("hands must have four positive integers")
    return int(raw_seed.removeprefix("seed")), values


def mean_ci95(values: list[float]) -> dict:
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean())
    half = 1.96 * float(array.std(ddof=1)) / math.sqrt(len(array))
    return {"mean_bb100": mean * 100.0, "ci95_half_bb100": half * 100.0}


def seed_t_summary(values: list[float]) -> dict:
    mean = statistics.fmean(values)
    half = T95_DF2 * statistics.stdev(values) / math.sqrt(len(values))
    return {
        "values_bb100": values,
        "mean_bb100": mean,
        "student_t95_low_bb100": mean - half,
        "student_t95_high_bb100": mean + half,
        "student_t_df": 2,
    }


def subset(rows: list[dict], anchor: str | None) -> list[dict]:
    return rows if anchor is None else [row for row in rows if row["anchor"] == anchor]


def summarize_endpoint(rows: list[dict]) -> dict:
    output = {}
    for anchor in (None, *ANCHORS):
        selected = subset(rows, anchor)
        deltas = [float(row["treatment_minus_control_pair_mean_bb"]) for row in selected]
        seats = [
            mean_ci95(
                [float(row["treatment_minus_control_rewards_bb"][seat]) for row in selected]
            )
            for seat in (0, 1)
        ]
        output[anchor or "pooled"] = {**mean_ci95(deltas), "seats": seats}
    return output


def paired_contrast(early: list[dict], late: list[dict]) -> dict:
    early_map = {(row["anchor"], int(row["pair_index"])): row for row in early}
    late_map = {(row["anchor"], int(row["pair_index"])): row for row in late}
    output = {}
    for anchor in (None, *ANCHORS):
        keys = [key for key in early_map if anchor is None or key[0] == anchor]
        means = [
            float(late_map[key]["treatment_pair_mean_bb"])
            - float(early_map[key]["treatment_pair_mean_bb"])
            for key in keys
        ]
        seats = []
        for seat in (0, 1):
            values = [
                float(late_map[key]["treatment_rewards_bb"][seat])
                - float(early_map[key]["treatment_rewards_bb"][seat])
                for key in keys
            ]
            seats.append(mean_ci95(values))
        output[anchor or "pooled"] = {**mean_ci95(means), "seats": seats}
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument("--prior-experiment-dir", type=Path, required=True)
    parser.add_argument("--hands", action="append", type=parse_hands, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    hands = dict(args.hands)
    if set(hands) != {1, 2, 3}:
        parser.error("--hands must specify seeds 1, 2, and 3 exactly once")

    root = args.experiment_dir.resolve()
    prior_root = args.prior_experiment_dir.resolve()
    seeds = []
    all_gates: list[bool] = []
    for seed in (1, 2, 3):
        endpoint_rows: dict[str, list[dict]] = {}
        endpoint_summaries = {}
        endpoint_artifacts = {}
        reference_keys = None
        reference_controls = None
        endpoint_gates = {}
        for endpoint in ENDPOINTS:
            eval_dir = root / f"eval_seed{seed}_{endpoint}"
            summary_path = eval_dir / "summary.json"
            raw_path = eval_dir / "common_deck_pairs.jsonl.gz"
            summary = load_json(summary_path)
            rows = load_raw(raw_path)
            keys = [(row["anchor"], int(row["pair_index"])) for row in rows]
            controls = {
                key: (
                    row["deck"],
                    float(row["control_pair_mean_bb"]),
                    tuple(float(value) for value in row["control_rewards_bb"]),
                )
                for key, row in zip(keys, rows)
            }
            counts = Counter(row["anchor"] for row in rows)
            gates = {
                "raw_sha_exact": sha256_path(raw_path) == summary["raw_pairs_sha256"],
                "row_count_exact": len(rows) == 2048,
                "anchor_counts_exact": counts == Counter({"standard10": 1024, "cfr4": 1024}),
                "keys_unique": len(keys) == len(set(keys)),
                "summary_evaluation_hands_exact": int(summary["evaluation_hands"]) == 8192,
            }
            if reference_keys is None:
                reference_keys = keys
                reference_controls = controls
            else:
                gates["common_keys_across_endpoints"] = keys == reference_keys
                gates["common_decks_and_controls_across_endpoints"] = controls == reference_controls
            endpoint_rows[endpoint] = rows
            endpoint_summaries[endpoint] = summarize_endpoint(rows)
            endpoint_gates[endpoint] = gates
            endpoint_artifacts[endpoint] = {
                "summary": {"path": str(summary_path), "sha256": sha256_path(summary_path)},
                "raw": {"path": str(raw_path), "sha256": sha256_path(raw_path)},
            }
            all_gates.extend(gates.values())

        contrasts = {
            "iter48_minus_iter32": paired_contrast(
                endpoint_rows["iter32"], endpoint_rows["iter48"]
            ),
            "final_minus_iter48": paired_contrast(
                endpoint_rows["iter48"], endpoint_rows["final"]
            ),
            "final_minus_iter32": paired_contrast(
                endpoint_rows["iter32"], endpoint_rows["final"]
            ),
        }
        x_hands = np.asarray(hands[seed], dtype=np.float64) / 100_000.0
        slopes = {}
        for label in ("pooled", *ANCHORS):
            y = [0.0] + [endpoint_summaries[ep][label]["mean_bb100"] for ep in ENDPOINTS]
            slopes[label] = float(np.polyfit(x_hands, np.asarray(y), 1)[0])

        prior = load_json(prior_root / f"eval_seed{seed}" / "summary.json")
        prior_common = statistics.fmean(
            float(row["treatment_minus_control_bb100"])
            for row in prior["anchors"]
            if row["anchor"] in ANCHORS
        )
        current_common = endpoint_summaries["final"]["pooled"]["mean_bb100"]
        seeds.append(
            {
                "seed": seed,
                "environment_hands": {
                    "parent": hands[seed][0],
                    **dict(zip(ENDPOINTS, hands[seed][1:])),
                },
                "endpoints": endpoint_summaries,
                "paired_contrasts": contrasts,
                "linear_slope_bb100_per_100k_hands": slopes,
                "endpoint_gates": endpoint_gates,
                "artifacts": endpoint_artifacts,
                "prior_panel_common_anchor_final_bb100": prior_common,
                "current_panel_common_anchor_final_bb100": current_common,
                "prior_current_sign_flip": (prior_common > 0) != (current_common > 0),
            }
        )

    aggregate_endpoints = {}
    for endpoint in ENDPOINTS:
        aggregate_endpoints[endpoint] = {
            label: seed_t_summary(
                [row["endpoints"][endpoint][label]["mean_bb100"] for row in seeds]
            )
            for label in ("pooled", *ANCHORS)
        }
    aggregate_contrasts = {
        label: seed_t_summary(
            [
                row["paired_contrasts"]["final_minus_iter32"][label]["mean_bb100"]
                for row in seeds
            ]
        )
        for label in ("pooled", *ANCHORS)
    }
    below_counts = {
        label: sum(
            row["paired_contrasts"]["final_minus_iter32"][label]["mean_bb100"] < 0
            for row in seeds
        )
        for label in ("pooled", *ANCHORS)
    }
    selective_tradeoff = (
        below_counts["standard10"] >= 2
        and below_counts["cfr4"] <= 1
        and aggregate_contrasts["standard10"]["mean_bb100"] < 0
        and aggregate_contrasts["cfr4"]["mean_bb100"] >= 0
    )
    coherent_broad_decline = (
        below_counts["pooled"] >= 2
        and aggregate_contrasts["pooled"]["student_t95_high_bb100"] < 0
    )
    coherent_positive_curve = (
        below_counts["pooled"] <= 1
        and aggregate_contrasts["pooled"]["student_t95_low_bb100"] > 0
    )
    evidence_passed = all(all_gates)
    if selective_tradeoff:
        decision = "CHANGE_LEAGUE_OR_STANDARD10_PRESERVATION_OBJECTIVE"
    elif coherent_broad_decline:
        decision = "STOP_INTEGRATED_RECIPE_FOR_BROAD_DEGRADATION"
    elif coherent_positive_curve:
        decision = "REOPEN_MULTI_SEED_SCALING"
    else:
        decision = "RUN_ONE_SEED_1M_DEEP_CONVERGENCE_CONTROL"
    output = {
        "schema": "cardpilot.integrated_alphaholdem_archive_curve_audit.v1",
        "design": {
            "endpoints": list(ENDPOINTS),
            "anchors": list(ANCHORS),
            "pairs_per_anchor": 1024,
            "evaluation_hands": 73_728,
            "raw_pair_rows": 18_432,
            "paired_within_seed_across_endpoints": True,
        },
        "seeds": seeds,
        "aggregate_endpoints": aggregate_endpoints,
        "aggregate_final_minus_iter32": aggregate_contrasts,
        "final_below_iter32_seed_counts": below_counts,
        "prior_current_final_panel_sign_flip_count": sum(
            row["prior_current_sign_flip"] for row in seeds
        ),
        "classification": {
            "selective_standard10_tradeoff": selective_tradeoff,
            "coherent_broad_decline": coherent_broad_decline,
            "coherent_positive_curve": coherent_positive_curve,
            "nonmonotone_high_variance": not any(
                (selective_tradeoff, coherent_broad_decline, coherent_positive_curve)
            ),
        },
        "evidence_passed": evidence_passed,
        "decision": decision if evidence_passed else "INVALID_EVIDENCE_DO_NOT_DECIDE",
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(output, sort_keys=True))
    if not evidence_passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
