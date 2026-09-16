"""External-sampling CFR primitives over the canonical physical-v6 engine.

The module intentionally depends on ``ChipState`` and the shared nine-slot
``action_table`` instead of maintaining another poker rules implementation.
Only public state and the acting player's private cards enter the information
set encoding.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import torch

from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import BB, ChipState
from deep_cfr.hand_eval import combo_index
from deep_cfr.reservoir import AdvantageSample, ReservoirBuffer


MAX_ACTIONS = 9
RAW_DIM = 56
MAX_HISTORY_ACTIONS = 12


class PhysicalV6Encoder:
    """Encode one exact-v6 information set into the legacy 56D network shell."""

    RAW_DIM = RAW_DIM

    @staticmethod
    def encode(state: ChipState) -> np.ndarray:
        if state.terminal:
            raise ValueError("Cannot encode a terminal state")
        player = state.actor
        opponent = 1 - player
        features = np.zeros(RAW_DIM, dtype=np.float32)
        features[0] = float(combo_index(*state.holes[player]))
        features[1:6] = -1.0
        for index, card in enumerate(state.board):
            features[1 + index] = float(card)

        offset = 6
        features[offset + state.street] = 1.0
        offset += 4
        features[offset + player] = 1.0
        offset += 2

        total_chips = float(sum(state.initial))
        to_call = float(state.to_call)
        features[offset + 0] = state.pot / total_chips
        features[offset + 1] = to_call / total_chips
        features[offset + 2] = min(state.stacks[player] / max(state.pot, 1), 10.0) / 10.0
        features[offset + 3] = to_call / max(state.pot + to_call, 1.0)
        offset += 4

        features[offset + 0] = state.stacks[player] / state.initial[player]
        features[offset + 1] = state.stacks[opponent] / state.initial[opponent]
        offset += 2

        history = state.history[-MAX_HISTORY_ACTIONS:]
        action_code = {"f": 0.0, "k": 0.2, "c": 0.4}
        for index, event in enumerate(history):
            base = offset + index * 3
            features[base] = 0.0 if event.player == player else 1.0
            features[base + 1] = (
                0.8 if event.is_raise else 0.6
            ) if event.kind == "b" else action_code[event.kind]
            features[base + 2] = event.amount / total_chips
        offset += MAX_HISTORY_ACTIONS * 3

        street_raises = sum(
            event.kind == "b" and event.street == state.street for event in state.history
        )
        features[offset] = min(street_raises, 12) / 12.0
        features[offset + 1] = state.last_full_raise / max(state.initial[player], 1)
        return features

    @staticmethod
    def legal_mask(state: ChipState) -> np.ndarray:
        mask, _ = action_table(state)
        return mask.astype(np.float32, copy=False)


def legal_slot_actions(state: ChipState) -> list[tuple[int, str]]:
    """Return the canonical, unique physical actions in slot order."""
    _, table = action_table(state)
    return [(slot, action) for slot, action in enumerate(table) if action is not None]


def regret_strategy(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    """Deep-CFR regret matching with the paper's least-negative fallback."""
    positive = np.maximum(advantages, 0.0) * legal_mask
    if positive.sum() > 0:
        return positive / positive.sum()
    masked = np.where(legal_mask > 0, advantages, -np.inf)
    result = np.zeros(MAX_ACTIONS, dtype=np.float32)
    result[int(np.argmax(masked))] = 1.0
    return result


def exploration_strategy(
    strategy: np.ndarray, legal_mask: np.ndarray, epsilon: float,
) -> np.ndarray:
    """Mix a current strategy with uniform legal exploration."""
    if not 0.0 <= epsilon <= 1.0:
        raise ValueError("epsilon must be in [0, 1]")
    legal_count = float(legal_mask.sum())
    if legal_count <= 0:
        raise ValueError("at least one legal action is required")
    uniform = legal_mask / legal_count
    return (1.0 - epsilon) * strategy + epsilon * uniform


