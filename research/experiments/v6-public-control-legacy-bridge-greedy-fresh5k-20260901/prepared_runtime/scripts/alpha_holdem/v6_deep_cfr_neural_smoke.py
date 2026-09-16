"""Bounded learned-weight smoke for exact-v6 neural regret minimization."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import sys
import time

import numpy as np
import torch

SCRIPTS_ROOT = Path(__file__).resolve().parents[1]
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

from alpha_holdem.physical_v6_cfr import (
    PhysicalV6Encoder,
    TraversalStats,
    legal_slot_actions,
    regret_strategy,
    traverse_external_sampling,
)
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, apply_incr
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION
from deep_cfr.networks import AdvantageNetwork, StrategyBuffer
from deep_cfr.reservoir import ReservoirBuffer
from deep_cfr.train import train_advantage_net


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _passive_network() -> AdvantageNetwork:
    network = AdvantageNetwork(max_actions=9, hidden_dims=(64, 64))
    with torch.no_grad():
        # Retain seeded random hidden features so optimization can learn
        # state-dependent targets; make only the output exactly passive.
        network.adv_head[2].weight.zero_()
        network.adv_head[2].bias.zero_()
        network.adv_head[2].bias[1] = 1.0
        network.val_head[2].weight.zero_()
        network.val_head[2].bias.zero_()
    network.eval()
    return network


@torch.no_grad()
def _strategy(network: AdvantageNetwork, state: ChipState) -> np.ndarray:
    encoded = PhysicalV6Encoder.encode(state)
    mask = PhysicalV6Encoder.legal_mask(state)
    advantages = network(
        torch.from_numpy(encoded).unsqueeze(0),
        torch.from_numpy(mask).unsqueeze(0),
    ).squeeze(0).cpu().numpy()
    return regret_strategy(advantages, mask)


def _candidate_action(
    networks: list[AdvantageNetwork], state: ChipState, mode: str,
    rng: np.random.Generator, movement: dict,
) -> str:
    strategy = _strategy(networks[state.actor], state)
    slot_actions = legal_slot_actions(state)
    slots = np.asarray([slot for slot, _ in slot_actions], dtype=np.int64)
    probabilities = np.asarray([strategy[slot] for slot in slots], dtype=np.float64)
    probabilities /= probabilities.sum()
    argmax_slot = int(slots[int(np.argmax(probabilities))])
    movement["decisions"] += 1
    movement["argmax_not_passive"] += int(argmax_slot != 1)
    movement["tv_from_passive_sum"] += 1.0 - float(strategy[1])
    if mode == "greedy":
        chosen_slot = argmax_slot
    else:
        chosen_slot = int(rng.choice(slots, p=probabilities))
    return dict(slot_actions)[chosen_slot]


def _anchor_action(kind: str, state: ChipState, rng: np.random.Generator) -> str:
    slot_actions = legal_slot_actions(state)
    if kind == "call_station":
        return dict(slot_actions)[1]
    if kind == "min_bet":
        raises = [action for slot, action in slot_actions if 2 <= slot < 8]
        return raises[0] if raises else dict(slot_actions)[1]
    if kind == "uniform":
        return slot_actions[int(rng.integers(len(slot_actions)))][1]
    raise ValueError(f"unknown anchor {kind}")


def _play(
    networks: list[AdvantageNetwork], deck: list[int], candidate_seat: int,
    anchor: str, mode: str, rng: np.random.Generator, movement: dict,
) -> tuple[float, int]:
    state = ChipState.new(deck)
    decisions = 0
    while not state.terminal:
        action = (
            _candidate_action(networks, state, mode, rng, movement)
            if state.actor == candidate_seat
            else _anchor_action(anchor, state, rng)
        )
        state = apply_incr(state, action)
        decisions += 1
    return state.payoffs()[candidate_seat] / 100.0, decisions


def _evaluate(
    networks: list[AdvantageNetwork], decks: list[list[int]], anchor: str,
    mode: str, seed: int,
) -> dict:
    rng = np.random.default_rng(seed)
    pairs = []
    movement = {"decisions": 0, "argmax_not_passive": 0, "tv_from_passive_sum": 0.0}
    decisions = 0
    for deck in decks:
        first, d0 = _play(networks, deck, 0, anchor, mode, rng, movement)
        second, d1 = _play(networks, deck, 1, anchor, mode, rng, movement)
        pairs.append((first + second) / 2.0)
        decisions += d0 + d1
    values = np.asarray(pairs, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return {
        "anchor": anchor,
        "mode": mode,
        "pairs": len(decks),
        "hands": 2 * len(decks),
        "candidate_bb100": mean * 100.0,
        "candidate_ci95_bb100": [100.0 * (mean - half), 100.0 * (mean + half)],
        "decisions": decisions,
        "candidate_decisions": movement["decisions"],
        "argmax_not_passive_fraction": (
            movement["argmax_not_passive"] / max(movement["decisions"], 1)
        ),
        "mean_tv_from_passive": (
            movement["tv_from_passive_sum"] / max(movement["decisions"], 1)
        ),
    }


def run(args: argparse.Namespace) -> dict:
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    rng = np.random.default_rng(args.seed)
    device = torch.device("cpu")
    networks = [_passive_network().to(device), _passive_network().to(device)]
    buffers = [ReservoirBuffer(200_000), ReservoirBuffer(200_000)]
    strategies = [StrategyBuffer(), StrategyBuffer()]
    metrics = []
    total_stats = TraversalStats()
    root_traversals = 0
    started = time.time()

    metrics_path = args.output_dir / "metrics.jsonl"
    for iteration in range(args.iterations):
        row = {"iteration": iteration + 1, "players": []}
        for player in range(2):
            player_stats = TraversalStats()
            values = []
            for _ in range(args.traversals_per_player):
                deck = rng.permutation(52).tolist()
                root_stats = TraversalStats()
                values.append(traverse_external_sampling(
                    ChipState.new(deck), player, networks, buffers[player],
                    iteration, device, rng, root_stats, node_limit=args.node_limit,
                ))
                root_traversals += 1
                for name in ("decision_nodes", "traverser_nodes", "sampled_opponent_nodes", "terminal_rollouts"):
                    setattr(player_stats, name, getattr(player_stats, name) + getattr(root_stats, name))
                    setattr(total_stats, name, getattr(total_stats, name) + getattr(root_stats, name))
                player_stats.max_depth = max(player_stats.max_depth, root_stats.max_depth)
                total_stats.max_depth = max(total_stats.max_depth, root_stats.max_depth)
            loss = train_advantage_net(
                networks[player], buffers[player], device, iteration + 1,
                steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
                reinit=False, sizing_weight=0.0,
            )
            networks[player].eval()
            strategies[player].add(networks[player], iteration)
            row["players"].append({
                "player": player,
                "mean_root_value_bb": float(np.mean(values)),
                "loss": float(loss),
                "buffer_size": len(buffers[player]),
                "stats": vars(player_stats),
            })
        metrics.append(row)
        with metrics_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row) + "\n")

    checkpoint = {
        "schema_version": 1,
        "algorithm": "external_sampling_neural_regret",
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "starting_stack_bb": 200,
        "max_actions": 9,
        "encoder": "PhysicalV6Encoder56_v1",
        "hidden_dims": [64, 64],
        "iterations": args.iterations,
        "root_traversals": root_traversals,
        "net_0": networks[0].state_dict(),
        "net_1": networks[1].state_dict(),
        "strategy_buffer_0": strategies[0].networks,
        "strategy_buffer_1": strategies[1].networks,
    }
    checkpoint_path = args.output_dir / "checkpoint.pt"
    torch.save(checkpoint, checkpoint_path)

    loaded = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    reloaded = [_passive_network(), _passive_network()]
    for player in range(2):
        reloaded[player].load_state_dict(loaded[f"net_{player}"])
        reloaded[player].eval()
    reload_exact = all(
        torch.equal(networks[p].state_dict()[key], reloaded[p].state_dict()[key])
        for p in range(2) for key in networks[p].state_dict()
    )

    eval_rng = np.random.default_rng(args.seed + 1_000_000)
    decks = [eval_rng.permutation(52).tolist() for _ in range(args.eval_pairs)]
    evaluations = []
    cell = 0
    for anchor in ("call_station", "uniform"):
        for mode in ("sampled", "greedy"):
            evaluations.append(_evaluate(
                reloaded, decks, anchor, mode, args.seed + 2_000_000 + cell,
            ))
            cell += 1

    losses = [p["loss"] for row in metrics for p in row["players"]]
    movement = max(row["argmax_not_passive_fraction"] for row in evaluations)
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "accounting": {
            "root_traversals": root_traversals,
            "environment_training_hands": root_traversals,
            "decision_nodes": total_stats.decision_nodes,
            "terminal_rollouts": total_stats.terminal_rollouts,
            "evaluation_hands": sum(row["hands"] for row in evaluations),
        },
        "training": {
            "metrics": metrics,
            "buffer_sizes": [len(buffer) for buffer in buffers],
            "stats": vars(total_stats),
            "elapsed_seconds": time.time() - started,
        },
        "checkpoint": {
            "path": str(checkpoint_path),
            "sha256": _sha256(checkpoint_path),
            "reload_exact": reload_exact,
        },
        "evaluations": evaluations,
        "gates": {
            "planned_root_traversals_complete": root_traversals == args.iterations * args.traversals_per_player * 2,
            "finite_positive_losses": all(math.isfinite(loss) and loss > 0 for loss in losses),
            "both_buffers_nonempty": all(len(buffer) > 0 for buffer in buffers),
            "checkpoint_reload_exact": reload_exact,
            "behavior_moved_from_passive": movement > 0.05,
            "evaluation_complete": sum(row["hands"] for row in evaluations) == args.eval_pairs * 2 * 4,
        },
    }
    result["admit_larger_pilot"] = all(result["gates"].values())
    result["decision"] = (
        "ADMIT_EXACT_V6_NEURAL_REGRET_PILOT"
        if result["admit_larger_pilot"]
        else "REJECT_OR_REVISE_EXACT_V6_NEURAL_REGRET_SMOKE"
    )
    summary_path = args.output_dir / "summary.json"
    summary_path.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=32)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60902)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    result = run(args)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
