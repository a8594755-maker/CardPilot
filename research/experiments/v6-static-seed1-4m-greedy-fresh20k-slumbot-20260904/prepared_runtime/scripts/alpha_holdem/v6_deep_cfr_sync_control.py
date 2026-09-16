"""Matched simultaneous-versus-sequential exact-v6 CFR update control."""
from __future__ import annotations

import argparse
import hashlib
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
from alpha_holdem.v6_deep_cfr_neural_smoke import _evaluate, _passive_network
from deep_cfr.reservoir import ReservoirBuffer
from deep_cfr.train import train_advantage_net


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _add_stats(target: TraversalStats, source: TraversalStats) -> None:
    for name in ("decision_nodes", "traverser_nodes", "sampled_opponent_nodes", "terminal_rollouts"):
        setattr(target, name, getattr(target, name) + getattr(source, name))
    target.max_depth = max(target.max_depth, source.max_depth)


def _initialize(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    return [_passive_network(), _passive_network()]


def _collect_player(
    networks, buffer, player: int, iteration: int, decks: list[list[int]],
    seed: int, node_limit: int,
) -> tuple[TraversalStats, list[float]]:
    stats = TraversalStats()
    values = []
    for root, deck in enumerate(decks):
        rng = np.random.default_rng(seed + iteration * 100_000 + player * 10_000 + root)
        root_stats = TraversalStats()
        values.append(traverse_external_sampling(
            ChipState.new(deck), player, networks, buffer, iteration,
            torch.device("cpu"), rng, root_stats, node_limit=node_limit,
        ))
        _add_stats(stats, root_stats)
    return stats, values


def _train_player(network, buffer, player: int, iteration: int, args) -> float:
    random.seed(args.seed + 5_000_000 + iteration * 100 + player)
    loss = train_advantage_net(
        network, buffer, torch.device("cpu"), iteration + 1,
        steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
        reinit=False, sizing_weight=0.0,
    )
    network.eval()
    return float(loss)


def _run_arm(mode: str, training_decks, eval_decks, args, arm_dir: Path) -> dict:
    arm_dir.mkdir(parents=True, exist_ok=True)
    networks = _initialize(args.seed)
    buffers = [ReservoirBuffer(500_000), ReservoirBuffer(500_000)]
    initial_path = arm_dir / "initial.pt"
    torch.save({"net_0": networks[0].state_dict(), "net_1": networks[1].state_dict()}, initial_path)
    iterations = []
    total = TraversalStats()
    for iteration in range(args.iterations):
        rows = [None, None]
        if mode == "sequential":
            for player in range(2):
                stats, values = _collect_player(
                    networks, buffers[player], player, iteration,
                    training_decks[iteration], args.seed, args.node_limit,
                )
                loss = _train_player(networks[player], buffers[player], player, iteration, args)
                rows[player] = {
                    "player": player, "loss": loss,
                    "mean_root_value_bb": float(np.mean(values)),
                    "buffer_size": len(buffers[player]), "stats": vars(stats),
                }
                _add_stats(total, stats)
        elif mode == "synchronized":
            collected = []
            for player in range(2):
                collected.append(_collect_player(
                    networks, buffers[player], player, iteration,
                    training_decks[iteration], args.seed, args.node_limit,
                ))
            for player in range(2):
                stats, values = collected[player]
                loss = _train_player(networks[player], buffers[player], player, iteration, args)
                rows[player] = {
                    "player": player, "loss": loss,
                    "mean_root_value_bb": float(np.mean(values)),
                    "buffer_size": len(buffers[player]), "stats": vars(stats),
                }
                _add_stats(total, stats)
        else:
            raise ValueError(mode)
        nodes = [row["stats"]["traverser_nodes"] for row in rows]
        iterations.append({
            "iteration": iteration + 1,
            "players": rows,
            "traverser_node_log_imbalance": abs(math.log((nodes[0] + 1) / (nodes[1] + 1))),
        })

    checkpoint_path = arm_dir / "terminal.pt"
    torch.save({
        "schema_version": 1,
        "mode": mode,
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "iteration": args.iterations,
        "net_0": networks[0].state_dict(),
        "net_1": networks[1].state_dict(),
        "buffer_0": buffers[0].buffer,
        "buffer_1": buffers[1].buffer,
        "buffer_n_seen": [buffer.n_seen for buffer in buffers],
        "config": {
            "iterations": args.iterations,
            "traversals_per_player": args.traversals_per_player,
            "train_steps": args.train_steps,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "seed": args.seed,
        },
    }, checkpoint_path)
    loaded = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reload_networks = _initialize(args.seed)
    for player in range(2):
        reload_networks[player].load_state_dict(loaded[f"net_{player}"])
        reload_networks[player].eval()
    reload_exact = all(
        torch.equal(networks[player].state_dict()[key], reload_networks[player].state_dict()[key])
        for player in range(2) for key in networks[player].state_dict()
    )
    cells = []
    for cell, anchor in enumerate(("call_station", "uniform", "min_bet")):
        cells.append(_evaluate(
            reload_networks, eval_decks, anchor, "greedy",
            args.seed + 7_000_000 + cell,
        ))
    greedy_mean = float(np.mean([cell["candidate_bb100"] for cell in cells]))
    mean_imbalance = float(np.mean([row["traverser_node_log_imbalance"] for row in iterations]))
    return {
        "mode": mode,
        "initial_sha256": _sha256(initial_path),
        "iterations": iterations,
        "stats": vars(total),
        "buffer_sizes": [len(buffer) for buffer in buffers],
        "terminal_checkpoint": str(checkpoint_path),
        "terminal_sha256": _sha256(checkpoint_path),
        "reload_exact": reload_exact,
        "evaluations": cells,
        "terminal_greedy_mean_bb100": greedy_mean,
        "mean_traverser_node_log_imbalance": mean_imbalance,
    }


def run(args: argparse.Namespace) -> dict:
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
    deck_path.write_text(json.dumps({
        "training": training_decks, "evaluation": eval_decks,
    }) + "\n", encoding="utf-8")
    sequential = _run_arm("sequential", training_decks, eval_decks, args, args.output_dir / "sequential")
    synchronized = _run_arm("synchronized", training_decks, eval_decks, args, args.output_dir / "synchronized")
    seq_cells = {cell["anchor"]: cell for cell in sequential["evaluations"]}
    sync_cells = {cell["anchor"]: cell for cell in synchronized["evaluations"]}
    anchors_improved = sum(
        sync_cells[name]["candidate_bb100"] > seq_cells[name]["candidate_bb100"]
        for name in seq_cells
    )
    gates = {
        "identical_initial_weights": sequential["initial_sha256"] == synchronized["initial_sha256"],
        "both_reload_exact": sequential["reload_exact"] and synchronized["reload_exact"],
        "synchronization_reduces_imbalance": synchronized["mean_traverser_node_log_imbalance"] < sequential["mean_traverser_node_log_imbalance"],
        "synchronized_terminal_mean_better": synchronized["terminal_greedy_mean_bb100"] > sequential["terminal_greedy_mean_bb100"],
        "at_least_two_anchors_better": anchors_improved >= 2,
    }
    result = {
        "schema_version": 1,
        "config": {
            "iterations": args.iterations,
            "traversals_per_player": args.traversals_per_player,
            "train_steps": args.train_steps,
            "batch_size": args.batch_size,
            "lr": args.lr,
            "eval_pairs": args.eval_pairs,
            "node_limit": args.node_limit,
            "seed": args.seed,
        },
        "common_decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "accounting": {
            "environment_training_hands": args.iterations * args.traversals_per_player * 2 * 2,
            "evaluation_hands": args.eval_pairs * 2 * 3 * 2,
        },
        "arms": {"sequential": sequential, "synchronized": synchronized},
        "comparison": {
            "anchors_better_for_synchronized": anchors_improved,
            "greedy_mean_delta_bb100": synchronized["terminal_greedy_mean_bb100"] - sequential["terminal_greedy_mean_bb100"],
            "imbalance_delta": synchronized["mean_traverser_node_log_imbalance"] - sequential["mean_traverser_node_log_imbalance"],
        },
        "gates": gates,
        "admit_synchronized_trainer": all(gates.values()),
        "decision": (
            "ADMIT_SYNCHRONIZED_EXACT_V6_CFR_TRAINER"
            if all(gates.values()) else "REJECT_SYNCHRONIZATION_AS_SUFFICIENT_FIX"
        ),
    }
    (args.output_dir / "summary.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
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
    parser.add_argument("--seed", type=int, default=60905)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
