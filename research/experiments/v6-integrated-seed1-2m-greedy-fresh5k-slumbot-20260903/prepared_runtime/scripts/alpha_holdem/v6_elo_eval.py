"""Exact physical-v6 mirrored evaluation for in-training ELO tournaments.

This module deliberately accepts already-constructed models.  It is used by
``train_v5`` while all competitors share the active run's observation contract,
so it neither loads checkpoints nor consumes rollout RNG/accounting state.
"""
from __future__ import annotations

import math
import random
import time

import numpy as np
import torch

from alpha_holdem.policy_contract_v6 import apply_incr, observation
from alpha_holdem.rules_v6 import ChipState


def _observation(model, state: ChipState, observation_style: str):
    include_position = bool(
        getattr(model, "requires_position_feature", False)
    ) or any(
        int(getattr(model, key, 0)) > 0
        for key in ("position_adapter_hidden", "position_value_adapter_hidden")
    )
    if observation_style == "legacy_v4":
        from alpha_holdem.legacy_observation_bridge_v6 import (
            legacy_observation_from_state,
        )

        return legacy_observation_from_state(
            state, include_position=include_position
        )
    if observation_style != "v6":
        raise ValueError(f"unknown v6 observation style: {observation_style}")
    return observation(state, include_position=include_position)


@torch.no_grad()
def greedy_action(model, state: ChipState, *, observation_style: str, device: str):
    obs, action_table = _observation(model, state, observation_style)
    tensors = [
        torch.as_tensor(
            obs[key], dtype=torch.float32, device=device
        ).unsqueeze(0)
        for key in ("card_info", "action_info", "extra_info", "legal_mask")
    ]
    logits, _ = model(*tensors)
    values = logits[0].detach().cpu().numpy().astype(np.float64)
    legal = np.flatnonzero(obs["legal_mask"])
    if values.shape != (9,) or not len(legal):
        raise ValueError("invalid v6 ELO policy output or legal mask")
    if not np.isfinite(values[legal]).all():
        raise ValueError("non-finite legal logits in v6 ELO tournament")
    slot = int(legal[int(np.argmax(values[legal]))])
    action = action_table[slot]
    if action is None:
        raise ValueError("v6 ELO evaluator selected an empty action slot")
    return action


def _play_hand(
    candidate,
    anchor,
    deck,
    *,
    candidate_seat: int,
    candidate_observation_style: str,
    anchor_observation_style: str,
    device: str,
):
    state = ChipState.new(deck)
    decisions = 0
    while not state.terminal:
        actor_model = candidate if state.actor == candidate_seat else anchor
        actor_observation_style = (
            candidate_observation_style
            if state.actor == candidate_seat
            else anchor_observation_style
        )
        action = greedy_action(
            actor_model,
            state,
            observation_style=actor_observation_style,
            device=device,
        )
        state = apply_incr(state, action)
        decisions += 1
    return float(state.payoffs()[candidate_seat]) / 100.0, decisions


def _mean_ci95(values):
    array = np.asarray(values, dtype=np.float64)
    mean = float(array.mean()) if len(array) else 0.0
    std = float(array.std(ddof=1)) if len(array) > 1 else 0.0
    return mean, 1.96 * std / math.sqrt(max(len(array), 1))


def summarize_models(
    *,
    candidate,
    anchor,
    pairs: int,
    seed: int,
    starting_stack: float,
    device: str,
    observation_style: str | None = None,
    candidate_observation_style: str | None = None,
    anchor_observation_style: str | None = None,
    include_pair_outcomes: bool = False,
):
    """Return the subset of v5 ``summarize_anchor`` used by ELO selection."""
    if int(pairs) <= 0:
        raise ValueError("pairs must be positive")
    if float(starting_stack) != 200.0:
        raise ValueError("physical-v6 ELO requires exactly 200bb")
    if observation_style is not None:
        if candidate_observation_style is not None or anchor_observation_style is not None:
            raise ValueError(
                "observation_style cannot be combined with per-policy styles"
            )
        candidate_observation_style = anchor_observation_style = observation_style
    if candidate_observation_style is None or anchor_observation_style is None:
        raise ValueError(
            "provide observation_style or both per-policy observation styles"
        )
    valid_styles = {"legacy_v4", "v6"}
    if candidate_observation_style not in valid_styles:
        raise ValueError(
            f"unknown candidate observation style: {candidate_observation_style}"
        )
    if anchor_observation_style not in valid_styles:
        raise ValueError(
            f"unknown anchor observation style: {anchor_observation_style}"
        )
    rng = random.Random(int(seed))
    pair_values = []
    pair_records = []
    pair_wins = pair_draws = pair_losses = 0
    total_decisions = 0
    started = time.time()
    for pair_index in range(int(pairs)):
        deck = list(range(52))
        rng.shuffle(deck)
        first, first_decisions = _play_hand(
            candidate,
            anchor,
            deck,
            candidate_seat=0,
            candidate_observation_style=candidate_observation_style,
            anchor_observation_style=anchor_observation_style,
            device=device,
        )
        second, second_decisions = _play_hand(
            candidate,
            anchor,
            deck,
            candidate_seat=1,
            candidate_observation_style=candidate_observation_style,
            anchor_observation_style=anchor_observation_style,
            device=device,
        )
        total = first + second
        pair_values.append(total / 2.0)
        if include_pair_outcomes:
            pair_records.append({
                "pair_index": int(pair_index),
                "deck": list(deck),
                "candidate_rewards_bb": [float(first), float(second)],
                "candidate_pair_mean_bb": float(total / 2.0),
                "decisions": [int(first_decisions), int(second_decisions)],
            })
        total_decisions += first_decisions + second_decisions
        if total > 0.01:
            pair_wins += 1
        elif total < -0.01:
            pair_losses += 1
        else:
            pair_draws += 1
    mean, ci95 = _mean_ci95(pair_values)
    result = {
        "pair_wins": int(pair_wins),
        "pair_draws": int(pair_draws),
        "pair_losses": int(pair_losses),
        "candidate_bb100": float(mean * 100.0),
        "candidate_ci95_bb100": float(ci95 * 100.0),
        "ood_nodes": {"candidate": 0, "anchor": 0},
        "decisions": int(total_decisions),
        "elapsed_seconds": float(time.time() - started),
        "candidate_observation_style": candidate_observation_style,
        "anchor_observation_style": anchor_observation_style,
        "evaluation_contract": (
            f"physical_v6_candidate_{candidate_observation_style}"
            f"_anchor_{anchor_observation_style}_v1"
        ),
    }
    if include_pair_outcomes:
        result["paired_outcomes"] = pair_records
    return result
