"""Matched paper-MSE/LCFR versus repository surrogate loss control."""
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
from deep_cfr.train import _reinit_weights, train_advantage_net


def train_paper_loss(network, buffer, max_iteration, steps, batch_size, lr):
    """Brown et al. value objective: fresh net, masked MSE, LCFR weights."""
    _reinit_weights(network)
    network.train()
    optimizer = torch.optim.Adam(network.parameters(), lr=lr)
    losses = []
    for _ in range(steps):
        indices = random.sample(range(len(buffer.buffer)), min(batch_size, len(buffer.buffer)))
        states = torch.from_numpy(np.stack([buffer.buffer[i].state for i in indices]))
        targets = torch.from_numpy(np.stack([buffer.buffer[i].advantages for i in indices]))
        masks = torch.from_numpy(np.stack([buffer.buffer[i].legal_mask for i in indices]))
        weights = torch.tensor([
            buffer.buffer[i].iteration / max(max_iteration, 1) for i in indices
        ], dtype=torch.float32)
        predictions = network(states, masks)
        per_sample = (((predictions - targets) ** 2) * masks).sum(-1)
        loss = (per_sample * weights).mean()
        optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(network.parameters(), 1.0)
        optimizer.step()
        losses.append(float(loss.item()))
    network.eval()
    return float(np.mean(losses))


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
            values = []
            for root, deck in enumerate(training_decks[iteration]):
                rng = np.random.default_rng(args.seed + iteration * 100_000 + player * 10_000 + root)
                root_stats = TraversalStats()
                values.append(traverse_external_sampling(
                    ChipState.new(deck), player, networks, buffers[player], iteration,
                    torch.device("cpu"), rng, root_stats, node_limit=args.node_limit,
                    opponent_exploration=0.0,
                ))
                _add_stats(stats, root_stats)
            random.seed(args.seed + 5_000_000 + iteration * 100 + player)
            torch.manual_seed(args.seed + 6_000_000 + iteration * 100 + player)
            if mode == "paper":
                loss = train_paper_loss(
                    networks[player], buffers[player], iteration + 1,
                    args.train_steps, args.batch_size, args.lr,
                )
            else:
                loss = train_advantage_net(
                    networks[player], buffers[player], torch.device("cpu"), iteration + 1,
                    steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
                    reinit=True, sizing_weight=0.0,
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
                "mean_root_value_bb": float(np.mean(values)),
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
        "loss_contract": mode,
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
    surrogate = _run_arm("surrogate", training_decks, eval_decks, args, args.output_dir / "surrogate")
    paper = _run_arm("paper", training_decks, eval_decks, args, args.output_dir / "paper")
    surrogate_cells = {cell["anchor"]: cell for cell in surrogate["evaluations"]}
    paper_cells = {cell["anchor"]: cell for cell in paper["evaluations"]}
    anchors_better = sum(
        paper_cells[name]["candidate_bb100"] > surrogate_cells[name]["candidate_bb100"]
        for name in surrogate_cells
    )
    gates = {
        "identical_initial_weights": surrogate["initial_sha256"] == paper["initial_sha256"],
        "paper_covers_every_seat_iteration": paper["all_seat_iterations_covered"],
        "paper_snapshot_mean_better": paper["anchor_mean_bb100"] > surrogate["anchor_mean_bb100"],
        "at_least_two_paper_anchors_better": anchors_better >= 2,
        "paper_losses_finite": all(
            np.isfinite(player["loss"])
            for row in paper["iterations"] for player in row["players"]
        ),
    }
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "common_decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "accounting": {
            "environment_training_hands": args.iterations * args.traversals_per_player * 2 * 2,
            "evaluation_hands": args.eval_pairs * 2 * 3 * 2,
        },
        "arms": {"surrogate": surrogate, "paper": paper},
        "comparison": {
            "anchors_better_for_paper": anchors_better,
            "anchor_mean_delta_bb100": paper["anchor_mean_bb100"] - surrogate["anchor_mean_bb100"],
            "imbalance_delta": paper["mean_log_imbalance"] - surrogate["mean_log_imbalance"],
        },
        "gates": gates,
        "admit_paper_loss": all(gates.values()),
        "decision": "ADMIT_PAPER_MSE_LCFR_LOSS" if all(gates.values()) else "REJECT_PAPER_LOSS_AT_BOUNDED_BUDGET",
    }
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--traversals-per-player", type=int, default=4)
    parser.add_argument("--train-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60909)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
