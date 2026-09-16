"""Bounded Standard10-prior residual-regret mechanism smoke."""
from __future__ import annotations

import argparse
import gzip
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

from alpha_holdem.legacy_observation_bridge_v6 import decide as legacy_decide, load_policy
from alpha_holdem.physical_v6_cfr import (
    PhysicalV6Encoder,
    TraversalStats,
    legal_slot_actions,
    prior_residual_strategy,
    traverse_external_sampling,
)
from alpha_holdem.policy_contract_v6 import CONTRACT_VERSION, apply_incr
from alpha_holdem.rules_v6 import ChipState, RULES_VERSION
from alpha_holdem.v6_deep_cfr_neural_smoke import _anchor_action
from deep_cfr.networks import AdvantageNetwork
from deep_cfr.reservoir import ReservoirBuffer
from deep_cfr.train import train_advantage_net


EXPECTED_STANDARD10_SHA = "91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zero_residual_network() -> AdvantageNetwork:
    network = AdvantageNetwork(max_actions=9, hidden_dims=(64, 64))
    with torch.no_grad():
        network.adv_head[2].weight.zero_()
        network.adv_head[2].bias.zero_()
        network.val_head[2].weight.zero_()
        network.val_head[2].bias.zero_()
    network.eval()
    return network


def _base(policy, state: ChipState) -> tuple[np.ndarray, int]:
    _, metadata = legacy_decide(policy, state, uniform=0.5, policy_mode="greedy")
    return (
        np.asarray(metadata["model_probs"], dtype=np.float32),
        int(metadata["greedy_action_slot"]),
    )


def _provider(policy, residual_scale: float):
    def strategy(state: ChipState, residuals: np.ndarray, mask: np.ndarray) -> np.ndarray:
        base, _ = _base(policy, state)
        return prior_residual_strategy(base, residuals, mask, residual_scale)

    return strategy


@torch.no_grad()
def _residuals(network: AdvantageNetwork, state: ChipState) -> np.ndarray:
    encoded = PhysicalV6Encoder.encode(state)
    mask = PhysicalV6Encoder.legal_mask(state)
    return network(
        torch.from_numpy(encoded).unsqueeze(0),
        torch.from_numpy(mask).unsqueeze(0),
    ).squeeze(0).cpu().numpy()


def _zero_parity(policy, decks: list[list[int]], residual_scale: float) -> dict:
    network = _zero_residual_network()
    checked = mismatches = 0
    max_abs_error = 0.0
    for deck in decks:
        state = ChipState.new(deck)
        while not state.terminal:
            base, base_slot = _base(policy, state)
            mask = PhysicalV6Encoder.legal_mask(state)
            combined = prior_residual_strategy(
                base, _residuals(network, state), mask, residual_scale
            )
            max_abs_error = max(max_abs_error, float(np.max(np.abs(base - combined))))
            mismatches += int(int(np.argmax(combined)) != base_slot)
            checked += 1
            action, _ = legacy_decide(policy, state, uniform=0.5, policy_mode="greedy")
            state = apply_incr(state, action)
    return {
        "states": checked,
        "greedy_mismatches": mismatches,
        "max_probability_abs_error": max_abs_error,
    }


def _snapshot_networks(snapshot_states):
    result = [[], []]
    for player in range(2):
        for state_dict, weight in snapshot_states[player]:
            network = _zero_residual_network()
            network.load_state_dict(state_dict)
            network.eval()
            result[player].append((network, weight))
    return result


def _ensemble_strategy(networks, policy, state: ChipState, residual_scale: float) -> np.ndarray:
    base, _ = _base(policy, state)
    mask = PhysicalV6Encoder.legal_mask(state)
    weighted = np.zeros(9, dtype=np.float64)
    total = 0.0
    for network, weight in networks[state.actor]:
        weighted += float(weight) * prior_residual_strategy(
            base, _residuals(network, state), mask, residual_scale
        )
        total += float(weight)
    return (weighted / total).astype(np.float32)


def _candidate_action(networks, policy, state, residual_scale, movement):
    strategy = _ensemble_strategy(networks, policy, state, residual_scale)
    _, base_slot = _base(policy, state)
    slot = int(np.argmax(strategy))
    movement["decisions"] += 1
    movement["greedy_disagreements"] += int(slot != base_slot)
    return dict(legal_slot_actions(state))[slot]


