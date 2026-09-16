"""Small iterative exact-v6 neural-regret pilot with complete snapshots."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import TraversalStats, traverse_external_sampling
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION
from alpha_holdem.v6_deep_cfr_neural_smoke import _evaluate, _passive_network
from deep_cfr.networks import StrategyBuffer
from deep_cfr.reservoir import ReservoirBuffer
from deep_cfr.train import train_advantage_net


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _buffer_state(buffer: ReservoirBuffer) -> dict:
    return {
        "max_size": buffer.max_size,
        "n_seen": buffer.n_seen,
        "max_iteration": buffer._max_iteration,
        "samples": buffer.buffer,
    }


def _checkpoint(
    path: Path, iteration: int, networks, buffers, strategies,
    traversal_rng: np.random.Generator, config: dict,
) -> str:
    torch.save({
        "schema_version": 1,
        "algorithm": "external_sampling_neural_regret",
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "encoder": "PhysicalV6Encoder56_v1",
        "max_actions": 9,
        "hidden_dims": [64, 64],
        "iteration": iteration,
        "config": config,
        "optimizer_regimen": "fresh_adam_cosine_per_player_iteration",
        "net_0": networks[0].state_dict(),
        "net_1": networks[1].state_dict(),
        "buffer_0": _buffer_state(buffers[0]),
        "buffer_1": _buffer_state(buffers[1]),
        "strategy_buffer_0": strategies[0].networks,
        "strategy_buffer_1": strategies[1].networks,
        "python_random_state": random.getstate(),
        "numpy_legacy_state": np.random.get_state(),
        "traversal_rng_state": traversal_rng.bit_generator.state,
        "torch_rng_state": torch.get_rng_state(),
    }, path)
    return _sha256(path)


def _load_networks(path: Path):
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    networks = [_passive_network(), _passive_network()]
    for player in range(2):
        networks[player].load_state_dict(checkpoint[f"net_{player}"])
        networks[player].eval()
    return checkpoint, networks


def run(args: argparse.Namespace) -> dict:
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = torch.device("cpu")
    networks = [_passive_network(), _passive_network()]
    buffers = [ReservoirBuffer(500_000), ReservoirBuffer(500_000)]
    strategies = [StrategyBuffer(), StrategyBuffer()]
    config = {
        "iterations": args.iterations,
        "traversals_per_player": args.traversals_per_player,
        "train_steps": args.train_steps,
        "batch_size": args.batch_size,
        "lr": args.lr,
        "node_limit": args.node_limit,
        "seed": args.seed,
    }
    checkpoints = []
    initial_path = args.output_dir / "checkpoint_iter0.pt"
    checkpoints.append({"iteration": 0, "path": str(initial_path), "sha256": _checkpoint(
        initial_path, 0, networks, buffers, strategies, rng, config,
    )})
    metrics_path = args.output_dir / "metrics.jsonl"
    total_stats = TraversalStats()
    root_traversals = 0
    metrics = []
    started = time.time()

    for iteration in range(args.iterations):
        row = {"iteration": iteration + 1, "players": []}
        for player in range(2):
            player_stats = TraversalStats()
            root_values = []
            for _ in range(args.traversals_per_player):
                root_stats = TraversalStats()
                root_values.append(traverse_external_sampling(
                    ChipState.new(rng.permutation(52).tolist()), player, networks,
                    buffers[player], iteration, device, rng, root_stats,
                    node_limit=args.node_limit,
                ))
                root_traversals += 1
                for name in ("decision_nodes", "traverser_nodes", "sampled_opponent_nodes", "terminal_rollouts"):
                    setattr(player_stats, name, getattr(player_stats, name) + getattr(root_stats, name))
                    setattr(total_stats, name, getattr(total_stats, name) + getattr(root_stats, name))
                player_stats.max_depth = max(player_stats.max_depth, root_stats.max_depth)
                total_stats.max_depth = max(total_stats.max_depth, root_stats.max_depth)
            random.seed(args.seed + 100_000 * (iteration + 1) + player)
            loss = train_advantage_net(
                networks[player], buffers[player], device, iteration + 1,
                steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
                reinit=False, sizing_weight=0.0,
            )
            networks[player].eval()
            strategies[player].add(networks[player], iteration)
            row["players"].append({
                "player": player,
                "mean_root_value_bb": float(np.mean(root_values)),
                "loss": float(loss),
                "buffer_size": len(buffers[player]),
                "stats": vars(player_stats),
            })
        metrics.append(row)
        with metrics_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")
        checkpoint_path = args.output_dir / f"checkpoint_iter{iteration + 1}.pt"
        checkpoints.append({
            "iteration": iteration + 1,
            "path": str(checkpoint_path),
            "sha256": _checkpoint(
                checkpoint_path, iteration + 1, networks, buffers, strategies,
                rng, config,
            ),
        })

    eval_rng = np.random.default_rng(args.seed + 1_000_000)
    decks = [eval_rng.permutation(52).tolist() for _ in range(args.eval_pairs)]
    evaluations = []
    reload_exact = True
    for checkpoint_row in checkpoints:
        checkpoint, loaded_networks = _load_networks(Path(checkpoint_row["path"]))
        if checkpoint_row["iteration"] == args.iterations:
            reload_exact = all(
                torch.equal(networks[player].state_dict()[key], loaded_networks[player].state_dict()[key])
                for player in range(2) for key in networks[player].state_dict()
            )
        cells = []
        cell = 0
        for anchor in ("call_station", "uniform", "min_bet"):
            for mode in ("sampled", "greedy"):
                cells.append(_evaluate(
                    loaded_networks, decks, anchor, mode,
                    args.seed + 2_000_000 + cell,
                ))
                cell += 1
        evaluations.append({"iteration": checkpoint_row["iteration"], "cells": cells})

    def _mode_map(row, mode):
        return {cell["anchor"]: cell for cell in row["cells"] if cell["mode"] == mode}

    initial_greedy = _mode_map(evaluations[0], "greedy")
    terminal_greedy = _mode_map(evaluations[-1], "greedy")
    anchors_improved = sum(
        terminal_greedy[name]["candidate_bb100"] > initial_greedy[name]["candidate_bb100"]
        for name in initial_greedy
    )
    initial_mean = float(np.mean([row["candidate_bb100"] for row in initial_greedy.values()]))
    terminal_mean = float(np.mean([row["candidate_bb100"] for row in terminal_greedy.values()]))
    terminal_movement = float(np.mean([
        row["argmax_not_passive_fraction"] for row in terminal_greedy.values()
    ]))
    expected_roots = args.iterations * args.traversals_per_player * 2
    expected_eval_hands = (args.iterations + 1) * 3 * 2 * args.eval_pairs * 2
    gates = {
        "planned_roots_complete": root_traversals == expected_roots,
        "checkpoint_reload_exact": reload_exact,
        "finite_losses": all(
            np.isfinite(player["loss"]) for row in metrics for player in row["players"]
        ),
        "terminal_behavior_moved": terminal_movement > 0.05,
        "terminal_greedy_mean_improved": terminal_mean > initial_mean,
        "at_least_two_anchors_improved": anchors_improved >= 2,
        "evaluation_complete": sum(
            cell["hands"] for row in evaluations for cell in row["cells"]
        ) == expected_eval_hands,
    }
    result = {
        "schema_version": 1,
        "config": config | {"eval_pairs": args.eval_pairs},
        "accounting": {
            "environment_training_hands": root_traversals,
            "root_traversals": root_traversals,
            "decision_nodes": total_stats.decision_nodes,
            "terminal_rollouts": total_stats.terminal_rollouts,
            "evaluation_hands": expected_eval_hands,
        },
        "training": {"metrics": metrics, "stats": vars(total_stats), "elapsed_seconds": time.time() - started},
        "checkpoints": checkpoints,
        "evaluations": evaluations,
        "terminal_comparison": {
            "initial_greedy_mean_bb100": initial_mean,
            "terminal_greedy_mean_bb100": terminal_mean,
            "anchors_improved": anchors_improved,
            "terminal_mean_argmax_movement": terminal_movement,
        },
        "gates": gates,
        "admit_larger_pilot": all(gates.values()),
        "decision": (
            "ADMIT_LARGER_EXACT_V6_NEURAL_REGRET_PILOT"
            if all(gates.values()) else "REJECT_ITERATIVE_NEURAL_REGRET_PILOT"
        ),
    }
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=128)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60904)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
