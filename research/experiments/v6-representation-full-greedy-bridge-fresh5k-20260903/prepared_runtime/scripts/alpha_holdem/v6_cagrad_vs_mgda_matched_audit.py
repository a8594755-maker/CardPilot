"""Exact paired audit of CAGrad against the prior matched MGDA treatment."""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.alpha_holdem.v6_dual_contract_residual_training_smoke import mean_ci95


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gzip_content_sha256(path: Path) -> str:
    """Hash decompressed bytes so gzip header timestamps are irrelevant."""
    digest = hashlib.sha256()
    with gzip.open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> dict[tuple[int, int], dict]:
    rows = {}
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        for line in handle:
            row = json.loads(line)
            key = (int(row["anchor_index"]), int(row["pair_index"]))
            if key in rows:
                raise ValueError(f"duplicate evaluation key {key}")
            rows[key] = row
    return rows


def paired_summary(values: list[float]) -> dict:
    mean, half = mean_ci95(values)
    return {
        "pairs": len(values),
        "delta_bb100": mean * 100.0,
        "delta_ci95_half_bb100": half * 100.0,
        "delta_ci95_lower_bb100": (mean - half) * 100.0,
        "delta_ci95_upper_bb100": (mean + half) * 100.0,
    }


def audit(mgda_dir: Path, cagrad_dir: Path) -> dict:
    mgda_summary = json.loads((mgda_dir / "summary.json").read_text(encoding="utf-8"))
    cagrad_summary = json.loads((cagrad_dir / "summary.json").read_text(encoding="utf-8"))
    mgda_path = mgda_dir / "evaluation_pairs.jsonl.gz"
    cagrad_path = cagrad_dir / "evaluation_pairs.jsonl.gz"
    mgda_rows = load_rows(mgda_path)
    cagrad_rows = load_rows(cagrad_path)
    if set(mgda_rows) != set(cagrad_rows):
        raise ValueError("evaluation keys differ")

    controls_exact = True
    decks_exact = True
    anchor_shas_exact = True
    pooled = []
    pooled_seats = [[], []]
    by_anchor: dict[int, list[float]] = {}
    for key in sorted(mgda_rows):
        mgda = mgda_rows[key]
        cagrad = cagrad_rows[key]
        decks_exact &= mgda["deck"] == cagrad["deck"]
        controls_exact &= mgda["control_rewards_bb"] == cagrad["control_rewards_bb"]
        anchor_shas_exact &= mgda["anchor_sha256"] == cagrad["anchor_sha256"]
        seat_deltas = [
            float(cagrad["treatment_rewards_bb"][seat])
            - float(mgda["treatment_rewards_bb"][seat])
            for seat in (0, 1)
        ]
        pair_delta = sum(seat_deltas) / 2.0
        pooled.append(pair_delta)
        by_anchor.setdefault(key[0], []).append(pair_delta)
        for seat in (0, 1):
            pooled_seats[seat].append(seat_deltas[seat])

    cagrad_steps = cagrad_summary["treatment_steps"]
    mgda_steps = mgda_summary["treatment_steps"]
    result = {
        "schema": "cardpilot.cagrad_vs_mgda_matched_audit.v1",
        "status": "COMPLETED",
        "mgda_summary_sha256": sha256_path(mgda_dir / "summary.json"),
        "cagrad_summary_sha256": sha256_path(cagrad_dir / "summary.json"),
        "mgda_evidence_sha256": sha256_path(mgda_path),
        "cagrad_evidence_sha256": sha256_path(cagrad_path),
        "matched_contract": {
            "keys_exact": set(mgda_rows) == set(cagrad_rows),
            "decks_exact": decks_exact,
            "controls_exact": controls_exact,
            "anchor_shas_exact": anchor_shas_exact,
            "schedule_logical_sha256_exact": (
                gzip_content_sha256(mgda_dir / "training_schedule.jsonl.gz")
                == gzip_content_sha256(cagrad_dir / "training_schedule.jsonl.gz")
            ),
            "initial_residual_sha256_exact": (
                mgda_summary["initial_residual_sha256"]
                == cagrad_summary["initial_residual_sha256"]
            ),
            "source_training_sha256_exact": (
                mgda_summary["source_training_sha256"]
                == cagrad_summary["source_training_sha256"]
            ),
            "step_count_exact": len(mgda_steps) == len(cagrad_steps) == 32,
        },
        "geometry": {
            "cagrad_positive_worst_alignment_steps": sum(
                row["applied_worst_alignment"] > 0 for row in cagrad_steps
            ),
            "mgda_positive_worst_alignment_steps": sum(
                row["applied_worst_alignment"] > 0 for row in mgda_steps
            ),
            "cagrad_median_ordinary_cosine": float(
                np.median([row["ordinary_applied_cosine"] for row in cagrad_steps])
            ),
            "cagrad_median_norm_ratio": float(
                np.median(
                    [row["applied_to_ordinary_norm_ratio"] for row in cagrad_steps]
                )
            ),
        },
        "cagrad_minus_mgda": {
            "pooled": paired_summary(pooled),
            "anchors": [
                {"anchor_index": index, **paired_summary(values)}
                for index, values in sorted(by_anchor.items())
            ],
            "seats": [
                {"seat": seat, **paired_summary(pooled_seats[seat])}
                for seat in (0, 1)
            ],
        },
    }
    contract_pass = all(result["matched_contract"].values())
    comparisons = result["cagrad_minus_mgda"]
    positive_anchors = sum(row["delta_bb100"] >= 0 for row in comparisons["anchors"])
    result["gates"] = {
        "matched_contract_pass": contract_pass,
        "both_methods_positive_geometry_all_steps": (
            result["geometry"]["cagrad_positive_worst_alignment_steps"] == 32
            and result["geometry"]["mgda_positive_worst_alignment_steps"] == 32
        ),
        "cagrad_retains_mean_cosine_at_least_0p85": (
            result["geometry"]["cagrad_median_ordinary_cosine"] >= 0.85
        ),
        "cagrad_pooled_not_worse_than_mgda": comparisons["pooled"]["delta_bb100"] >= 0,
        "cagrad_nonnegative_on_two_of_three_anchors": positive_anchors >= 2,
        "cagrad_nonnegative_on_both_seats": all(
            row["delta_bb100"] >= 0 for row in comparisons["seats"]
        ),
    }
    result["admitted"] = all(result["gates"].values())
    result["decision"] = (
        "ADMIT_CAGRAD_BROAD_NEW_HAND_CURVE"
        if result["admitted"]
        else "REJECT_CAGRAD_C0P5_MATCHED_RECIPE"
    )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mgda-dir", type=Path, required=True)
    parser.add_argument("--cagrad-dir", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.mgda_dir.resolve(), args.cagrad_dir.resolve())
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
