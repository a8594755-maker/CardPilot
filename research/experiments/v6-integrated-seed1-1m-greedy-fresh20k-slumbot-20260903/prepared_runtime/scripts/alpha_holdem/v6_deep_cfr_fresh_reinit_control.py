"""Matched warm-versus-fresh advantage-network Deep CFR control."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
import random
import sys

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import TraversalStats, traverse_external_sampling
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION
from alpha_holdem.v6_deep_cfr_exploration_control import (
    _add_stats, _evaluate, _initialize, _sha256,
)
from deep_cfr.reservoir import ReservoirBuffer
from deep_cfr.train import train_advantage_net


def _run_arm(mode, training_decks, eval_decks, args, arm_dir):
    arm_dir.mkdir(parents=True, exist_ok=True)
    networks = _initialize(args.seed)
    buffers = [ReservoirBuffer(500_000), ReservoirBuffer(500_000)]
    snapshots = [[], []]
    initial_path = arm_dir / "initial.pt"
    torch.save({"net_0": networks[0].state_dict(), "net_1": networks[1].state_dict()}, initial_path)
    rows = []
    total = TraversalStats()
    for iteration in range(args.iterations):
        player_rows = []
        for player in range(2):
            stats = TraversalStats()
            root_values = []
            for root, deck in enumerate(training_decks[iteration]):
                rng = np.random.default_rng(
                    args.seed + iteration * 100_000 + player * 10_000 + root
                )
                root_stats = TraversalStats()
                root_values.append(traverse_external_sampling(
                    ChipState.new(deck), player, networks, buffers[player],
                    iteration, torch.device("cpu"), rng, root_stats,
                    node_limit=args.node_limit, opponent_exploration=0.0,
                ))
                _add_stats(stats, root_stats)
            random.seed(args.seed + 5_000_000 + iteration * 100 + player)
            torch.manual_seed(args.seed + 6_000_000 + iteration * 100 + player)
            loss = train_advantage_net(
                networks[player], buffers[player], torch.device("cpu"), iteration + 1,
                steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
                reinit=(mode == "fresh"), sizing_weight=0.0,
            )
            networks[player].eval()
            snapshots[player].append((
                {key: value.cpu().clone() for key, value in networks[player].state_dict().items()},
                iteration + 1,
            ))
            _add_stats(total, stats)
            player_rows.append({
                "player": player,
                "loss": float(loss),
                "mean_root_value_bb": float(np.mean(root_values)),
                "new_traverser_nodes": stats.traverser_nodes,
                "buffer_size": len(buffers[player]),
                "stats": vars(stats),
            })
        nodes = [row["new_traverser_nodes"] for row in player_rows]
        rows.append({
            "iteration": iteration + 1,
            "players": player_rows,
            "log_imbalance": abs(math.log((nodes[0] + 1) / (nodes[1] + 1))),
        })
    checkpoint_path = arm_dir / "snapshot_policy.pt"
    torch.save({
        "schema_version": 1,
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "mode": mode,
        "strategy_buffer_0": snapshots[0],
        "strategy_buffer_1": snapshots[1],
        "buffer_0": buffers[0].buffer,
        "buffer_1": buffers[1].buffer,
    }, checkpoint_path)
    cells = [
        _evaluate(snapshots, eval_decks, anchor, args.seed + 7_000_000 + index)
        for index, anchor in enumerate(("call_station", "uniform", "min_bet"))
    ]
    return {
        "mode": mode,
        "initial_sha256": _sha256(initial_path),
        "iterations": rows,
        "stats": vars(total),
        "buffer_sizes": [len(buffer) for buffer in buffers],
        "all_seat_iterations_covered": all(
            player["new_traverser_nodes"] > 0 for row in rows for player in row["players"]
        ),
        "mean_log_imbalance": float(np.mean([row["log_imbalance"] for row in rows])),
        "checkpoint": str(checkpoint_path),
        "checkpoint_sha256": _sha256(checkpoint_path),
        "evaluations": cells,
        "anchor_mean_bb100": float(np.mean([cell["candidate_bb100"] for cell in cells])),
    }


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    deck_rng = np.random.default_rng(args.seed + 1_000_000)
    training_decks = [
        [deck_rng.permutation(52).tolist() for _ in range(args.traversals_per_player)]
        for _ in range(args.iterations)
    ]
    eval_decks = [deck_rng.permutation(52).tolist() for _ in range(args.eval_pairs)]
    deck_path = args.output_dir / "common_decks.json"
    deck_path.write_text(json.dumps({"training": training_decks, "evaluation": eval_decks}) + "\n")
    warm = _run_arm("warm", training_decks, eval_decks, args, args.output_dir / "warm")
    fresh = _run_arm("fresh", training_decks, eval_decks, args, args.output_dir / "fresh")
    warm_cells = {cell["anchor"]: cell for cell in warm["evaluations"]}
    fresh_cells = {cell["anchor"]: cell for cell in fresh["evaluations"]}
    anchors_better = sum(
        fresh_cells[name]["candidate_bb100"] > warm_cells[name]["candidate_bb100"]
        for name in warm_cells
    )
    gates = {
        "identical_initial_weights": warm["initial_sha256"] == fresh["initial_sha256"],
        "fresh_covers_every_seat_iteration": fresh["all_seat_iterations_covered"],
        "fresh_snapshot_mean_better": fresh["anchor_mean_bb100"] > warm["anchor_mean_bb100"],
        "at_least_two_fresh_anchors_better": anchors_better >= 2,
    }
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "common_decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "accounting": {
            "environment_training_hands": args.iterations * args.traversals_per_player * 2 * 2,
            "evaluation_hands": args.eval_pairs * 2 * 3 * 2,
        },
        "arms": {"warm": warm, "fresh": fresh},
        "comparison": {
            "anchors_better_for_fresh": anchors_better,
            "anchor_mean_delta_bb100": fresh["anchor_mean_bb100"] - warm["anchor_mean_bb100"],
            "imbalance_delta": fresh["mean_log_imbalance"] - warm["mean_log_imbalance"],
        },
        "gates": gates,
        "admit_fresh_reinit": all(gates.values()),
        "decision": (
            "ADMIT_PAPER_FRESH_REINIT"
            if all(gates.values()) else "REJECT_FRESH_REINIT_AT_BOUNDED_BUDGET"
        ),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60907)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