def _play(networks, policy, deck, candidate_seat, anchor, treatment, residual_scale, rng, movement):
    state = ChipState.new(deck)
    while not state.terminal:
        if state.actor == candidate_seat:
            if treatment:
                action = _candidate_action(
                    networks, policy, state, residual_scale, movement
                )
            else:
                action, _ = legacy_decide(
                    policy, state, uniform=0.5, policy_mode="greedy"
                )
        elif anchor == "standard10":
            action, _ = legacy_decide(policy, state, uniform=0.5, policy_mode="greedy")
        else:
            action = _anchor_action(anchor, state, rng)
        state = apply_incr(state, action)
    return state.payoffs()[candidate_seat] / 100.0


def _evaluate(networks, policy, decks, anchor, residual_scale, seed, raw_stream):
    deltas = []
    candidate_values = []
    base_values = []
    movement = {"decisions": 0, "greedy_disagreements": 0}
    for pair_index, deck in enumerate(decks):
        candidate_pair = []
        base_pair = []
        for seat in range(2):
            candidate_rng = np.random.default_rng(seed + pair_index * 10 + seat)
            base_rng = np.random.default_rng(seed + pair_index * 10 + seat)
            candidate_pair.append(_play(
                networks, policy, deck, seat, anchor, True, residual_scale,
                candidate_rng, movement,
            ))
            base_pair.append(_play(
                networks, policy, deck, seat, anchor, False, residual_scale,
                base_rng, movement,
            ))
        candidate_mean = float(np.mean(candidate_pair))
        base_mean = float(np.mean(base_pair))
        delta = candidate_mean - base_mean
        deltas.append(delta)
        candidate_values.append(candidate_mean)
        base_values.append(base_mean)
        raw_stream.write(json.dumps({
            "anchor": anchor,
            "pair_index": pair_index,
            "deck": deck,
            "candidate_rewards_bb": candidate_pair,
            "base_rewards_bb": base_pair,
            "paired_delta_bb": delta,
        }, separators=(",", ":")) + "\n")
    values = np.asarray(deltas, dtype=np.float64)
    mean = float(values.mean())
    half = float(1.96 * values.std(ddof=1) / math.sqrt(len(values)))
    return {
        "anchor": anchor,
        "pairs": len(decks),
        "hands_per_policy": 2 * len(decks),
        "candidate_bb100": 100.0 * float(np.mean(candidate_values)),
        "base_bb100": 100.0 * float(np.mean(base_values)),
        "paired_delta_bb100": 100.0 * mean,
        "paired_ci95_bb100": [100.0 * (mean - half), 100.0 * (mean + half)],
        "candidate_decisions": movement["decisions"],
        "greedy_disagreement_from_base": (
            movement["greedy_disagreements"] / max(movement["decisions"], 1)
        ),
    }


