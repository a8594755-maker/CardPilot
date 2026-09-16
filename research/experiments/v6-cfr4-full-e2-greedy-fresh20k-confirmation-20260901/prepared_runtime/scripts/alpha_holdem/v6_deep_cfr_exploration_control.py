"""Matched exploration control with the SD-CFR snapshot-policy contract."""
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

from alpha_holdem.physical_v6_cfr import (
    PhysicalV6Encoder, TraversalStats, legal_slot_actions, regret_strategy,
    traverse_external_sampling,
)
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, apply_incr
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION
from alpha_holdem.v6_deep_cfr_neural_smoke import _anchor_action, _passive_network
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


@torch.no_grad()
def _policy_strategy(network, state: ChipState) -> np.ndarray:
    encoded = PhysicalV6Encoder.encode(state)
    mask = PhysicalV6Encoder.legal_mask(state)
    values = network(
        torch.from_numpy(encoded).unsqueeze(0),
        torch.from_numpy(mask).unsqueeze(0),
    ).squeeze(0).numpy()
    return regret_strategy(values, mask)


def _snapshot_networks(snapshot_states):
    result = [[], []]
    for player in range(2):
        for state_dict, weight in snapshot_states[player]:
            network = _passive_network()
            network.load_state_dict(state_dict)
            network.eval()
            result[player].append((network, weight))
    return result


def _play_snapshot_hand(snapshot_networks, deck, candidate_seat, anchor, rng):
    choices = snapshot_networks[candidate_seat]
    weights = np.asarray([weight for _, weight in choices], dtype=np.float64)
    selected = int(rng.choice(len(choices), p=weights / weights.sum()))
    candidate_network = choices[selected][0]
    state = ChipState.new(deck)
    movement = []
    while not state.terminal:
        if state.actor == candidate_seat:
            strategy = _policy_strategy(candidate_network, state)
            slot_actions = legal_slot_actions(state)
            slots = np.asarray([slot for slot, _ in slot_actions], dtype=np.int64)
            probabilities = np.asarray([strategy[slot] for slot in slots], dtype=np.float64)
            probabilities /= probabilities.sum()
            action = dict(slot_actions)[int(rng.choice(slots, p=probabilities))]
            movement.append(1.0 - float(strategy[1]))
        else:
            action = _anchor_action(anchor, state, rng)
        state = apply_incr(state, action)
    return state.payoffs()[candidate_seat] / 100.0, movement


