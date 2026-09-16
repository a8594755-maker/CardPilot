"""Independently verify and gate the one-seed 1M integrated deep control."""
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


def mean_ci95_bb100(values_bb: list[float]) -> tuple[float, float]:
    mean = statistics.fmean(values_bb)
    half = 1.96 * statistics.stdev(values_bb) / math.sqrt(len(values_bb))
    return mean * 100.0, half * 100.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-dir", type=Path, required=True)
    parser.add_argument(
        "--training-audit",
        type=Path,
        help="Training-audit JSON (default: <experiment-dir>/training_audit_v2.json).",
    )
    parser.add_argument(
        "--eval-dir",
        type=Path,
        help="Matched-evaluation directory (default: <experiment-dir>/eval_seed1).",
    )
    parser.add_argument(
        "--drift-dir",
        type=Path,
        help="Preservation-audit directory (default: <experiment-dir>/drift_seed1).",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--promote-decision",
        default="REPLICATE_INTEGRATED_RECIPE_TO_1M_SECOND_SEED",
    )
    parser.add_argument(
        "--reject-decision",
        default="CHANGE_INTEGRATED_RECIPE_AFTER_1M_BREADTH_FAILURE",
    )
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)

    root = args.experiment_dir.resolve()
    training_path = (
        args.training_audit.resolve()
        if args.training_audit is not None
        else root / "training_audit_v2.json"
    )
    eval_dir = (
        args.eval_dir.resolve() if args.eval_dir is not None else root / "eval_seed1"
    )
    drift_dir = (
        args.drift_dir.resolve()
        if args.drift_dir is not None
        else root / "drift_seed1"
    )
    summary_path = eval_dir / "summary.json"
    raw_path = eval_dir / "common_deck_pairs.jsonl.gz"
    drift_path = drift_dir / "drift_analysis.json"
    drift_raw_path = drift_dir / "drift_raw.jsonl.gz"
    training = load_json(training_path)
    summary = load_json(summary_path)
    raw = load_gzip_jsonl(raw_path)
    drift = load_json(drift_path)
    drift_raw = load_gzip_jsonl(drift_raw_path)

    pair_keys = [(row["anchor"], int(row["pair_index"])) for row in raw]
    anchor_counts = Counter(row["anchor"] for row in raw)
    anchor_deltas: dict[str, list[float]] = defaultdict(list)
    pooled_deltas: list[float] = []
    seat_deltas: list[list[float]] = [[], []]
    decks_valid = True
    for row in raw:
        delta = float(row["treatment_minus_control_pair_mean_bb"])
        anchor_deltas[row["anchor"]].append(delta)
        pooled_deltas.append(delta)
        for seat in (0, 1):
            seat_deltas[seat].append(
                float(row["treatment_minus_control_rewards_bb"][seat])
            )
        deck = [int(card) for card in row["deck"]]
        decks_valid &= len(deck) == 52 and sorted(deck) == list(range(52))

    pooled_bb100, pooled_ci95 = mean_ci95_bb100(pooled_deltas)
    pooled_seats = [mean_ci95_bb100(values) for values in seat_deltas]
    anchor_rows = []
    for name in sorted(anchor_deltas):
        delta, half = mean_ci95_bb100(anchor_deltas[name])
        anchor_rows.append(
            {"anchor": name, "delta_bb100": delta, "ci95_half_bb100": half}
        )
    summary_anchor = {row["anchor"]: row for row in summary["anchors"]}
    drift_tv = [float(row["tv"]) for row in drift_raw]
    drift_disagreement = [bool(row["greedy_disagreement"]) for row in drift_raw]
    training_run = training["runs"][0]

    evidence_gates = {
        "training_audit_passed": bool(training["passed"]),
        "training_checkpoint_is_treatment": (
            training_run["hashes"]["checkpoint"] == summary["input_sha256"]["treatment"]
        ),
        "training_parent_is_control": (
            training_run["continuation"]["parent_sha256"]
            == summary["input_sha256"]["control"]
        ),
        "eval_raw_sha_exact": sha256_path(raw_path) == summary["raw_pairs_sha256"],
        "eval_row_count_exact": len(raw) == 16_384,
        "eval_anchor_counts_exact": (
            set(anchor_counts) == EXPECTED_ANCHORS
            and set(anchor_counts.values()) == {4_096}
        ),
        "eval_pair_keys_unique": len(pair_keys) == len(set(pair_keys)),
        "eval_pair_indices_complete": all(
            sorted(int(row["pair_index"]) for row in raw if row["anchor"] == anchor)
            == list(range(4_096))
            for anchor in EXPECTED_ANCHORS
        ),
        "decks_are_complete_permutations": decks_valid,
        "eval_hands_exact": int(summary["evaluation_hands"]) == 65_536,
        "pooled_delta_recomputed": math.isclose(
            pooled_bb100,
            float(summary["pooled_treatment_minus_control_bb100"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "pooled_ci_recomputed": math.isclose(
            pooled_ci95,
            float(summary["pooled_treatment_minus_control_ci95_bb100"]),
            rel_tol=0.0,
            abs_tol=1e-12,
        ),
        "seat_deltas_recomputed": all(
            math.isclose(
                pooled_seats[seat][0],
                float(summary["pooled_seat_deltas"][seat]["delta_bb100"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for seat in (0, 1)
        ),
        "anchor_deltas_recomputed": all(
            math.isclose(
                row["delta_bb100"],
                float(summary_anchor[row["anchor"]]["treatment_minus_control_bb100"]),
                rel_tol=0.0,
                abs_tol=1e-12,
            )
            for row in anchor_rows
        ),
        "drift_raw_sha_exact": sha256_path(drift_raw_path) == drift["raw_sha256"],
        "drift_row_count_exact": len(drift_raw) == 20_000,
        "drift_rows_sequential": [int(row["row"]) for row in drift_raw]
        == list(range(20_000)),
        "drift_treatment_is_training_checkpoint": (
            drift["treatment"]["sha256"] == training_run["hashes"]["checkpoint"]
        ),
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
    positive_anchor_count = sum(row["delta_bb100"] >= 0.0 for row in anchor_rows)
    research_gates = {
        "all_evidence_gates_passed": all(evidence_gates.values()),
        "pooled_slope_positive": pooled_bb100 > 0.0,
        "at_least_three_nonnegative_anchors": positive_anchor_count >= 3,
        "both_seats_nonnegative": all(row[0] >= 0.0 for row in pooled_seats),
        "standard10_preservation_passed": (
            drift["status"] == "PASS"
            and statistics.fmean(drift_tv) < 0.03
            and statistics.fmean(drift_disagreement) < 0.05
        ),
    }
    promote = all(research_gates.values())
    output = {
        "schema": "cardpilot.integrated_alphaholdem_deep_control_aggregate.v1",
        "training_environment_hands": training_run["physical_environment_hands"],
        "evaluation_hands": summary["evaluation_hands"],
        "offline_drift_states": len(drift_raw),
        "pooled_slope_bb100": pooled_bb100,
        "pooled_slope_ci95_half_bb100": pooled_ci95,
        "pooled_seat_slopes": [
            {"seat": seat, "delta_bb100": row[0], "ci95_half_bb100": row[1]}
            for seat, row in enumerate(pooled_seats)
        ],
        "anchor_slopes": anchor_rows,
        "nonnegative_anchor_count": positive_anchor_count,
        "drift_mean_tv": statistics.fmean(drift_tv),
        "drift_greedy_disagreement": statistics.fmean(drift_disagreement),
        "evidence_gates": evidence_gates,
        "research_gates": research_gates,
        "promote": promote,
        "decision": args.promote_decision if promote else args.reject_decision,
        "artifacts": {
            "training_audit": {"path": str(training_path), "sha256": sha256_path(training_path)},
            "eval_summary": {"path": str(summary_path), "sha256": sha256_path(summary_path)},
            "eval_raw": {"path": str(raw_path), "sha256": sha256_path(raw_path)},
            "drift_analysis": {"path": str(drift_path), "sha256": sha256_path(drift_path)},
            "drift_raw": {"path": str(drift_raw_path), "sha256": sha256_path(drift_raw_path)},
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps(output, sort_keys=True))
    if not all(evidence_gates.values()):
        raise SystemExit(2)
    if not promote:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