def run(args):
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise FileExistsError(f"refusing to overwrite nonempty {args.output_dir}")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.time()
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    policy = load_policy(args.standard10, "cpu")
    if policy.sha256 != EXPECTED_STANDARD10_SHA:
        raise ValueError(f"Standard10 hash mismatch: {policy.sha256}")
    deck_rng = np.random.default_rng(args.seed + 1_000_000)
    training_decks = [
        [deck_rng.permutation(52).tolist() for _ in range(args.traversals_per_player)]
        for _ in range(args.iterations)
    ]
    eval_decks = [deck_rng.permutation(52).tolist() for _ in range(args.eval_pairs)]
    parity = _zero_parity(policy, eval_decks[:64], args.residual_scale)
    networks = [_zero_residual_network(), _zero_residual_network()]
    buffers = [ReservoirBuffer(500_000), ReservoirBuffer(500_000)]
    snapshots = [[], []]
    rows = []
    total_stats = TraversalStats()
    provider = _provider(policy, args.residual_scale)
    for iteration in range(args.iterations):
        player_rows = []
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
                    node_limit=args.node_limit, opponent_exploration=0.0,
                    strategy_provider=provider,
                ))
                for name in (
                    "decision_nodes", "traverser_nodes", "sampled_opponent_nodes",
                    "terminal_rollouts",
                ):
                    setattr(stats, name, getattr(stats, name) + getattr(root_stats, name))
                    setattr(total_stats, name, getattr(total_stats, name) + getattr(root_stats, name))
                stats.max_depth = max(stats.max_depth, root_stats.max_depth)
                total_stats.max_depth = max(total_stats.max_depth, root_stats.max_depth)
            random.seed(args.seed + 5_000_000 + iteration * 100 + player)
            torch.manual_seed(args.seed + 6_000_000 + iteration * 100 + player)
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
            player_rows.append({
                "player": player,
                "loss": float(loss),
                "mean_root_value_bb": float(np.mean(values)),
                "new_traverser_nodes": stats.traverser_nodes,
                "buffer_size": len(buffers[player]),
                "stats": vars(stats),
            })
        rows.append({"iteration": iteration + 1, "players": player_rows})
    checkpoint_path = args.output_dir / "residual_policy.pt"
    torch.save({
        "schema_version": 1,
        "algorithm": "standard10_prior_external_sampling_residual_regret",
        "rules_version": RULES_VERSION,
        "policy_contract": CONTRACT_VERSION,
        "source_checkpoint": str(args.standard10),
        "source_sha256": policy.sha256,
        "residual_scale": args.residual_scale,
        "strategy_buffer_0": snapshots[0],
        "strategy_buffer_1": snapshots[1],
    }, checkpoint_path)
    reloaded = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
    loaded_networks = _snapshot_networks([
        reloaded["strategy_buffer_0"], reloaded["strategy_buffer_1"]
    ])
    raw_path = args.output_dir / "paired_evaluation.jsonl.gz"
    with gzip.open(raw_path, "wt", encoding="utf-8") as stream:
        evaluations = [
            _evaluate(
                loaded_networks, policy, eval_decks, anchor, args.residual_scale,
                args.seed + 7_000_000 + index * 100_000, stream,
            )
            for index, anchor in enumerate(
                ("standard10", "call_station", "uniform", "min_bet")
            )
        ]
    positive = sum(cell["paired_delta_bb100"] > 0 for cell in evaluations)
    standard10_cell = evaluations[0]
    gates = {
        "zero_residual_probability_parity": parity["max_probability_abs_error"] < 1e-6,
        "zero_residual_greedy_parity": parity["greedy_mismatches"] == 0,
        "all_seat_iterations_covered": all(
            player["new_traverser_nodes"] > 0 for row in rows for player in row["players"]
        ),
        "finite_positive_losses": all(
            math.isfinite(player["loss"]) and player["loss"] > 0
            for row in rows for player in row["players"]
        ),
        "learned_state_conditioned_movement": max(
            cell["greedy_disagreement_from_base"] for cell in evaluations
        ) > 0,
        "standard10_anchor_point_positive": standard10_cell["paired_delta_bb100"] > 0,
        "at_least_three_anchor_points_positive": positive >= 3,
    }
    result = {
        "schema_version": 1,
        "config": vars(args) | {"standard10": str(args.standard10), "output_dir": str(args.output_dir)},
        "contracts": {
            "base": "physical_v6_legacy_v4_bridge_greedy_v1",
            "candidate": "physical_v6_standard10_prior_lcfr_residual_ensemble_greedy_v1",
        },
        "source": {"path": str(args.standard10), "sha256": policy.sha256},
        "accounting": {
            "environment_training_hands": args.iterations * args.traversals_per_player * 2,
            "evaluation_hands": args.eval_pairs * 2 * 4 * 2,
            "decision_nodes": total_stats.decision_nodes,
            "terminal_rollouts": total_stats.terminal_rollouts,
        },
        "zero_residual_parity": parity,
        "training": {"iterations": rows, "stats": vars(total_stats)},
        "checkpoint": {
            "path": str(checkpoint_path),
            "sha256": _sha256(checkpoint_path),
            "reload_exact": True,
        },
        "raw_evaluation": {"path": str(raw_path), "sha256": _sha256(raw_path)},
        "evaluations": evaluations,
        "positive_anchor_points": positive,
        "gates": gates,
        "elapsed_seconds": time.time() - started,
    }
    result["admit_larger_control"] = all(gates.values())
    result["decision"] = (
        "ADMIT_STANDARD10_RESIDUAL_REGRET_CONTROL"
        if result["admit_larger_control"]
        else "REJECT_OR_REVISE_STANDARD10_RESIDUAL_REGRET_SMOKE"
    )
    (args.output_dir / "summary.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--standard10", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=2)
    parser.add_argument("--traversals-per-player", type=int, default=2)
    parser.add_argument("--train-steps", type=int, default=512)
    parser.add_argument("--batch-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=0.001)
    parser.add_argument("--residual-scale", type=float, default=1.0)
    parser.add_argument("--eval-pairs", type=int, default=256)
    parser.add_argument("--node-limit", type=int, default=250_000)
    parser.add_argument("--seed", type=int, default=60911)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    torch.set_num_threads(1)
    print(json.dumps(run(args), indent=2))


if __name__ == "__main__":
    main()
