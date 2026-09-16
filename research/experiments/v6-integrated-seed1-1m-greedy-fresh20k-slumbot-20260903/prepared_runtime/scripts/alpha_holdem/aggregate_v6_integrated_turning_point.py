"""Audit and aggregate shared-deck checkpoints on the 1M-to-2M learning curve."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

import torch


ANCHORS = {"standard10", "cfr4", "legacy_iter16", "legacy_mixed65k"}
SEEDS = ("seed1", "seed2")
STAGES = ("iter256", "iter320", "iter384", "final")


def parse_endpoint(value: str) -> tuple[str, Path]:
    if "=" not in value:
        raise argparse.ArgumentTypeError("endpoint must be SEED:STAGE=DIR")
    name, raw_path = value.split("=", 1)
    if ":" not in name or not raw_path:
        raise argparse.ArgumentTypeError("endpoint must be SEED:STAGE=DIR")
    return name, Path(raw_path)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_rows(path: Path) -> list[dict]:
    with gzip.open(path, "rt", encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def mean_ci95(values: list[float]) -> dict:
    mean = statistics.fmean(values)
    half = 1.96 * statistics.stdev(values) / math.sqrt(len(values))
    return {
        "pairs": len(values),
        "delta_bb100": mean * 100.0,
        "ci95_half_bb100": half * 100.0,
        "ci95_low_bb100": (mean - half) * 100.0,
        "ci95_high_bb100": (mean + half) * 100.0,
    }


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=0.0, abs_tol=1e-12)


def summarize_rows(rows: list[dict], value_key: str) -> dict:
    pooled = mean_ci95([float(row[value_key]) for row in rows])
    pooled["seats"] = [
        {
            "seat": seat,
            **mean_ci95(
                [float(row["seat_values"][seat]) for row in rows]
            ),
        }
        for seat in (0, 1)
    ]
    by_anchor = {}
    for anchor in sorted(ANCHORS):
        anchor_rows = [row for row in rows if row["anchor"] == anchor]
        by_anchor[anchor] = mean_ci95(
            [float(row[value_key]) for row in anchor_rows]
        )
    pooled["anchors"] = by_anchor
    return pooled


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--endpoint", action="append", type=parse_endpoint, required=True
    )
    parser.add_argument(
        "--prior-final", action="append", type=parse_endpoint, default=[]
    )
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    endpoints = dict(args.endpoint)
    expected = {f"{seed}:{stage}" for seed in SEEDS for stage in STAGES}
    if set(endpoints) != expected or len(args.endpoint) != len(expected):
        parser.error(f"endpoint names must be exactly {sorted(expected)}")

    audited = {}
    rows_by_endpoint: dict[str, list[dict]] = {}
    evidence_gates = {}
    for name in sorted(endpoints):
        directory = endpoints[name].resolve()
        summary_path = directory / "summary.json"
        raw_path = directory / "common_deck_pairs.jsonl.gz"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        rows = load_rows(raw_path)
        counts = Counter(row["anchor"] for row in rows)
        keys = [(row["anchor"], int(row["pair_index"])) for row in rows]
        recomputed = mean_ci95(
            [float(row["treatment_minus_control_pair_mean_bb"]) for row in rows]
        )
        recomputed_seats = [
            mean_ci95(
                [
                    float(row["treatment_minus_control_rewards_bb"][seat])
                    for row in rows
                ]
            )
            for seat in (0, 1)
        ]
        checkpoint_path = Path(summary["input_paths"]["treatment"])
        checkpoint = torch.load(
            checkpoint_path, map_location="cpu", weights_only=False
        )
        endpoint_gates = {
            "summary_complete": summary["status"] == "COMPLETED",
            "raw_hash_exact": sha256_path(raw_path) == summary["raw_pairs_sha256"],
            "treatment_hash_exact": (
                sha256_path(checkpoint_path)
                == summary["input_sha256"]["treatment"]
            ),
            "row_count_exact": len(rows) == 8_192,
            "anchor_counts_exact": (
                set(counts) == ANCHORS and set(counts.values()) == {2_048}
            ),
            "pair_keys_unique": len(keys) == len(set(keys)),
            "pair_indices_complete": all(
                sorted(
                    int(row["pair_index"])
                    for row in rows
                    if row["anchor"] == anchor
                )
                == list(range(2_048))
                for anchor in ANCHORS
            ),
            "decks_complete": all(
                sorted(int(card) for card in row["deck"]) == list(range(52))
                for row in rows
            ),
            "pooled_delta_recomputed": close(
                recomputed["delta_bb100"],
                summary["pooled_treatment_minus_control_bb100"],
            ),
            "pooled_ci_recomputed": close(
                recomputed["ci95_half_bb100"],
                summary["pooled_treatment_minus_control_ci95_bb100"],
            ),
            "seat_deltas_recomputed": all(
                close(
                    recomputed_seats[seat]["delta_bb100"],
                    summary["pooled_seat_deltas"][seat]["delta_bb100"],
                )
                for seat in (0, 1)
            ),
        }
        evidence_gates[name] = endpoint_gates
        rows_by_endpoint[name] = rows
        audited[name] = {
            "directory": str(directory),
            "summary_sha256": sha256_path(summary_path),
            "raw_sha256": sha256_path(raw_path),
            "control_sha256": summary["input_sha256"]["control"],
            "treatment_sha256": summary["input_sha256"]["treatment"],
            "evaluation_seed": int(summary["anchors"][0]["seed"]),
            "environment_hands": int(
                checkpoint["environment_hand_accounting"]["completed_hands"]
            ),
            "iteration": int(checkpoint["iteration"]),
            "gates": endpoint_gates,
        }
        del checkpoint

    shared_deck_gates = {}
    for seed in SEEDS:
        reference = rows_by_endpoint[f"{seed}:{STAGES[0]}"]
        reference_identity = [
            (
                row["anchor"],
                int(row["pair_index"]),
                row["deck"],
                row["control_rewards_bb"],
                float(row["control_pair_mean_bb"]),
            )
            for row in reference
        ]
        shared_deck_gates[seed] = {
            "control_checkpoint_shared": len(
                {audited[f"{seed}:{stage}"]["control_sha256"] for stage in STAGES}
            )
            == 1,
            "evaluation_seed_shared": len(
                {audited[f"{seed}:{stage}"]["evaluation_seed"] for stage in STAGES}
            )
            == 1,
            "raw_control_and_decks_shared": all(
                [
                    (
                        row["anchor"],
                        int(row["pair_index"]),
                        row["deck"],
                        row["control_rewards_bb"],
                        float(row["control_pair_mean_bb"]),
                    )
                    for row in rows_by_endpoint[f"{seed}:{stage}"]
                ]
                == reference_identity
                for stage in STAGES[1:]
            ),
            "treatments_distinct": len(
                {
                    audited[f"{seed}:{stage}"]["treatment_sha256"]
                    for stage in STAGES
                }
            )
            == len(STAGES),
            "environment_hands_increasing": [
                audited[f"{seed}:{stage}"]["environment_hands"]
                for stage in STAGES
            ]
            == sorted(
                audited[f"{seed}:{stage}"]["environment_hands"]
                for stage in STAGES
            ),
        }
    independent_seed_gate = (
        audited["seed1:iter256"]["evaluation_seed"]
        != audited["seed2:iter256"]["evaluation_seed"]
    )

    endpoint_summaries = {}
    normalized_rows = {}
    for stage in STAGES:
        combined = []
        for seed in SEEDS:
            normalized = []
            for row in rows_by_endpoint[f"{seed}:{stage}"]:
                normalized.append(
                    {
                        "seed": seed,
                        "anchor": row["anchor"],
                        "pair_index": int(row["pair_index"]),
                        "pair_value": float(
                            row["treatment_minus_control_pair_mean_bb"]
                        ),
                        "seat_values": [
                            float(value)
                            for value in row[
                                "treatment_minus_control_rewards_bb"
                            ]
                        ],
                        "treatment_pair_mean_bb": float(
                            row["treatment_pair_mean_bb"]
                        ),
                        "treatment_rewards_bb": [
                            float(value) for value in row["treatment_rewards_bb"]
                        ],
                    }
                )
            normalized_rows[f"{seed}:{stage}"] = normalized
            combined.extend(normalized)
        endpoint_summaries[stage] = summarize_rows(combined, "pair_value")
        endpoint_summaries[stage]["seed_means_bb100"] = {
            seed: mean_ci95(
                [
                    row["pair_value"]
                    for row in normalized_rows[f"{seed}:{stage}"]
                ]
            )["delta_bb100"]
            for seed in SEEDS
        }
        endpoint_summaries[stage]["mean_environment_hands"] = statistics.fmean(
            audited[f"{seed}:{stage}"]["environment_hands"] for seed in SEEDS
        )

    adjacent_summaries = {}
    previous = "control"
    for stage in STAGES:
        combined = []
        for seed in SEEDS:
            current_rows = normalized_rows[f"{seed}:{stage}"]
            if previous == "control":
                combined.extend(current_rows)
                continue
            previous_rows = normalized_rows[f"{seed}:{previous}"]
            for current, prior in zip(current_rows, previous_rows):
                combined.append(
                    {
                        "seed": seed,
                        "anchor": current["anchor"],
                        "pair_index": current["pair_index"],
                        "pair_value": current["treatment_pair_mean_bb"]
                        - prior["treatment_pair_mean_bb"],
                        "seat_values": [
                            current["treatment_rewards_bb"][seat]
                            - prior["treatment_rewards_bb"][seat]
                            for seat in (0, 1)
                        ],
                    }
                )
        label = f"{previous}_to_{stage}"
        adjacent_summaries[label] = summarize_rows(combined, "pair_value")
        adjacent_summaries[label]["seed_means_bb100"] = {
            seed: mean_ci95(
                [row["pair_value"] for row in combined if row["seed"] == seed]
            )["delta_bb100"]
            for seed in SEEDS
        }
        previous = stage

    prior_final_summary = None
    prior_final_gates = {}
    if args.prior_final:
        prior_finals = dict(args.prior_final)
        expected_prior = {f"{seed}:prior" for seed in SEEDS}
        if set(prior_finals) != expected_prior or len(args.prior_final) != 2:
            parser.error(
                f"prior-final names must be exactly {sorted(expected_prior)}"
            )
        prior_normalized = []
        prior_seeds = set()
        for seed in SEEDS:
            name = f"{seed}:prior"
            directory = prior_finals[name].resolve()
            summary_path = directory / "summary.json"
            raw_path = directory / "common_deck_pairs.jsonl.gz"
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
            rows = load_rows(raw_path)
            counts = Counter(row["anchor"] for row in rows)
            recomputed = mean_ci95(
                [
                    float(row["treatment_minus_control_pair_mean_bb"])
                    for row in rows
                ]
            )
            prior_seed = int(summary["anchors"][0]["seed"])
            prior_seeds.add(prior_seed)
            prior_final_gates[name] = {
                "summary_complete": summary["status"] == "COMPLETED",
                "raw_hash_exact": (
                    sha256_path(raw_path) == summary["raw_pairs_sha256"]
                ),
                "row_count_exact": len(rows) == 16_384,
                "anchor_counts_exact": (
                    set(counts) == ANCHORS and set(counts.values()) == {4_096}
                ),
                "decks_complete": all(
                    sorted(int(card) for card in row["deck"])
                    == list(range(52))
                    for row in rows
                ),
                "pooled_delta_recomputed": close(
                    recomputed["delta_bb100"],
                    summary["pooled_treatment_minus_control_bb100"],
                ),
                "control_matches_current_final": (
                    summary["input_sha256"]["control"]
                    == audited[f"{seed}:final"]["control_sha256"]
                ),
                "treatment_matches_current_final": (
                    summary["input_sha256"]["treatment"]
                    == audited[f"{seed}:final"]["treatment_sha256"]
                ),
                "evaluation_seed_is_fresh": (
                    prior_seed
                    != audited[f"{seed}:final"]["evaluation_seed"]
                ),
            }
            for row in rows:
                prior_normalized.append(
                    {
                        "seed": seed,
                        "anchor": row["anchor"],
                        "pair_index": int(row["pair_index"]),
                        "pair_value": float(
                            row["treatment_minus_control_pair_mean_bb"]
                        ),
                        "seat_values": [
                            float(value)
                            for value in row[
                                "treatment_minus_control_rewards_bb"
                            ]
                        ],
                    }
                )
        prior_final_gates["independent_prior_seeds"] = len(prior_seeds) == 2
        current_final = [
            row
            for seed in SEEDS
            for row in normalized_rows[f"{seed}:final"]
        ]
        combined_final = [*prior_normalized, *current_final]
        prior_final_summary = {
            "prior_cohort": summarize_rows(prior_normalized, "pair_value"),
            "current_cohort": summarize_rows(current_final, "pair_value"),
            "combined": summarize_rows(combined_final, "pair_value"),
            "combined_evaluation_hands": len(combined_final) * 4,
            "cohort_mean_difference_bb100": (
                mean_ci95([row["pair_value"] for row in current_final])[
                    "delta_bb100"
                ]
                - mean_ci95([row["pair_value"] for row in prior_normalized])[
                    "delta_bb100"
                ]
            ),
        }

    empirical_best = max(
        ("control", *STAGES),
        key=lambda stage: (
            0.0 if stage == "control" else endpoint_summaries[stage]["delta_bb100"]
        ),
    )
    confidently_better = [
        stage
        for stage in STAGES
        if endpoint_summaries[stage]["ci95_low_bb100"] > 0.0
    ]
    conservative_choice = (
        max(
            confidently_better,
            key=lambda stage: endpoint_summaries[stage]["ci95_low_bb100"],
        )
        if confidently_better
        else "control"
    )
    all_evidence_passed = (
        all(all(gates.values()) for gates in evidence_gates.values())
        and all(all(gates.values()) for gates in shared_deck_gates.values())
        and independent_seed_gate
        and all(
            all(gates.values()) if isinstance(gates, dict) else bool(gates)
            for gates in prior_final_gates.values()
        )
    )
    output = {
        "schema": "cardpilot.integrated_alphaholdem_turning_point.v1",
        "passed": all_evidence_passed,
        "design": {
            "pairs_per_anchor": 2_048,
            "anchors": sorted(ANCHORS),
            "shared_decks_within_lineage": True,
            "independent_seeds_across_lineages": True,
            "evaluation_hands": len(endpoints) * 32_768,
        },
        "audited_endpoints": audited,
        "evidence_gates": evidence_gates,
        "shared_deck_gates": shared_deck_gates,
        "independent_seed_gate": independent_seed_gate,
        "prior_final_gates": prior_final_gates,
        "combined_final_evidence": prior_final_summary,
        "endpoint_vs_1m": endpoint_summaries,
        "adjacent_intervals": adjacent_summaries,
        "selection": {
            "empirical_best": empirical_best,
            "confidently_better_than_1m": confidently_better,
            "conservative_choice": conservative_choice,
        },
        "command": [sys.executable, *sys.argv],
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(output, sort_keys=True))
    if not all_evidence_passed:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
