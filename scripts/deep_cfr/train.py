"""
SD-CFR (Single Deep CFR) training loop.

Usage:
  # Smoke test on Leduc Hold'em
  python -m scripts.deep_cfr.train --game leduc --iterations 100 --traversals 5000

  # Full HU NL Hold'em
  python -m scripts.deep_cfr.train --game hunl --iterations 200 --traversals 30000

  # Resume from checkpoint
  python -m scripts.deep_cfr.train --game hunl --iterations 200 --resume checkpoints/sdcfr_iter50.pt
"""

from __future__ import annotations

import argparse
import json
import os
import time
from collections import OrderedDict

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from .encoding import (
    HUNLEncoder, LeducEncoder, encode_legal_mask_from_actions, actions_to_slots,
)
from .game_state import (
    HUNLGameState, LeducGameState, GameConfig, Street, ActionType, Action,
    EXPANDED_BET_FRACTIONS,
)
from .networks import (
    AdvantageNetwork, LeducAdvantageNetwork, LeducPolicyNetwork,
    PolicyNetwork, StrategyBuffer,
)
from .reservoir import ReservoirBuffer, AdvantageSample, PolicyBuffer, PolicySample


# ---------- Traversal ----------

def traverse_hunl(
    state: HUNLGameState,
    traverser: int,
    adv_nets: list[AdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    encoder: type = HUNLEncoder,
    max_actions: int = 9,
) -> float:
    """
    External Sampling MCCFR traversal for HU NL Hold'em.
    Returns the expected value for the traverser.

    Args:
        adv_nets: [net_p0, net_p1] — each player's advantage network.
                  Uses the CURRENT PLAYER's network at each node.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    # Use the CURRENT PLAYER's network (not the traverser's)
    current_net = adv_nets[state.current_player]

    # Encode state and get strategy from network
    raw = encoder.encode(state)
    legal_mask = encode_legal_mask_from_actions(actions, max_actions)
    slots = actions_to_slots(actions, max_actions)

    with torch.inference_mode():
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)
        advantages = current_net(raw_t, mask_t).squeeze(0).cpu().numpy()

    # Regret matching to get strategy
    strategy = _regret_match(advantages, legal_mask)

    if state.current_player == traverser:
        # Traverse ALL actions (external sampling — we traverse all of traverser's actions)
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            slot = slots[i]
            child = state.apply(action)
            values[slot] = traverse_hunl(child, traverser, adv_nets, adv_buffer, iteration, device, encoder, max_actions)

        # Compute EV under current strategy
        ev = np.sum(strategy * values)

        # Instantaneous advantages
        inst_advantages = (values - ev) * legal_mask

        # Sizing target
        sizing_target = _compute_sizing_target(actions, slots, inst_advantages, state)

        # Store in buffer
        sample = AdvantageSample(
            state=raw,
            advantages=inst_advantages,
            legal_mask=legal_mask,
            iteration=iteration + 1,
            sizing_target=sizing_target,
        )
        adv_buffer.add(sample)
        return ev

    else:
        # Opponent: sample one action according to strategy
        slot_probs = np.array([strategy[slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)

        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return traverse_hunl(child, traverser, adv_nets, adv_buffer, iteration, device, encoder, max_actions)


def traverse_leduc(
    state: LeducGameState,
    traverser: int,
    adv_nets: list[LeducAdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    max_actions: int = 4,
) -> float:
    """External Sampling MCCFR traversal for Leduc Hold'em.

    Args:
        adv_nets: [net_p0, net_p1] — each player's advantage network.
                  Uses the CURRENT PLAYER's network at each node.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    # Use the CURRENT PLAYER's network (not the traverser's)
    current_net = adv_nets[state.current_player]
    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    with torch.inference_mode():
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)
        advantages = current_net(raw_t, mask_t).squeeze(0).cpu().numpy()

    strategy = _regret_match(advantages, legal_mask)

    # Map Leduc actions to slots
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
    action_slots = [action_slot_map[a] for a in actions]

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            slot = action_slots[i]
            child = state.apply(action)
            values[slot] = traverse_leduc(child, traverser, adv_nets, adv_buffer, iteration, device, max_actions)

        ev = np.sum(strategy * values)
        inst_advantages = (values - ev) * legal_mask

        sample = AdvantageSample(
            state=raw,
            advantages=inst_advantages,
            legal_mask=legal_mask,
            iteration=iteration + 1,  # 1-based for Linear CFR weighting
        )
        adv_buffer.add(sample)
        return ev

    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return traverse_leduc(child, traverser, adv_nets, adv_buffer, iteration, device, max_actions)


# ---------- Coroutine-Based Batched Traversal ----------

def _traverse_leduc_coro(state, traverser, adv_buffer, iteration, max_actions=4):
    """Generator-based traversal. Yields (player, raw, mask) for NN eval.
    Receives advantages via send(). Returns EV via StopIteration.value.

    Uses 'yield from' for recursive sub-generators — send() passes through
    to the innermost yield automatically.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    # YIELD to request batched NN eval — scheduler will batch these
    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
    action_slots = [action_slot_map[a] for a in actions]

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[action_slots[i]] = yield from _traverse_leduc_coro(
                child, traverser, adv_buffer, iteration, max_actions)

        ev = float(np.sum(strategy * values))
        inst_advantages = (values - ev) * legal_mask
        adv_buffer.add(AdvantageSample(
            state=raw, advantages=inst_advantages,
            legal_mask=legal_mask, iteration=iteration + 1))
        return ev
    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return (yield from _traverse_leduc_coro(
            child, traverser, adv_buffer, iteration, max_actions))


def _traverse_leduc_coro_with_policy(
    state, traverser, adv_buffer, policy_buffer, iteration, max_actions=4,
):
    """Like _traverse_leduc_coro but also collects policy samples.
    At each decision node, records (state, regret_matched_strategy) for policy network training.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
    action_slots = [action_slot_map[a] for a in actions]

    # Collect policy sample: the regret-matched strategy at this state
    if policy_buffer is not None:
        policy_buffer.add(PolicySample(
            state=raw.copy(), strategy=strategy.copy(),
            legal_mask=legal_mask.copy(), iteration=iteration + 1,
        ))

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[action_slots[i]] = yield from _traverse_leduc_coro_with_policy(
                child, traverser, adv_buffer, policy_buffer, iteration, max_actions)

        ev = float(np.sum(strategy * values))
        inst_advantages = (values - ev) * legal_mask
        adv_buffer.add(AdvantageSample(
            state=raw, advantages=inst_advantages,
            legal_mask=legal_mask, iteration=iteration + 1))
        return ev
    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return (yield from _traverse_leduc_coro_with_policy(
            child, traverser, adv_buffer, policy_buffer, iteration, max_actions))


def batched_traverse_leduc(
    n_traversals: int,
    traverser: int,
    adv_nets: list[LeducAdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    max_actions: int = 4,
    concurrent: int = 1024,
    policy_buffer: PolicyBuffer | None = None,
) -> float:
    """Run n_traversals with batched NN inference using coroutine scheduling.

    Instead of 40,000 individual GPU calls (batch=1), this batches all pending
    NN evals across concurrent fibers into ~40-80 batched forward passes.
    Each fiber is a Python generator that yields at NN eval points.
    """
    ev_sum = 0.0
    n_spawned = 0

    # fibers: list of (generator, pending_request)
    fibers: list[tuple] = []

    def _spawn_fiber():
        nonlocal n_spawned
        state = LeducGameState().deal_new_hand()
        if policy_buffer is not None:
            gen = _traverse_leduc_coro_with_policy(
                state, traverser, adv_buffer, policy_buffer, iteration, max_actions)
        else:
            gen = _traverse_leduc_coro(state, traverser, adv_buffer, iteration, max_actions)
        req = next(gen)  # advance to first yield
        fibers.append((gen, req))
        n_spawned += 1

    # Spawn initial batch
    for _ in range(min(concurrent, n_traversals)):
        _spawn_fiber()

    while fibers:
        # Group pending evals by player (P0 and P1 use different nets)
        p0_indices, p0_raws, p0_masks = [], [], []
        p1_indices, p1_raws, p1_masks = [], [], []

        for i, (_gen, req) in enumerate(fibers):
            player, raw, mask = req
            if player == 0:
                p0_indices.append(i)
                p0_raws.append(raw)
                p0_masks.append(mask)
            else:
                p1_indices.append(i)
                p1_raws.append(raw)
                p1_masks.append(mask)

        results = [None] * len(fibers)

        # Batch forward pass for each player's network
        for indices, raws, masks, net in [
            (p0_indices, p0_raws, p0_masks, adv_nets[0]),
            (p1_indices, p1_raws, p1_masks, adv_nets[1]),
        ]:
            if not indices:
                continue
            raw_t = torch.from_numpy(np.stack(raws)).to(device)
            mask_t = torch.from_numpy(np.stack(masks)).to(device)
            with torch.inference_mode():
                out = net(raw_t, mask_t).cpu().numpy()
            for j, idx in enumerate(indices):
                results[idx] = out[j]

        # Advance all fibers with their results
        new_fibers: list[tuple] = []
        for i, (gen, _) in enumerate(fibers):
            try:
                new_req = gen.send(results[i])
                new_fibers.append((gen, new_req))
            except StopIteration as e:
                ev_sum += e.value
                # Spawn replacement fiber if more traversals needed
                if n_spawned < n_traversals:
                    state = LeducGameState().deal_new_hand()
                    if policy_buffer is not None:
                        new_gen = _traverse_leduc_coro_with_policy(
                            state, traverser, adv_buffer, policy_buffer, iteration, max_actions)
                    else:
                        new_gen = _traverse_leduc_coro(
                            state, traverser, adv_buffer, iteration, max_actions)
                    new_req = next(new_gen)
                    new_fibers.append((new_gen, new_req))
                    n_spawned += 1
        fibers = new_fibers

    return ev_sum


def _traverse_hunl_coro(state, traverser, adv_buffer, iteration,
                        encoder=HUNLEncoder, max_actions=9, explore_eps=0.1):
    """Generator-based HUNL traversal. Yields (player, raw, mask) for NN eval.
    Receives advantages via send(). Returns EV via StopIteration.value.
    explore_eps: mix strategy with uniform over legal actions for exploration."""
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = encoder.encode(state)
    legal_mask = encode_legal_mask_from_actions(actions, max_actions)

    # YIELD to request batched NN eval
    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    slots = actions_to_slots(actions, max_actions)

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[slots[i]] = yield from _traverse_hunl_coro(
                child, traverser, adv_buffer, iteration, encoder, max_actions, explore_eps)

        ev = float(np.sum(strategy * values))
        inst_advantages = (values - ev) * legal_mask
        sizing_target = _compute_sizing_target(actions, slots, inst_advantages, state)
        adv_buffer.add(AdvantageSample(
            state=raw, advantages=inst_advantages,
            legal_mask=legal_mask, iteration=iteration + 1,
            sizing_target=sizing_target))
        return ev
    else:
        # Exploration: mix strategy with uniform over legal actions
        if explore_eps > 0:
            n_legal = legal_mask.sum()
            uniform = legal_mask / max(n_legal, 1.0)
            mixed = (1 - explore_eps) * strategy + explore_eps * uniform
        else:
            mixed = strategy
        slot_probs = np.array([mixed[slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return (yield from _traverse_hunl_coro(
            child, traverser, adv_buffer, iteration, encoder, max_actions, explore_eps))


def _traverse_hunl_coro_with_policy(state, traverser, adv_buffer, policy_buffer,
                                     iteration, encoder=HUNLEncoder, max_actions=9, explore_eps=0.1):
    """Like _traverse_hunl_coro but also collects policy samples."""
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = encoder.encode(state)
    legal_mask = encode_legal_mask_from_actions(actions, max_actions)

    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    slots = actions_to_slots(actions, max_actions)

    if policy_buffer is not None:
        policy_buffer.add(PolicySample(
            state=raw.copy(), strategy=strategy.copy(),
            legal_mask=legal_mask.copy(), iteration=iteration + 1,
        ))

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[slots[i]] = yield from _traverse_hunl_coro_with_policy(
                child, traverser, adv_buffer, policy_buffer, iteration, encoder, max_actions, explore_eps)

        ev = float(np.sum(strategy * values))
        inst_advantages = (values - ev) * legal_mask
        sizing_target = _compute_sizing_target(actions, slots, inst_advantages, state)
        adv_buffer.add(AdvantageSample(
            state=raw, advantages=inst_advantages,
            legal_mask=legal_mask, iteration=iteration + 1,
            sizing_target=sizing_target))
        return ev
    else:
        # Exploration: mix strategy with uniform over legal actions
        if explore_eps > 0:
            n_legal = legal_mask.sum()
            uniform = legal_mask / max(n_legal, 1.0)
            mixed = (1 - explore_eps) * strategy + explore_eps * uniform
        else:
            mixed = strategy
        slot_probs = np.array([mixed[slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return (yield from _traverse_hunl_coro_with_policy(
            child, traverser, adv_buffer, policy_buffer, iteration, encoder, max_actions, explore_eps))


def traverse_hunl_batched(
    n_traversals: int,
    traverser: int,
    adv_nets: list[AdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    encoder: type = HUNLEncoder,
    max_actions: int = 9,
    concurrent: int = 512,
    config_factory=None,
    policy_buffer: PolicyBuffer | None = None,
) -> float:
    """Run n_traversals with batched NN inference using coroutine scheduling.

    Same coroutine pattern as batched_traverse_leduc — 512 concurrent fibers,
    batch GPU forward passes, dispatch results via send().
    """
    if config_factory is None:
        config_factory = GameConfig.srp_50bb

    ev_sum = 0.0
    n_spawned = 0

    fibers: list[tuple] = []

    def _spawn_fiber():
        nonlocal n_spawned
        state = HUNLGameState(config_factory()).deal_new_hand()
        if policy_buffer is not None:
            gen = _traverse_hunl_coro_with_policy(
                state, traverser, adv_buffer, policy_buffer, iteration, encoder, max_actions)
        else:
            gen = _traverse_hunl_coro(state, traverser, adv_buffer, iteration, encoder, max_actions)
        req = next(gen)
        fibers.append((gen, req))
        n_spawned += 1

    # Spawn initial batch
    for _ in range(min(concurrent, n_traversals)):
        _spawn_fiber()

    while fibers:
        # Group pending evals by player
        p0_indices, p0_raws, p0_masks = [], [], []
        p1_indices, p1_raws, p1_masks = [], [], []

        for i, (_gen, req) in enumerate(fibers):
            player, raw, mask = req
            if player == 0:
                p0_indices.append(i)
                p0_raws.append(raw)
                p0_masks.append(mask)
            else:
                p1_indices.append(i)
                p1_raws.append(raw)
                p1_masks.append(mask)

        results = [None] * len(fibers)

        # Batch forward pass for each player's network
        for indices, raws, masks, net in [
            (p0_indices, p0_raws, p0_masks, adv_nets[0]),
            (p1_indices, p1_raws, p1_masks, adv_nets[1]),
        ]:
            if not indices:
                continue
            raw_t = torch.from_numpy(np.stack(raws)).to(device)
            mask_t = torch.from_numpy(np.stack(masks)).to(device)
            with torch.inference_mode():
                out = net(raw_t, mask_t).cpu().numpy()
            for j, idx in enumerate(indices):
                results[idx] = out[j]

        # Advance all fibers with their results
        new_fibers: list[tuple] = []
        for i, (gen, _) in enumerate(fibers):
            try:
                new_req = gen.send(results[i])
                new_fibers.append((gen, new_req))
            except StopIteration as e:
                ev_sum += e.value
                if n_spawned < n_traversals:
                    # Spawn replacement inline (don't use _spawn_fiber which appends to fibers during iteration)
                    state = HUNLGameState(config_factory()).deal_new_hand()
                    if policy_buffer is not None:
                        new_gen = _traverse_hunl_coro_with_policy(
                            state, traverser, adv_buffer, policy_buffer, iteration, encoder, max_actions)
                    else:
                        new_gen = _traverse_hunl_coro(
                            state, traverser, adv_buffer, iteration, encoder, max_actions)
                    first_req = next(new_gen)
                    new_fibers.append((new_gen, first_req))
                    n_spawned += 1
        fibers = new_fibers

    return ev_sum



# ---------- Sizing Target ----------

def _compute_sizing_target(
    actions: list[Action],
    slots: list[int],
    advantages: np.ndarray,
    state: HUNLGameState,
) -> float:
    """Compute sizing regression target as weighted average of bet fractions by positive advantages.

    Returns a value in [0, 1] representing pot fraction, or -1.0 if no bet/raise actions.
    """
    pot = max(state.pot, 0.01)
    committed = state.street_committed[state.current_player]

    bet_fracs = []
    bet_advs = []
    for i, action in enumerate(actions):
        if action.type in (ActionType.BET, ActionType.RAISE):
            # Convert absolute bet amount to pot fraction
            bet_amount = action.amount - committed
            frac = bet_amount / pot
            slot = slots[i]
            adv = max(advantages[slot], 0.0)  # only positive advantages
            bet_fracs.append(frac)
            bet_advs.append(adv)

    if not bet_fracs:
        return -1.0

    total_adv = sum(bet_advs)
    if total_adv > 0:
        # Weighted average of bet fractions by positive advantage
        target = sum(f * a for f, a in zip(bet_fracs, bet_advs)) / total_adv
    else:
        # All bet advantages <= 0: use uniform average
        target = sum(bet_fracs) / len(bet_fracs)

    # Clamp to [0, 2] then normalize to [0, 1] (max fraction is 1.5, so /2 maps to [0, 0.75])
    return min(target / 2.0, 1.0)


# ---------- Regret Matching ----------

def _regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    """Convert advantages to a strategy via regret matching.

    When all advantages are non-positive, selects the action with the highest
    (least negative) advantage with probability 1, per Brown et al. (2019) Sec 4.1.
    This produces ~50% lower exploitability vs uniform fallback.
    """
    positive = np.maximum(advantages, 0) * legal_mask
    total = positive.sum()
    if total > 0:
        return positive / total
    else:
        # Paper: select highest (least negative) advantage action
        masked = np.where(legal_mask > 0, advantages, -np.inf)
        best = np.argmax(masked)
        result = np.zeros_like(advantages)
        result[best] = 1.0
        return result


# ---------- Network Training ----------

def train_advantage_net(
    net: nn.Module,
    buffer: ReservoirBuffer,
    device: torch.device,
    max_iteration: int,
    steps: int = 4000,
    batch_size: int = 4096,
    lr: float = 0.001,
    reinit: bool = True,
    sizing_weight: float = 0.1,
) -> float:
    """
    Train advantage network on the reservoir buffer.
    Uses weighted MSE loss with Linear CFR weighting + optional sizing regression loss.
    Returns final loss.
    """
    if reinit:
        _reinit_weights(net)
    net.to(device)
    net.train()

    has_sizing_head = hasattr(net, 'sizing_head')

    optimizer = optim.Adam(net.parameters(), lr=lr)
    scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=steps, eta_min=lr * 0.1)
    huber = nn.SmoothL1Loss(reduction='none')  # Huber loss — robust to outlier advantages
    total_loss = 0.0

    for step in range(steps):
        states, targets, masks, weights, sizing_targets = buffer.sample_batch(batch_size, device)

        if has_sizing_head:
            preds, sizing_pred = net(states, masks, return_sizing=True)
        else:
            preds = net(states, masks)

        # Weighted Huber loss over legal actions (more robust than MSE to outlier advantages)
        diff = huber(preds, targets) * masks
        per_sample_loss = diff.sum(dim=-1)  # sum over actions
        weighted_loss = (per_sample_loss * weights).mean()

        # Sizing regression loss (only for samples with valid target >= 0)
        if has_sizing_head and sizing_weight > 0:
            valid_mask = (sizing_targets >= 0).float()
            if valid_mask.sum() > 0:
                sizing_mse = ((sizing_pred.squeeze(-1) - sizing_targets) ** 2 * valid_mask).sum() / valid_mask.sum()
                weighted_loss = weighted_loss + sizing_weight * sizing_mse

        optimizer.zero_grad()
        weighted_loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        optimizer.step()
        scheduler.step()

        total_loss += weighted_loss.item()

    return total_loss / max(steps, 1)


def train_advantage_aggregated(
    net: nn.Module,
    buffer: ReservoirBuffer,
    device: torch.device,
    max_iteration: int = 0,  # deprecated, uses DCFR discounting per-sample now
    max_actions: int = 4,
    epochs: int = 100,
    lr: float = 0.001,
) -> float:
    """
    Train advantage network on per-info-set aggregated targets.
    Aggregates buffer samples by their feature encoding, computes weighted-average
    advantages per info set, then trains the network on these 'clean' targets.
    Warm-starts from current weights (no reinit) — ~2x better than reinit.
    Returns final loss.
    """
    net.to(device)
    net.train()

    # Aggregate samples by feature encoding (unique per info set)
    agg: dict[bytes, dict] = {}
    for s in buffer.buffer:
        key = s.state.tobytes()
        if key not in agg:
            agg[key] = {
                'state': s.state,
                'mask': s.legal_mask,
                'wadv': np.zeros(max_actions, dtype=np.float64),
                'wsum': 0.0,
            }
        # DCFR discounting: t^alpha / (t^alpha + 1), alpha=1.5
        t = s.iteration
        w = (t ** 1.5) / (t ** 1.5 + 1) if t > 0 else 0.0
        agg[key]['wadv'] += w * s.advantages.astype(np.float64)
        agg[key]['wsum'] += w

    if not agg:
        return 0.0

    states_t = torch.from_numpy(np.stack([v['state'] for v in agg.values()])).to(device)
    targets_t = torch.from_numpy(np.stack([
        (v['wadv'] / max(v['wsum'], 1e-8)).astype(np.float32) for v in agg.values()
    ])).to(device)
    masks_t = torch.from_numpy(np.stack([v['mask'] for v in agg.values()])).to(device)
    n = len(agg)

    # Scale batch size and epochs by dataset size.
    # Target: ~4000 gradient steps total regardless of dataset size.
    TARGET_STEPS = 4000
    if n > 10000:
        batch_size = min(2048, n)
    elif n > 1000:
        batch_size = min(512, n)
    else:
        batch_size = min(64, n)
    steps_per_epoch = max(1, n // batch_size)
    actual_epochs = max(3, min(epochs, TARGET_STEPS // steps_per_epoch))

    optimizer = optim.Adam(net.parameters(), lr=lr)
    huber = nn.SmoothL1Loss(reduction='none')
    total_loss = 0.0
    total_steps = 0

    for _ in range(actual_epochs):
        indices = torch.randperm(n, device=device)
        for start in range(0, n, batch_size):
            idx = indices[start:start + batch_size]
            preds = net(states_t[idx], masks_t[idx])
            diff = huber(preds, targets_t[idx]) * masks_t[idx]
            loss = diff.sum(dim=-1).mean()

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()
            total_steps += 1

    return total_loss / max(total_steps, 1)


def train_policy_net(
    policy_net: nn.Module,
    policy_buffer: PolicyBuffer,
    device: torch.device,
    steps: int = 2000,
    batch_size: int = 512,
    lr: float = 0.0005,
) -> float:
    """
    Train policy network with weighted cross-entropy on strategy targets.
    The policy network directly outputs action probabilities (softmax).
    Targets are the regret-matched strategies from the advantage network.
    Warm-starts from current weights (no reinit).
    """
    policy_net.to(device)
    policy_net.train()
    optimizer = optim.Adam(policy_net.parameters(), lr=lr)
    total_loss = 0.0

    for step in range(steps):
        states, strategies, masks, weights = policy_buffer.sample_batch(batch_size, device)
        pred_probs = policy_net(states, masks)  # softmaxed output
        log_pred = torch.log(pred_probs + 1e-8) * masks
        ce_loss = -(strategies * log_pred).sum(dim=-1)
        weighted_loss = (ce_loss * weights).mean()

        optimizer.zero_grad()
        weighted_loss.backward()
        nn.utils.clip_grad_norm_(policy_net.parameters(), 1.0)
        optimizer.step()
        total_loss += weighted_loss.item()

    return total_loss / max(steps, 1)


def _reinit_weights(net: nn.Module) -> None:
    """Re-initialize all weights (SD-CFR trains from scratch each iteration)."""
    for m in net.modules():
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, 0, 0.1)
            if m.padding_idx is not None:
                nn.init.zeros_(m.weight[m.padding_idx])
        elif isinstance(m, nn.LayerNorm):
            nn.init.ones_(m.weight)
            nn.init.zeros_(m.bias)


# ---------- Main Training Loop ----------

def train_sdcfr(
    game: str = 'leduc',
    iterations: int = 100,
    traversals_per_iter: int = 5000,
    train_steps: int = 1200,
    batch_size: int = 2048,
    lr: float = 0.001,
    buffer_size: int = 1_000_000,
    device_str: str = 'auto',
    checkpoint_dir: str = 'checkpoints/sdcfr',
    checkpoint_interval: int = 10,
    resume_path: str | None = None,
    game_config: str = 'srp_50bb',
    train_mode: str = 'standard',
    use_policy_net: bool = False,
    hidden_dims: tuple[int, ...] | None = None,
    eval_interval: int = 0,
    eval_samples: int = 5000,
) -> StrategyBuffer:
    """
    Main SD-CFR training loop.

    Args:
        train_mode: 'standard' (reinit + MSE), 'warm' (warm-start + MSE),
                    'aggregated' (warm-start + aggregated targets — best for Leduc)
        use_policy_net: if True, also train a policy network for average strategy
    """
    # Device
    if device_str == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(device_str)
    print(f"Using device: {device}")

    # Game setup
    is_leduc = game == 'leduc'

    # Resolve 'auto' train mode: aggregated for Leduc, warm for HUNL
    # warm = warm-start (no reinit) + mini-batch SGD — faster than aggregated, better than standard
    if train_mode == 'auto':
        train_mode = 'aggregated' if is_leduc else 'warm'

    if is_leduc:
        max_actions = 4
        net_oop = LeducAdvantageNetwork(max_actions=max_actions).to(device)
        net_ip = LeducAdvantageNetwork(max_actions=max_actions).to(device)
    else:
        max_actions = 9
        h_dims = hidden_dims or (256, 256)
        net_oop = AdvantageNetwork(max_actions=max_actions, hidden_dims=h_dims).to(device)
        net_ip = AdvantageNetwork(max_actions=max_actions, hidden_dims=h_dims).to(device)

    nets = [net_oop, net_ip]

    buffers = [ReservoirBuffer(buffer_size), ReservoirBuffer(buffer_size)]
    strategy_buffers = [StrategyBuffer(), StrategyBuffer()]

    # Policy networks (optional)
    policy_nets = None
    policy_bufs = None
    if use_policy_net:
        if is_leduc:
            policy_nets = [LeducPolicyNetwork(max_actions).to(device) for _ in range(2)]
        else:
            policy_nets = [PolicyNetwork(max_actions, hidden_dims=h_dims).to(device) for _ in range(2)]
        policy_bufs = [PolicyBuffer(buffer_size), PolicyBuffer(buffer_size)]

    # Game config
    configs = {
        'srp_50bb': GameConfig.srp_50bb,
        'bet3_50bb': GameConfig.bet3_50bb,
        'srp_100bb': GameConfig.srp_100bb,
        'bet3_100bb': GameConfig.bet3_100bb,
        'full_50bb': GameConfig.full_50bb,
        'full_100bb': GameConfig.full_100bb,
        'expanded_srp_50bb': GameConfig.expanded_srp_50bb,
    }
    config_factory = configs.get(game_config, GameConfig.srp_50bb)

    # Checkpoint dir
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Resume
    start_iter = 0
    if resume_path and os.path.exists(resume_path):
        print(f"Resuming from {resume_path}")
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        start_iter = ckpt['iteration'] + 1

        # Auto-detect architecture from checkpoint
        if is_leduc:
            sample_sd = ckpt['net_0']
            dims = []
            i = 0
            while f'trunk.{i}.weight' in sample_sd:
                dims.append(sample_sd[f'trunk.{i}.weight'].shape[0])
                i += 2  # skip ReLU layers (no parameters)
            for p_idx in range(2):
                nets[p_idx] = LeducAdvantageNetwork(
                    max_actions=max_actions, hidden_dims=tuple(dims)
                ).to(device)
        else:
            # Auto-detect max_actions from checkpoint
            ckpt_max_actions = ckpt.get('max_actions', None)
            if ckpt_max_actions is not None:
                max_actions = ckpt_max_actions
            else:
                # Fallback: detect from adv_head output size
                sample_sd = ckpt['net_0']
                if 'adv_head.2.weight' in sample_sd:
                    max_actions = sample_sd['adv_head.2.weight'].shape[0]

            ckpt_dims = ckpt.get('hidden_dims', None)
            if ckpt_dims:
                h_dims = tuple(ckpt_dims)
            for p_idx in range(2):
                nets[p_idx] = AdvantageNetwork(
                    max_actions=max_actions, hidden_dims=h_dims
                ).to(device)
            if use_policy_net and policy_nets:
                for p_idx in range(2):
                    policy_nets[p_idx] = PolicyNetwork(
                        max_actions, hidden_dims=h_dims
                    ).to(device)

        for p in range(2):
            nets[p].load_state_dict(ckpt[f'net_{p}'], strict=False)
            for sd, w in ckpt[f'strategy_buffer_{p}']:
                # Normalize to CPU (checkpoint may load to CUDA via map_location)
                cpu_sd = OrderedDict((k, v.cpu()) for k, v in sd.items())
                strategy_buffers[p].networks.append((cpu_sd, w))
        if use_policy_net and 'policy_net_0' in ckpt:
            for p in range(2):
                policy_nets[p].load_state_dict(ckpt[f'policy_net_{p}'], strict=False)
        print(f"Resumed at iteration {start_iter}, strategy buffer has {len(strategy_buffers[0])} networks")

    # Metrics log
    metrics_path = os.path.join(checkpoint_dir, 'metrics.jsonl')

    print(f"\n{'='*60}")
    print(f"SD-CFR Training: {game.upper()} | {game_config}")
    print(f"Iterations: {iterations} | Traversals/iter: {traversals_per_iter}")
    print(f"Train mode: {train_mode} | Policy net: {use_policy_net}")
    print(f"Train steps: {train_steps} | Batch: {batch_size} | LR: {lr}")
    print(f"Buffer size: {buffer_size:,} | Device: {device}")
    if not is_leduc:
        print(f"Network hidden dims: {h_dims}")
    print(f"{'='*60}\n")

    for t in range(start_iter, iterations):
        iter_start = time.time()

        for p in range(2):
            # --- 1. Traversals ---
            trav_start = time.time()
            ev_sum = 0.0

            if is_leduc:
                p_policy_buf = policy_bufs[p] if policy_bufs else None
                ev_sum = batched_traverse_leduc(
                    traversals_per_iter, p, nets, buffers[p],
                    t, device, max_actions, concurrent=1024,
                    policy_buffer=p_policy_buf)
            else:
                p_policy_buf = policy_bufs[p] if policy_bufs else None
                ev_sum = traverse_hunl_batched(
                    traversals_per_iter, p, nets, buffers[p],
                    t, device, HUNLEncoder, max_actions, concurrent=1024,
                    config_factory=config_factory,
                    policy_buffer=p_policy_buf)
            avg_ev = ev_sum / traversals_per_iter

            trav_time = time.time() - trav_start

            # --- 2. Train advantage network ---
            train_start = time.time()
            actual_steps = 0  # for logging; set by standard/warm mode, 0 = aggregated
            if train_mode == 'aggregated':
                loss = train_advantage_aggregated(
                    nets[p], buffers[p], device,
                    max_iteration=t + 1, max_actions=max_actions,
                    epochs=100, lr=lr,
                )
            else:
                reinit = (train_mode == 'standard')
                # Ensure enough training: at least 3 epochs over buffer, minimum 500 steps
                epochs_worth = max(1, len(buffers[p]) // batch_size) * 3
                actual_steps = max(500, min(train_steps, epochs_worth))
                loss = train_advantage_net(
                    nets[p], buffers[p], device,
                    max_iteration=t + 1,
                    steps=actual_steps,
                    batch_size=batch_size,
                    lr=lr,
                    reinit=reinit,
                )
            train_time = time.time() - train_start

            # --- 3. Advantage magnitude diagnostics ---
            adv_mean = adv_max = 0.0
            if len(buffers[p]) >= 256:
                with torch.inference_mode():
                    diag_s, diag_a, diag_m, _, _ = buffers[p].sample_batch(256, device)
                    pred_a = nets[p](diag_s, diag_m)
                    adv_abs = (pred_a * diag_m).abs()
                    nonzero = adv_abs[adv_abs > 0]
                    if len(nonzero) > 0:
                        adv_mean = nonzero.mean().item()
                        adv_max = adv_abs.max().item()

            # --- 4. Store network in strategy buffer ---
            strategy_buffers[p].add(nets[p], t)

            # --- 5. Train policy network (optional) ---
            pol_loss = 0.0
            if policy_nets and policy_bufs:
                pol_steps = min(2000, max(len(policy_bufs[p]) // 128, 200))
                pol_loss = train_policy_net(
                    policy_nets[p], policy_bufs[p], device,
                    steps=pol_steps, batch_size=512, lr=0.0005,
                )

            print(
                f"  Iter {t+1} P{p}: EV={avg_ev:+.4f} | "
                f"loss={loss:.6f} | "
                f"buf={len(buffers[p]):,} | "
                f"adv={adv_mean:.3f}/{adv_max:.3f} | "
                f"steps={actual_steps} | "
                f"trav={trav_time:.1f}s | train={train_time:.1f}s"
                + (f" | pol_loss={pol_loss:.4f}" if policy_nets else "")
            )

        iter_time = time.time() - iter_start

        print(f"  Iter {t+1} total: {iter_time:.1f}s | "
              f"strategy_buf: {len(strategy_buffers[0])} nets, "
              f"{strategy_buffers[0].memory_mb():.1f}MB")

        # Periodic LBR evaluation
        lbr_exploit = None
        if eval_interval > 0 and (t + 1) % eval_interval == 0:
            from .eval_agent import SDCFRAgent, compute_lbr_exploitability_hunl, compute_exploitability_leduc
            eval_start = time.time()
            if is_leduc:
                eval_agents = []
                for p in range(2):
                    sb = StrategyBuffer()
                    sb.networks = list(strategy_buffers[p].networks)
                    template = LeducAdvantageNetwork(max_actions=max_actions)
                    eval_agents.append(SDCFRAgent(sb, template, device=device, mode='ensemble'))
                lbr_exploit = compute_exploitability_leduc(eval_agents)
            else:
                # Use 'average' mode for speed during training (single forward pass vs N)
                eval_agents = []
                for p in range(2):
                    sb = StrategyBuffer()
                    sb.networks = list(strategy_buffers[p].networks)
                    template = AdvantageNetwork(max_actions=max_actions, hidden_dims=h_dims)
                    eval_agents.append(SDCFRAgent(sb, template, device=device, mode='average'))
                lbr_exploit = compute_lbr_exploitability_hunl(
                    eval_agents, config_factory=config_factory, n_samples=eval_samples)
            eval_time = time.time() - eval_start
            print(f"  >>> {'Exploitability' if is_leduc else 'LBR Exploitability'}: "
                  f"{lbr_exploit:.1f} mbb/g ({eval_time:.1f}s)")

        # Checkpoint FIRST (before eval, so progress is saved even if eval crashes)
        if (t + 1) % checkpoint_interval == 0 or t == iterations - 1:
            ckpt_path = os.path.join(checkpoint_dir, f'sdcfr_iter{t+1}.pt')
            ckpt_data = {
                'iteration': t,
                'game': game,
                'game_config': game_config,
                'train_mode': train_mode,
                'max_actions': max_actions,
                'net_0': nets[0].state_dict(),
                'net_1': nets[1].state_dict(),
                'strategy_buffer_0': strategy_buffers[0].networks,
                'strategy_buffer_1': strategy_buffers[1].networks,
                'hidden_dims': h_dims if not is_leduc else None,
            }
            if policy_nets:
                ckpt_data['policy_net_0'] = policy_nets[0].state_dict()
                ckpt_data['policy_net_1'] = policy_nets[1].state_dict()
            torch.save(ckpt_data, ckpt_path)
            print(f"  Checkpoint saved: {ckpt_path}")

        # Log metrics
        metrics = {
            'iteration': t + 1,
            'time_s': iter_time,
            'buffer_size': [len(b) for b in buffers],
            'strategy_buffer_size': len(strategy_buffers[0]),
        }
        if lbr_exploit is not None:
            metrics['exploitability_mbbg'] = lbr_exploit
        with open(metrics_path, 'a') as f:
            json.dump(metrics, f)
            f.write('\n')

    print(f"\nTraining complete! {len(strategy_buffers[0])} networks in strategy buffer.")
    return strategy_buffers


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='SD-CFR Training')
    parser.add_argument('--game', type=str, default='leduc', choices=['leduc', 'hunl'])
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--traversals', type=int, default=20000)
    parser.add_argument('--train-steps', type=int, default=1200)
    parser.add_argument('--batch-size', type=int, default=2048)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--buffer-size', type=int, default=2_000_000)
    parser.add_argument('--device', type=str, default='auto')
    parser.add_argument('--checkpoint-dir', type=str, default='checkpoints/sdcfr')
    parser.add_argument('--checkpoint-interval', type=int, default=10)
    parser.add_argument('--resume', type=str, default=None)
    parser.add_argument('--game-config', type=str, default='srp_50bb',
                       choices=['srp_50bb', 'bet3_50bb', 'srp_100bb', 'bet3_100bb',
                                'full_50bb', 'full_100bb', 'expanded_srp_50bb'])
    parser.add_argument('--train-mode', type=str, default='auto',
                       choices=['standard', 'warm', 'aggregated', 'auto'],
                       help='Training mode: standard (reinit+MSE), warm (warm-start+MSE), '
                            'aggregated (warm-start+aggregated targets), '
                            'auto (aggregated for Leduc, standard for HUNL)')
    parser.add_argument('--use-policy-net', action='store_true',
                       help='Also train a policy network for average strategy')
    parser.add_argument('--hidden-dims', type=str, default=None,
                       help='HUNL network hidden dims, comma-separated (e.g. "512,512,512")')
    parser.add_argument('--eval-interval', type=int, default=0,
                       help='Run LBR evaluation every N iterations (0=disabled)')
    parser.add_argument('--eval-samples', type=int, default=5000,
                       help='Number of samples for LBR evaluation')
    args = parser.parse_args()

    hdims = None
    if args.hidden_dims:
        hdims = tuple(int(d) for d in args.hidden_dims.split(','))

    # HUNL-aware defaults: override CLI defaults when user didn't specify
    if args.game == 'hunl':
        if args.train_steps == 1200:
            args.train_steps = 4000
        if args.batch_size == 2048:
            args.batch_size = 4096
        if args.buffer_size == 2_000_000:
            args.buffer_size = 10_000_000
        if hdims is None:
            hdims = (256, 256, 256)

    train_sdcfr(
        game=args.game,
        iterations=args.iterations,
        traversals_per_iter=args.traversals,
        train_steps=args.train_steps,
        batch_size=args.batch_size,
        lr=args.lr,
        buffer_size=args.buffer_size,
        device_str=args.device,
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_interval=args.checkpoint_interval,
        resume_path=args.resume,
        game_config=args.game_config,
        train_mode=args.train_mode,
        use_policy_net=args.use_policy_net,
        hidden_dims=hdims,
        eval_interval=args.eval_interval,
        eval_samples=args.eval_samples,
    )


if __name__ == '__main__':
    main()