def _evaluate(snapshot_states, decks, anchor: str, seed: int) -> dict:
    networks = _snapshot_networks(snapshot_states)
    rng = np.random.default_rng(seed)
    pair_values = []
    movement = []
    for deck in decks:
        first, move0 = _play_snapshot_hand(networks, deck, 0, anchor, rng)
        second, move1 = _play_snapshot_hand(networks, deck, 1, anchor, rng)
        pair_values.append((first + second) / 2.0)
        movement.extend(move0)
        movement.extend(move1)
    values = np.asarray(pair_values, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return {
        "anchor": anchor,
        "pairs": len(decks),
        "hands": 2 * len(decks),
        "candidate_bb100": mean * 100.0,
        "candidate_ci95_bb100": [100.0 * (mean - half), 100.0 * (mean + half)],
        "mean_tv_from_passive": float(np.mean(movement)) if movement else 0.0,
    }


def _run_arm(epsilon, training_decks, eval_decks, args, arm_dir):
    arm_dir.mkdir(parents=True, exist_ok=True)
    networks = _initialize(args.seed)
    buffers = [ReservoirBuffer(500_000), ReservoirBuffer(500_000)]
    snapshots = [[], []]
    iteration_rows = []
    total = TraversalStats()
    for iteration in range(args.iterations):
        collected = []
        for player in range(2):
            stats = TraversalStats()
            values = []
            for root, deck in enumerate(training_decks[iteration]):
                rng = np.random.default_rng(
                    args.seed + iteration * 100_000 + player * 10_000 + root
                )
                root_stats = TraversalStats()
                values.append(traverse_external_sampling(
                    ChipState.new(deck), player, networks, buffers[player],
                    iteration, torch.device("cpu"), rng, root_stats,
                    node_limit=args.node_limit, opponent_exploration=epsilon,
                ))
                _add_stats(stats, root_stats)
            collected.append((stats, values))
        rows = []
        for player in range(2):
            random.seed(args.seed + 5_000_000 + iteration * 100 + player)
            loss = train_advantage_net(
                networks[player], buffers[player], torch.device("cpu"), iteration + 1,
                steps=args.train_steps, batch_size=args.batch_size, lr=args.lr,
                reinit=False, sizing_weight=0.0,
            )
            networks[player].eval()
            snapshots[player].append((
                {key: value.cpu().clone() for key, value in networks[player].state_dict().items()},
                iteration + 1,
            ))
            stats, values = collected[player]
            _add_stats(total, stats)
            rows.append({
                "player": player,
                "loss": float(loss),
                "mean_root_value_bb": float(np.mean(values)),
                "new_traverser_nodes": stats.traverser_nodes,
                "buffer_size": len(buffers[player]),
                "stats": vars(stats),
            })
        nodes = [row["new_traverser_nodes"] for row in rows]
        iteration_rows.append({
            "iteration": iteration + 1,
            "players": rows,
            "log_imbalance": abs(math.log((nodes[0] + 1) / (nodes[1] + 1))),
        })
    checkpoint_path = arm_dir / "snapshot_policy.pt"
    torch.save({
        "schema_version": 1,
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "epsilon": epsilon,
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
        "epsilon": epsilon,
        "iterations": iteration_rows,
        "stats": vars(total),
        "buffer_sizes": [len(buffer) for buffer in buffers],
        "all_seat_iterations_covered": all(
            player["new_traverser_nodes"] > 0
            for row in iteration_rows for player in row["players"]
        ),
        "mean_log_imbalance": float(np.mean([row["log_imbalance"] for row in iteration_rows])),
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
    arms = [
        _run_arm(epsilon, training_decks, eval_decks, args, args.output_dir / f"epsilon_{epsilon:g}")
        for epsilon in args.epsilons
    ]
    control = next(arm for arm in arms if arm["epsilon"] == 0.0)
    treatment = next(arm for arm in arms if arm["epsilon"] == 0.1)
    control_cells = {cell["anchor"]: cell for cell in control["evaluations"]}
    treatment_cells = {cell["anchor"]: cell for cell in treatment["evaluations"]}
    anchors_better = sum(
        treatment_cells[name]["candidate_bb100"] > control_cells[name]["candidate_bb100"]
        for name in control_cells
    )
    gates = {
        "treatment_covers_every_seat_iteration": treatment["all_seat_iterations_covered"],
        "exploration_reduces_imbalance": treatment["mean_log_imbalance"] < control["mean_log_imbalance"],
        "snapshot_mean_not_worse": treatment["anchor_mean_bb100"] >= control["anchor_mean_bb100"],
        "at_least_two_snapshot_anchors_better": anchors_better >= 2,
    }
    result = {
        "schema_version": 1,
        "config": vars(args) | {"output_dir": str(args.output_dir)},
        "common_decks": {"path": str(deck_path), "sha256": _sha256(deck_path)},
        "accounting": {
            "environment_training_hands": args.iterations * args.traversals_per_player * 2 * len(arms),
            "evaluation_hands": args.eval_pairs * 2 * 3 * len(arms),
        },
        "arms": arms,
        "comparison": {
            "anchors_better_for_epsilon_0_1": anchors_better,
            "anchor_mean_delta_bb100": treatment["anchor_mean_bb100"] - control["anchor_mean_bb100"],
            "imbalance_delta": treatment["mean_log_imbalance"] - control["mean_log_imbalance"],
        },
        "gates": gates,
        "admit_exploration_snapshot_trainer": all(gates.values()),
        "decision": (
            "ADMIT_EXPLORATION_SNAPSHOT_TRAINER"
            if all(gates.values()) else "REJECT_EPSILON_0_1_AS_SUFFICIENT"
        ),
    }
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=128)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--epsilons", type=float, nargs="+", default=[0.0, 0.1])
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60906)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if sorted(args.epsilons) != [0.0, 0.1]:
        raise ValueError("This matched control requires exactly epsilon 0 and 0.1")
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