def prior_residual_strategy(
    base_strategy: np.ndarray,
    residuals: np.ndarray,
    legal_mask: np.ndarray,
    residual_scale: float = 1.0,
) -> np.ndarray:
    """Apply learned state-conditioned residuals to a frozen policy prior.

    The prior is represented as action probabilities.  Adding a residual in
    log-probability space makes an all-zero residual reproduce the prior
    exactly, including its greedy action, while still allowing every legal
    action with non-zero prior support to move.
    """
    base = np.asarray(base_strategy, dtype=np.float64)
    residual = np.asarray(residuals, dtype=np.float64)
    mask = np.asarray(legal_mask, dtype=np.float64)
    if base.shape != (MAX_ACTIONS,) or residual.shape != (MAX_ACTIONS,) or mask.shape != (MAX_ACTIONS,):
        raise ValueError("base strategy, residuals, and legal mask must all have shape (9,)")
    if not np.isfinite(residual_scale) or residual_scale < 0:
        raise ValueError("residual_scale must be finite and non-negative")
    legal = mask > 0
    if not legal.any():
        raise ValueError("at least one legal action is required")
    if not np.isfinite(base[legal]).all() or (base[legal] < 0).any():
        raise ValueError("legal prior probabilities must be finite and non-negative")
    if not np.isfinite(residual[legal]).all():
        raise ValueError("legal residuals must be finite")
    legal_base = base[legal]
    total = float(legal_base.sum())
    if total <= 0:
        raise ValueError("legal prior probability mass must be positive")
    legal_base = legal_base / total
    scores = np.log(np.maximum(legal_base, 1e-12)) + residual_scale * residual[legal]
    scores -= scores.max()
    weights = np.exp(scores)
    weights /= weights.sum()
    result = np.zeros(MAX_ACTIONS, dtype=np.float32)
    result[legal] = weights.astype(np.float32)
    return result


@dataclass
class TraversalStats:
    decision_nodes: int = 0
    traverser_nodes: int = 0
    sampled_opponent_nodes: int = 0
    terminal_rollouts: int = 0
    max_depth: int = 0


def traverse_external_sampling(
    state: ChipState,
    traverser: int,
    advantage_networks: list[torch.nn.Module],
    advantage_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    rng: np.random.Generator,
    stats: TraversalStats,
    depth: int = 0,
    node_limit: int | None = None,
    opponent_exploration: float = 0.0,
    strategy_provider: Callable[[ChipState, np.ndarray, np.ndarray], np.ndarray] | None = None,
) -> float:
    """Run one exact-deal external-sampling traversal; return payoff in BB."""
    stats.max_depth = max(stats.max_depth, depth)
    if state.terminal:
        stats.terminal_rollouts += 1
        return state.payoffs()[traverser] / BB

    if node_limit is not None and stats.decision_nodes >= node_limit:
        raise RuntimeError(
            f"Traversal exceeded hard decision-node limit {node_limit}; target discarded"
        )
    stats.decision_nodes += 1
    encoded = PhysicalV6Encoder.encode(state)
    legal_mask = PhysicalV6Encoder.legal_mask(state)
    slot_actions = legal_slot_actions(state)
    network = advantage_networks[state.actor]
    with torch.inference_mode():
        values = network(
            torch.from_numpy(encoded).unsqueeze(0).to(device),
            torch.from_numpy(legal_mask).unsqueeze(0).to(device),
        ).squeeze(0).cpu().numpy()
    strategy = (
        regret_strategy(values, legal_mask)
        if strategy_provider is None
        else np.asarray(strategy_provider(state, values, legal_mask), dtype=np.float32)
    )
    if strategy.shape != (MAX_ACTIONS,):
        raise ValueError("strategy provider must return shape (9,)")
    if not np.isfinite(strategy).all() or (strategy < 0).any():
        raise ValueError("strategy provider returned invalid probabilities")
    if np.any(strategy[legal_mask <= 0] != 0):
        raise ValueError("strategy provider assigned probability to an illegal action")
    if not np.isclose(float(strategy.sum()), 1.0, atol=1e-6):
        raise ValueError("strategy provider probabilities must sum to one")

    if state.actor == traverser:
        stats.traverser_nodes += 1
        action_values = np.zeros(MAX_ACTIONS, dtype=np.float32)
        for slot, action in slot_actions:
            action_values[slot] = traverse_external_sampling(
                apply_incr(state, action), traverser, advantage_networks,
                advantage_buffer, iteration, device, rng, stats, depth + 1,
                node_limit, opponent_exploration, strategy_provider,
            )
        expected_value = float(np.dot(strategy, action_values))
        instantaneous = (action_values - expected_value) * legal_mask
        advantage_buffer.add(AdvantageSample(
            state=encoded,
            advantages=instantaneous,
            legal_mask=legal_mask,
            iteration=iteration + 1,
            sizing_target=-1.0,
        ))
        return expected_value

    stats.sampled_opponent_nodes += 1
    behavior = exploration_strategy(strategy, legal_mask, opponent_exploration)
    probabilities = np.asarray([behavior[slot] for slot, _ in slot_actions], dtype=np.float64)
    probabilities /= probabilities.sum()
    selected = int(rng.choice(len(slot_actions), p=probabilities))
    return traverse_external_sampling(
        apply_incr(state, slot_actions[selected][1]), traverser,
        advantage_networks, advantage_buffer, iteration, device, rng, stats,
        depth + 1, node_limit, opponent_exploration, strategy_provider,
    )
