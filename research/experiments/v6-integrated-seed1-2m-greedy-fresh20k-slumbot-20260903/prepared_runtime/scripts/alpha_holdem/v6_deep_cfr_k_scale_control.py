"""Matched traversal-count scale control for exact-v6 Deep CFR."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.v6_deep_cfr_exploration_control import _sha256
from alpha_holdem.v6_deep_cfr_fresh_reinit_control import _run_arm


def _minimum_nodes(arm):
    return min(
        player["new_traverser_nodes"]
        for row in arm["iterations"] for player in row["players"]
    )


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    small_k, large_k = args.k_values
    deck_rng = np.random.default_rng(args.seed + 1_000_000)
    full_training_decks = [
        [deck_rng.permutation(52).tolist() for _ in range(large_k)]
        for _ in range(args.iterations)
    ]
    eval_decks = [deck_rng.permutation(52).tolist() for _ in range(args.eval_pairs)]
    deck_path = args.output_dir / "common_decks.json"
    deck_path.write_text(json.dumps({
        "training": full_training_decks, "evaluation": eval_decks,
        "small_k_prefix": small_k,
    }) + "\n")
    small = _run_arm(
        "fresh", [decks[:small_k] for decks in full_training_decks],
        eval_decks, args, args.output_dir / f"k{small_k}",
    )
    large = _run_arm(
        "fresh", full_training_decks, eval_decks, args,
        args.output_dir / f"k{large_k}",
    )
    small["k"] = small_k
    large["k"] = large_k
    small_cells = {cell["anchor"]: cell for cell in small["evaluations"]}
    large_cells = {cell["anchor"]: cell for cell in large["evaluations"]}
    anchors_better = sum(
        large_cells[name]["candidate_bb100"] >= small_cells[name]["candidate_bb100"]
        for name in small_cells
    )
    gates = {
        "identical_initial_weights": small["initial_sha256"] == large["initial_sha256"],
        "k8_covers_every_seat_iteration": large["all_seat_iterations_covered"],
        "k8_increases_minimum_coverage": _minimum_nodes(large) > _minimum_nodes(small),
        "k8_reduces_mean_imbalance": large["mean_log_imbalance"] < small["mean_log_imbalance"],
        "k8_snapshot_mean_not_worse": large["anchor_mean_bb100"] >= small["anchor_mean_bb100"],
        "at_least_two_k8_anchors_not_worse": anchors_better >= 2,
    }
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "common_decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "accounting": {
            "environment_training_hands": args.iterations * 2 * sum(args.k_values),
            "evaluation_hands": args.eval_pairs * 2 * 3 * 2,
        },
        "arms": {f"k{small_k}": small, f"k{large_k}": large},
        "comparison": {
            "minimum_nodes": {f"k{small_k}": _minimum_nodes(small), f"k{large_k}": _minimum_nodes(large)},
            "anchors_not_worse_for_k8": anchors_better,
            "anchor_mean_delta_bb100": large["anchor_mean_bb100"] - small["anchor_mean_bb100"],
            "imbalance_delta": large["mean_log_imbalance"] - small["mean_log_imbalance"],
        },
        "gates": gates,
        "admit_k8": all(gates.values()),
        "decision": "ADMIT_K8_TRAVERSAL_SCALE" if all(gates.values()) else "REJECT_K8_TRAVERSAL_SCALE",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--k-values", type=int, nargs=2, default=[2, 8])
    parser.add_argument("--train-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60908)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if not 0 < args.k_values[0] < args.k_values[1]:
        raise ValueError("k-values must be strictly increasing positive integers")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
