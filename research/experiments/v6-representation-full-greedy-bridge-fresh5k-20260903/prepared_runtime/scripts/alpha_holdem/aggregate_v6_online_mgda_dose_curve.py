"""Join shared-deck interpolation doses and combine independent alpha=1 evidence."""
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


def load_eval(directory: Path) -> tuple[dict, dict[tuple[str, int], dict]]:
    summary_path = directory / "summary.json"
    raw_path = directory / "common_deck_pairs.jsonl.gz"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    if sha256_path(raw_path) != summary["raw_pairs_sha256"]:
        raise ValueError(f"raw SHA mismatch: {directory}")
    with gzip.open(raw_path, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle if line.strip()]
    keyed = {(str(row["anchor"]), int(row["pair_index"])): row for row in rows}
    if len(keyed) != len(rows):
        raise ValueError(f"duplicate pair key: {directory}")
    return summary, keyed


def stats(values: list[float]) -> dict:
    mean, half = mean_ci95(values)
    return {
        "pairs": len(values),
        "delta_bb100": mean * 100.0,
        "ci95_half_bb100": half * 100.0,
        "ci95_lower_bb100": (mean - half) * 100.0,
        "ci95_upper_bb100": (mean + half) * 100.0,
        "nonzero_pairs": sum(not math.isclose(value, 0.0) for value in values),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dose", action="append", nargs=2, metavar=("ALPHA", "DIR"), required=True)
    parser.add_argument("--prior-alpha1-eval", type=Path, required=True)
    parser.add_argument("--prior-alpha1-audit", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    doses = {float(alpha): Path(path) for alpha, path in args.dose}
    if sorted(doses) != [0.125, 0.25, 0.5, 1.0]:
        parser.error("exact doses 0.125,0.25,0.5,1.0 are required")

    summaries = {}
    rows_by_dose = {}
    for alpha, directory in sorted(doses.items()):
        summaries[alpha], rows_by_dose[alpha] = load_eval(directory)
    keys = set(rows_by_dose[0.125])
    shared_keys = all(set(rows) == keys for rows in rows_by_dose.values())
    shared_decks = shared_keys and all(
        rows_by_dose[alpha][key]["deck"] == rows_by_dose[0.125][key]["deck"]
        for alpha in doses
        for key in keys
    )
    shared_controls = shared_keys and all(
        rows_by_dose[alpha][key]["control_rewards_bb"]
        == rows_by_dose[0.125][key]["control_rewards_bb"]
        for alpha in doses
        for key in keys
    )
    if not shared_decks or not shared_controls:
        raise RuntimeError("dose cohort is not exact shared-deck/shared-control")

    dose_stats = {}
    per_anchor = {}
    for alpha, rows in sorted(rows_by_dose.items()):
        values = [
            float(rows[key]["treatment_minus_control_pair_mean_bb"])
            for key in sorted(keys)
        ]
        dose_stats[str(alpha)] = stats(values)
        anchor_stats = {}
        for anchor in sorted({key[0] for key in keys}):
            anchor_stats[anchor] = stats([
                float(rows[key]["treatment_minus_control_pair_mean_bb"])
                for key in sorted(keys) if key[0] == anchor
            ])
        per_anchor[str(alpha)] = anchor_stats

    increment_stats = {}
    previous_alpha = 0.0
    previous_values = {
        key: float(rows_by_dose[0.125][key]["control_pair_mean_bb"])
        for key in keys
    }
    for alpha in sorted(doses):
        current_values = {
            key: float(rows_by_dose[alpha][key]["treatment_pair_mean_bb"])
            for key in keys
        }
        increment_stats[f"{previous_alpha:g}_to_{alpha:g}"] = stats([
            current_values[key] - previous_values[key] for key in sorted(keys)
        ])
        previous_alpha = alpha
        previous_values = current_values

    prior_summary, prior_rows = load_eval(args.prior_alpha1_eval)
    prior_audit = json.loads(args.prior_alpha1_audit.read_text(encoding="utf-8"))
    prior_raw = args.prior_alpha1_eval / "common_deck_pairs.jsonl.gz"
    prior_bound = (
        prior_audit["passed"]
        and prior_audit["hashes"]["eval_raw"] == sha256_path(prior_raw)
        and prior_summary["input_sha256"]["treatment"]
        == summaries[1.0]["input_sha256"]["treatment"]
        and prior_summary["input_sha256"]["control"]
        == summaries[1.0]["input_sha256"]["control"]
    )
    current_alpha1 = [
        float(row["treatment_minus_control_pair_mean_bb"])
        for row in rows_by_dose[1.0].values()
    ]
    prior_alpha1 = [
        float(row["treatment_minus_control_pair_mean_bb"])
        for row in prior_rows.values()
    ]
    combined_alpha1 = stats(prior_alpha1 + current_alpha1)
    low_doses_negative = all(
        dose_stats[str(alpha)]["delta_bb100"] < 0.0
        for alpha in (0.125, 0.25, 0.5)
    )
    gates = {
        "four_doses_present": len(doses) == 4,
        "shared_pair_keys": shared_keys,
        "shared_decks": shared_decks,
        "shared_control_rewards": shared_controls,
        "pair_count_exact": len(keys) == 2048,
        "raw_summary_recomputed": all(
            math.isclose(
                dose_stats[str(alpha)]["delta_bb100"],
                summaries[alpha]["pooled_treatment_minus_control_bb100"],
            )
            for alpha in doses
        ),
        "prior_alpha1_hash_and_checkpoint_bound": prior_bound,
    }
    if not all(gates.values()):
        raise RuntimeError(f"dose curve gates failed: {gates}")
    result = {
        "schema": "cardpilot.online_mgda_realized_dose_curve.v1",
        "gates": gates,
        "passed": all(gates.values()),
        "dose_stats": dose_stats,
        "per_anchor": per_anchor,
        "nested_increment_stats": increment_stats,
        "combined_independent_alpha1": combined_alpha1,
        "findings": {
            "low_doses_all_directionally_negative": low_doses_negative,
            "prior_alpha1_ci_upper_negative": (
                prior_audit["pooled_ci95_upper_bb100"] < 0.0
            ),
            "combined_alpha1_mean_negative": (
                combined_alpha1["delta_bb100"] < 0.0
            ),
            "combined_alpha1_ci_upper_negative": (
                combined_alpha1["ci95_upper_bb100"] < 0.0
            ),
        },
        "current_evaluation_hands": len(keys) * 4 * len(doses),
        "combined_alpha1_evaluation_hands": (
            len(prior_alpha1) + len(current_alpha1)
        ) * 4,
        "decision": (
            "CLOSE_UNIT_NORMALIZED_ONLINE_MGDA_DIRECTION"
            if low_doses_negative
            and prior_audit["pooled_ci95_upper_bb100"] < 0.0
            and combined_alpha1["delta_bb100"] < 0.0
            else "HOLD_ONLINE_MGDA_DOSE_DIRECTION"
        ),
        "hashes": {
            "prior_audit": sha256_path(args.prior_alpha1_audit),
            **{
                f"dose_{alpha:g}_raw": sha256_path(
                    directory / "common_deck_pairs.jsonl.gz"
                )
                for alpha, directory in sorted(doses.items())
            },
        },
        "command": [sys.executable, *sys.argv],
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
