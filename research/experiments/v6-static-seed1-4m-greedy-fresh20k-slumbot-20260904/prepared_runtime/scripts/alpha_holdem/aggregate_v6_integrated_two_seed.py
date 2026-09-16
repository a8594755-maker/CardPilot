"""Verify and aggregate two independent 1M integrated-policy training seeds."""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import gzip
import hashlib
import json
import math
from pathlib import Path
import statistics


EXPECTED_ANCHORS = {"standard10", "cfr4", "legacy_iter16", "legacy_mixed65k"}
T95_DF1 = 12.706204736432095


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


def parse_named_path(spec: str) -> tuple[str, Path]:
    name, separator, raw_path = spec.partition("=")
    if not separator or not name or not raw_path:
        raise argparse.ArgumentTypeError("expected NAME=PATH")
    return name, Path(raw_path).resolve()


def mean_ci95_bb100(values_bb: list[float]) -> tuple[float, float]:
    mean = statistics.fmean(values_bb)
    half = 1.96 * statistics.stdev(values_bb) / math.sqrt(len(values_bb))
    return mean * 100.0, half * 100.0


def seed_t95(values_bb100: list[float]) -> dict:
    mean = statistics.fmean(values_bb100)
    half = T95_DF1 * statistics.stdev(values_bb100) / math.sqrt(len(values_bb100))
    return {
        "values_bb100": values_bb100,
        "mean_bb100": mean,
        "student_t95_half_bb100": half,
        "student_t95_low_bb100": mean - half,
        "student_t95_high_bb100": mean + half,
        "student_t_df": 1,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seed",
        action="append",
        required=True,
        metavar="NAME=AGGREGATE_JSON",
        help="One verified per-seed aggregate; specify exactly twice.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--promote-decision",
        default="SCALE_UNCHANGED_INTEGRATED_RECIPE",
    )
    parser.add_argument(
        "--reject-decision",
        default="HOLD_UNCHANGED_SCALE_AND_DIAGNOSE_BREADTH",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)

    seed_specs = [parse_named_path(spec) for spec in args.seed]
    if len(seed_specs) != 2 or len({name for name, _ in seed_specs}) != 2:
        parser.error("--seed must provide exactly two unique names")

    seed_results = []
    all_pair_deltas: list[float] = []
    all_seat_deltas: list[list[float]] = [[], []]
    all_anchor_deltas: dict[str, list[float]] = defaultdict(list)
    aggregate_hashes: set[str] = set()
    eval_seeds: set[int] = set()
    treatment_hashes: set[str] = set()

    for name, aggregate_path in seed_specs:
        aggregate = load_json(aggregate_path)
        raw_artifact = aggregate["artifacts"]["eval_raw"]
        summary_artifact = aggregate["artifacts"]["eval_summary"]
        raw_path = Path(raw_artifact["path"])
        summary_path = Path(summary_artifact["path"])
        raw = load_gzip_jsonl(raw_path)
        summary = load_json(summary_path)

        pair_keys = [(row["anchor"], int(row["pair_index"])) for row in raw]
        anchor_counts = Counter(row["anchor"] for row in raw)
        deltas = [float(row["treatment_minus_control_pair_mean_bb"]) for row in raw]
        seat_deltas = [
            [float(row["treatment_minus_control_rewards_bb"][seat]) for row in raw]
            for seat in (0, 1)
        ]
        anchor_deltas: dict[str, list[float]] = defaultdict(list)
        decks_valid = True
        for row in raw:
            anchor_deltas[row["anchor"]].append(
                float(row["treatment_minus_control_pair_mean_bb"])
            )
            deck = [int(card) for card in row["deck"]]
            decks_valid &= len(deck) == 52 and sorted(deck) == list(range(52))

        pooled_bb100, pooled_half = mean_ci95_bb100(deltas)
        pooled_seats = [mean_ci95_bb100(values) for values in seat_deltas]
        aggregate_anchor = {row["anchor"]: row for row in aggregate["anchor_slopes"]}
        recomputed_anchors = {
            anchor: mean_ci95_bb100(values) for anchor, values in anchor_deltas.items()
        }
        raw_gates = {
            "per_seed_evidence_gates_passed": all(aggregate["evidence_gates"].values()),
            "raw_artifact_hash_exact": sha256_path(raw_path) == raw_artifact["sha256"],
            "summary_artifact_hash_exact": (
                sha256_path(summary_path) == summary_artifact["sha256"]
            ),
            "row_count_exact": len(raw) == 16_384,
            "anchor_counts_exact": (
                set(anchor_counts) == EXPECTED_ANCHORS
                and set(anchor_counts.values()) == {4_096}
            ),
            "pair_keys_unique": len(pair_keys) == len(set(pair_keys)),
            "pair_indices_complete": all(
                sorted(
                    int(row["pair_index"])
                    for row in raw
                    if row["anchor"] == anchor
                )
                == list(range(4_096))
                for anchor in EXPECTED_ANCHORS
            ),
            "decks_are_complete_permutations": decks_valid,
            "pooled_delta_recomputed": math.isclose(
                pooled_bb100,
                float(aggregate["pooled_slope_bb100"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            "pooled_ci_recomputed": math.isclose(
                pooled_half,
                float(aggregate["pooled_slope_ci95_half_bb100"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            ),
            "seat_deltas_recomputed": all(
                math.isclose(
                    pooled_seats[seat][0],
                    float(aggregate["pooled_seat_slopes"][seat]["delta_bb100"]),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                for seat in (0, 1)
            ),
            "anchor_deltas_recomputed": all(
                math.isclose(
                    recomputed_anchors[anchor][0],
                    float(aggregate_anchor[anchor]["delta_bb100"]),
                    rel_tol=0.0,
                    abs_tol=1e-12,
                )
                for anchor in EXPECTED_ANCHORS
            ),
            "evaluation_hands_exact": int(summary["evaluation_hands"]) == 65_536,
            "preservation_passed": bool(
                aggregate["research_gates"]["standard10_preservation_passed"]
            ),
        }
        all_pair_deltas.extend(deltas)
        for seat in (0, 1):
            all_seat_deltas[seat].extend(seat_deltas[seat])
        for anchor, values in anchor_deltas.items():
            all_anchor_deltas[anchor].extend(values)

        aggregate_sha = sha256_path(aggregate_path)
        aggregate_hashes.add(aggregate_sha)
        eval_seeds.add(int(summary["anchors"][0]["seed"]))
        treatment_hashes.add(summary["input_sha256"]["treatment"])
        seed_results.append(
            {
                "name": name,
                "aggregate": {"path": str(aggregate_path), "sha256": aggregate_sha},
                "training_environment_hands": aggregate["training_environment_hands"],
                "pooled_slope_bb100": pooled_bb100,
                "pooled_slope_ci95_half_bb100": pooled_half,
                "seat_slopes_bb100": [row[0] for row in pooled_seats],
                "anchor_slopes_bb100": {
                    anchor: recomputed_anchors[anchor][0]
                    for anchor in sorted(EXPECTED_ANCHORS)
                },
                "nonnegative_anchor_count": sum(
                    recomputed_anchors[anchor][0] >= 0.0
                    for anchor in EXPECTED_ANCHORS
                ),
                "per_seed_promote": bool(aggregate["promote"]),
                "raw_gates": raw_gates,
                "passed": all(raw_gates.values()),
            }
        )

    seed_slopes = [row["pooled_slope_bb100"] for row in seed_results]
    seed_seats = [
        seed_t95([row["seat_slopes_bb100"][seat] for row in seed_results])
        for seat in (0, 1)
    ]
    seed_anchors = {
        anchor: seed_t95(
            [row["anchor_slopes_bb100"][anchor] for row in seed_results]
        )
        for anchor in sorted(EXPECTED_ANCHORS)
    }
    pair_mean, pair_half = mean_ci95_bb100(all_pair_deltas)
    pair_seats = [mean_ci95_bb100(values) for values in all_seat_deltas]
    pair_anchors = {
        anchor: mean_ci95_bb100(values)
        for anchor, values in sorted(all_anchor_deltas.items())
    }
    gates = {
        "all_raw_evidence_recomputed": all(row["passed"] for row in seed_results),
        "independent_aggregate_artifacts": len(aggregate_hashes) == 2,
        "independent_evaluation_seeds": len(eval_seeds) == 2,
        "independent_treatment_checkpoints": len(treatment_hashes) == 2,
        "both_seed_slopes_positive": all(value > 0.0 for value in seed_slopes),
        "both_seed_breadth_gates_passed": all(
            row["per_seed_promote"] for row in seed_results
        ),
        "both_cross_seed_seat_means_nonnegative": all(
            row["mean_bb100"] >= 0.0 for row in seed_seats
        ),
        "cross_seed_standard10_mean_nonnegative": (
            seed_anchors["standard10"]["mean_bb100"] >= 0.0
        ),
    }
    promote = all(gates.values())
    output = {
        "schema": "cardpilot.integrated_alphaholdem_two_seed_aggregate.v1",
        "seed_results": seed_results,
        "seed_slope_summary": seed_t95(seed_slopes),
        "seed_seat_summaries": [
            {"seat": seat, **row} for seat, row in enumerate(seed_seats)
        ],
        "seed_anchor_summaries": seed_anchors,
        "all_pair_summary": {
            "pairs": len(all_pair_deltas),
            "evaluation_hands": len(all_pair_deltas) * 4,
            "delta_bb100": pair_mean,
            "ci95_half_bb100": pair_half,
            "seat_deltas": [
                {"seat": seat, "delta_bb100": row[0], "ci95_half_bb100": row[1]}
                for seat, row in enumerate(pair_seats)
            ],
            "anchor_deltas": {
                anchor: {"delta_bb100": row[0], "ci95_half_bb100": row[1]}
                for anchor, row in pair_anchors.items()
            },
        },
        "gates": gates,
        "promote": promote,
        "decision": args.promote_decision if promote else args.reject_decision,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not all(row["passed"] for row in seed_results):
        raise SystemExit(2)
    if not promote:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
