#!/usr/bin/env python3
"""Aggregate independent and pooled static current-KL 262k confirmation rows."""

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
    sha256_path,
    summarize_rows,
)


EXPECTED_EVAL_SEEDS = {1: 20263061, 2: 20263062, 3: 20263063}
CONTROL_SHA256 = {
    1: "8b92b254396156d3e65833725e03b2f5ba30ae6aa9906c688b15aa5b856c8238",
    2: "690c2e9e614b8f7f86408c0d8142dd7d3b3a42dcda31df79107068197be658a7",
    3: "ba6effa3ca20cccf371eef6d0ee80f93f7334e2622bc04920c932493d4ec3af9",
}
TREATMENT_SHA256 = {
    1: "1e9cda7fb9793554d767f36957df9c730baab32e1d2cd5f972497ab25d044e43",
    2: "2ac666344ad73b6d4a3a36cdfffed0e5f5cc9b4c8c40b7dc6227a5fc6803d8d6",
    3: "ce9a7ad4769cb1fca56231239866f7a478eef9958416ca53cf8c3e03c6f1c236",
}


def deck_fingerprint(row: dict) -> str:
    payload = json.dumps(row["deck"], separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()


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
    parser.add_argument("--prior-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise FileExistsError(args.out)
    started = time.time()
    root = args.experiment_dir.resolve()
    prior_root = args.prior_dir.resolve()

    integrity: dict[str, bool] = {}
    input_sha256: dict[str, str] = {}
    prior_aggregate_path = prior_root / "aggregate.json"
    prior_aggregate = read_json(prior_aggregate_path)
    input_sha256[str(prior_aggregate_path)] = sha256_path(prior_aggregate_path)
    integrity["prior_aggregate_complete_and_sound"] = (
        prior_aggregate.get("status") == "COMPLETED"
        and all(prior_aggregate.get("integrity", {}).values())
        and int(prior_aggregate.get("evaluation_hands", -1)) == 98304
    )

    fresh_by_seed = {}
    combined_by_seed = {}
    all_fresh_rows = []
    all_combined_rows = []
    first_fresh_decks = []
    total_fresh_hands = 0
    for seed in range(1, 4):
        fresh_dir = root / f"eval_seed{seed}"
        prior_dir = prior_root / f"eval_seed{seed}"
        summary_path = fresh_dir / "summary.json"
        raw_path = fresh_dir / "common_deck_pairs.jsonl.gz"
        prior_raw_path = prior_dir / "common_deck_pairs.jsonl.gz"
        summary = read_json(summary_path)
        fresh_rows = read_rows(raw_path)
        prior_rows = read_rows(prior_raw_path)
        input_sha256[str(summary_path)] = sha256_path(summary_path)
        input_sha256[str(raw_path)] = sha256_path(raw_path)
        input_sha256[str(prior_raw_path)] = sha256_path(prior_raw_path)

        fresh_keys = {
            (str(row["anchor"]), int(row["pair_index"])) for row in fresh_rows
        }
        prior_decks = {
            (str(row["anchor"]), deck_fingerprint(row)) for row in prior_rows
        }
        fresh_decks = {
            (str(row["anchor"]), deck_fingerprint(row)) for row in fresh_rows
        }
        integrity[f"seed{seed}_completed"] = summary.get("status") == "COMPLETED"
        integrity[f"seed{seed}_raw_hash"] = (
            sha256_path(raw_path) == summary.get("raw_pairs_sha256")
        )
        integrity[f"seed{seed}_row_count_unique"] = (
            len(fresh_rows) == len(fresh_keys) == 4096 * len(ANCHORS)
        )
        integrity[f"seed{seed}_accounting"] = (
            int(summary.get("evaluation_hands", -1)) == 65536
            and int(summary.get("pairs_per_anchor", -1)) == 4096
            and int(summary.get("anchor_count", -1)) == len(ANCHORS)
        )
        integrity[f"seed{seed}_anchors"] = (
            tuple(row["anchor"] for row in summary.get("anchors", [])) == ANCHORS
        )
        integrity[f"seed{seed}_eval_seed"] = (
            int(command_value(summary["command"], "--seed"))
            == EXPECTED_EVAL_SEEDS[seed]
        )
        integrity[f"seed{seed}_checkpoint_hashes"] = (
            summary["input_sha256"]["control"] == CONTROL_SHA256[seed]
            and summary["input_sha256"]["treatment"] == TREATMENT_SHA256[seed]
        )
        integrity[f"seed{seed}_fresh_decks_disjoint_from_prior"] = not (
            prior_decks & fresh_decks
        )
        integrity[f"seed{seed}_prior_row_count"] = (
            len(prior_rows) == 2048 * len(ANCHORS)
        )
        fresh_by_seed[str(seed)] = summarize_rows(fresh_rows)
        combined_by_seed[str(seed)] = summarize_rows(prior_rows + fresh_rows)
        all_fresh_rows.extend(fresh_rows)
        all_combined_rows.extend(prior_rows)
        all_combined_rows.extend(fresh_rows)
        first_fresh_decks.append(deck_fingerprint(fresh_rows[0]))
        total_fresh_hands += int(summary["evaluation_hands"])

    integrity["fresh_eval_seeds_unique"] = len(set(EXPECTED_EVAL_SEEDS.values())) == 3
    integrity["fresh_first_decks_unique"] = len(set(first_fresh_decks)) == 3
    fresh_slopes = [fresh_by_seed[str(seed)]["pooled"]["bb100"] for seed in range(1, 4)]
    combined_slopes = [
        combined_by_seed[str(seed)]["pooled"]["bb100"] for seed in range(1, 4)
    ]
    breadth_seeds = [seed for seed in range(1, 4) if breadth(combined_by_seed[str(seed)])]
    collapse_seeds = [seed for seed in range(1, 4) if collapse(fresh_by_seed[str(seed)])]
    mechanics_pass = all(integrity.values())
    gates = {
        "mechanically_sound": mechanics_pass,
        "fresh_positive_at_least_two_seeds": sum(x > 0.0 for x in fresh_slopes) >= 2,
        "fresh_median_positive": statistics.median(fresh_slopes) > 0.0,
        "combined_positive_at_least_two_seeds": (
            sum(x > 0.0 for x in combined_slopes) >= 2
        ),
        "combined_median_positive": statistics.median(combined_slopes) > 0.0,
        "combined_breadth_at_least_two_seeds": len(breadth_seeds) >= 2,
        "all_seed_pooled_combined_positive": (
            summarize_rows(all_combined_rows)["pooled"]["bb100"] > 0.0
        ),
        "no_replicated_fresh_broad_collapse": len(collapse_seeds) < 2,
    }
    promote = all(gates.values())
    clear_reject = (not mechanics_pass) or len(collapse_seeds) >= 2
    if promote:
        decision = "PROMOTE_STATIC_CURRENT_KL_TO_1M_SCALE"
        interpretation = "independent fresh and pooled breadth evidence supports more training"
    elif clear_reject:
        decision = "REJECT_STATIC_CURRENT_KL_SCALE_MECHANISM"
        interpretation = "causal integrity failed or broad reversal independently replicated"
    else:
        decision = "INSUFFICIENT_SCALE_OR_MIXED_DIRECTIONAL_EVIDENCE"
        interpretation = "confirmation remains mixed; do not infer long-horizon method failure"

    result = {
        "schema": "cardpilot.static_current_kl_262k_confirmation_aggregate.v1",
        "status": "COMPLETED",
        "design": {
            "fresh_pairs_per_anchor": 4096,
            "prior_pairs_per_anchor": 2048,
            "anchors": list(ANCHORS),
            "training_seeds": 3,
            "policy_mode": "greedy",
            "evaluation_contract": "untouched_common_deck_both_seats",
            "training_hands": 0,
            "slumbot_hands": 0,
        },
        "fresh_evaluation_hands": total_fresh_hands,
        "pooled_evaluation_hands": total_fresh_hands + 98304,
        "fresh": {
            "combined": summarize_rows(all_fresh_rows),
            "by_seed": fresh_by_seed,
        },
        "prior_plus_fresh": {
            "combined": summarize_rows(all_combined_rows),
            "by_seed": combined_by_seed,
        },
        "integrity": integrity,
        "gates": gates,
        "breadth_qualified_seeds": breadth_seeds,
        "fresh_collapse_seeds": collapse_seeds,
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
