#!/usr/bin/env python3
"""
Play AlphaHoldem V3 against Slumbot via HTTP API.

Slumbot plays 200bb HUNL (SB=50, BB=100, Stack=20000 chips).
Our AlphaHoldem trained on 50bb. We'll treat 1 BB = 100 chips for conversion.

Protocol:
  - POST /slumbot/api/new_hand
  - POST /slumbot/api/act with {token, incr}
  - Action string: "b200c/kk/kb300" (k=check, c=call, f=fold, b=bet)
  - client_pos: 0 = BB (acts first postflop), 1 = SB (acts first preflop)
"""

import argparse
import sys
import os
import time
import math
import json
from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F

import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment_v55 import NUM_ACTIONS

HOST = 'slumbot.com'
SMALL_BLIND = 50
BIG_BLIND = 100
STACK_SIZE = 20000
NUM_STREETS = 4


# ═══════════════════════════════════════════════════════════
# Action parsing (ported from sample_api.py)
# ═══════════════════════════════════════════════════════════

def parse_action(action: str) -> dict:
    st = 0
    street_last_bet_to = BIG_BLIND
    total_last_bet_to = BIG_BLIND
    last_bet_size = BIG_BLIND - SMALL_BLIND
    last_bettor = 0
    sz = len(action)
    pos = 1  # SB acts first preflop

    if sz == 0:
        return {'st': st, 'pos': pos, 'street_last_bet_to': street_last_bet_to,
                'total_last_bet_to': total_last_bet_to, 'last_bet_size': last_bet_size,
                'last_bettor': last_bettor, 'street_actions': [[] for _ in range(4)]}

    street_actions = [[] for _ in range(4)]
    check_or_call_ends_street = False
    i = 0
    while i < sz:
        if st >= NUM_STREETS:
            return {'error': 'Unexpected'}
        c = action[i]
        i += 1
        if c == 'k':
            street_actions[st].append(('k', pos, 0))
            if check_or_call_ends_street:
                if st < NUM_STREETS - 1 and i < sz and action[i] == '/':
                    i += 1
                if st == NUM_STREETS - 1:
                    pos = -1
                else:
                    pos = 0; st += 1
                street_last_bet_to = 0
                check_or_call_ends_street = False
            else:
                pos = (pos + 1) % 2
                check_or_call_ends_street = True
        elif c == 'c':
            street_actions[st].append(('c', pos, street_last_bet_to))
            if total_last_bet_to == STACK_SIZE:
                # All-in call
                if i != sz:
                    for _ in range(st, NUM_STREETS - 1):
                        if i < sz and action[i] == '/':
                            i += 1
                st = NUM_STREETS - 1
                pos = -1
                return {'st': st, 'pos': pos, 'street_last_bet_to': street_last_bet_to,
                        'total_last_bet_to': total_last_bet_to, 'last_bet_size': 0,
                        'last_bettor': last_bettor, 'street_actions': street_actions}
            if check_or_call_ends_street:
                if st < NUM_STREETS - 1 and i < sz and action[i] == '/':
                    i += 1
                if st == NUM_STREETS - 1:
                    pos = -1
                else:
                    pos = 0; st += 1
                street_last_bet_to = 0
                check_or_call_ends_street = False
            else:
                pos = (pos + 1) % 2
                check_or_call_ends_street = True
            last_bet_size = 0
            last_bettor = -1
        elif c == 'f':
            street_actions[st].append(('f', pos, 0))
            pos = -1
            return {'st': st, 'pos': pos, 'street_last_bet_to': street_last_bet_to,
                    'total_last_bet_to': total_last_bet_to, 'last_bet_size': last_bet_size,
                    'last_bettor': last_bettor, 'street_actions': street_actions}
        elif c == 'b':
            j = i
            while i < sz and action[i] >= '0' and action[i] <= '9':
                i += 1
            new_street_last_bet_to = int(action[j:i])
            new_last_bet_size = new_street_last_bet_to - street_last_bet_to
            street_actions[st].append(('b', pos, new_street_last_bet_to))
            last_bet_size = new_last_bet_size
            last_bettor = pos
            total_last_bet_to += new_last_bet_size
            street_last_bet_to = new_street_last_bet_to
            pos = (pos + 1) % 2
            check_or_call_ends_street = True

    return {'st': st, 'pos': pos, 'street_last_bet_to': street_last_bet_to,
            'total_last_bet_to': total_last_bet_to, 'last_bet_size': last_bet_size,
            'last_bettor': last_bettor, 'street_actions': street_actions}


# ═══════════════════════════════════════════════════════════
# Feature encoding for AlphaHoldem (matches environment.py)
# ═══════════════════════════════════════════════════════════

SUIT_IDX = {'c': 0, 'd': 1, 'h': 2, 's': 3}
RANK_IDX = {'2': 0, '3': 1, '4': 2, '5': 3, '6': 4, '7': 5, '8': 6, '9': 7,
            'T': 8, 'J': 9, 'Q': 10, 'K': 11, 'A': 12}


def card_to_suit_rank(card_str: str):
    return SUIT_IDX[card_str[1]], RANK_IDX[card_str[0]]


def encode_cards(hole_cards: list, board: list, street: int) -> np.ndarray:
    """Encode cards tensor (6, 4, 13)."""
    t = np.zeros((6, 4, 13), dtype=np.float32)
    # Channel 0: hole
    for c in hole_cards:
        s, r = card_to_suit_rank(c)
        t[0, s, r] = 1.0
    # Channels 1-3: flop/turn/river
    for i, c in enumerate(board):
        s, r = card_to_suit_rank(c)
        if i < 3: t[1, s, r] = 1.0  # flop
        elif i == 3: t[2, s, r] = 1.0  # turn
        elif i == 4: t[3, s, r] = 1.0  # river
    # Channel 4: all public
    for c in board:
        s, r = card_to_suit_rank(c)
        t[4, s, r] = 1.0
    # Channel 5: all visible (hole + public)
    for c in hole_cards + board:
        s, r = card_to_suit_rank(c)
        t[5, s, r] = 1.0
    return t


def encode_action_history(
    state: dict,
    client_pos: int,
    current_pos: int,
    obs_version: str = 'v55',
) -> np.ndarray:
    """Encode action history for either legacy V4 or V5.5 checkpoints."""
    t = np.zeros((25, 4, 5), dtype=np.float32)
    max_slots = 6
    pot = max(compute_commitments(state)['pot'], 1)
    for st in range(4):
        prior_bet_to = BIG_BLIND if st == 0 else 0
        for slot, (act, pos, amt) in enumerate(state['street_actions'][st][:max_slots]):
            ch = st * max_slots + slot
            is_hero = 1.0 if pos == client_pos else 0.0
            t[ch, 0, 0] = is_hero

            if obs_version == 'v4':
                # Match the legacy training encoder: Action.amount is zero for
                # folds/checks/calls, bet/raise stores total street commitment,
                # and all amounts are normalized by the current pot.
                if act == 'b':
                    atype = 4 if prior_bet_to > 0 else 3
                    prior_bet_to = amt
                else:
                    atype = {'f': 0, 'k': 1, 'c': 2}.get(act, 1)
                denom = pot
                encoded_amount = amt if act == 'b' else 0
            else:
                # Match deep_cfr.game_state.ActionType:
                # FOLD=0, CHECK=1, CALL=2, BET=3, RAISE=4. Slumbot encodes both
                # bets and raises as "b", so infer the distinction from the street.
                if act == 'b':
                    atype = 4 if prior_bet_to > 0 else 3
                    prior_bet_to = amt
                else:
                    atype = {'f': 0, 'k': 1, 'c': 2}.get(act, 1)
                denom = pot
                encoded_amount = amt

            t[ch, 1, min(atype, 4)] = 1.0
            if encoded_amount > 0:
                t[ch, 2, 0] = min(encoded_amount / denom, 2.0) / 2.0
            t[ch, 3, 0] = 1.0  # slot filled
    # Channel 24: current player indicator
    t[24, 0, 0] = 1.0 if current_pos == client_pos else 0.0
    return t


def encode_extra(stacks_remaining: list, starting: float = STACK_SIZE) -> np.ndarray:
    return np.array([stacks_remaining[0] / starting, stacks_remaining[1] / starting], dtype=np.float32)


def compute_legal_mask(
    state: dict,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> np.ndarray:
    """9-slot legal actions: [fold, check/call, 6 raise sizes, allin]."""
    mask, _ = build_action_table(state, raise_action_mapping)
    return mask
    mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
    last_bet_size = state['last_bet_size']
    total_bet = state['total_last_bet_to']

    # Check/Call always legal
    mask[1] = 1.0

    # Fold only if facing a bet
    if last_bet_size > 0:
        mask[0] = 1.0

    # Raise sizes (slots 2-7) and allin (slot 8)
    remaining = STACK_SIZE - total_bet
    if remaining > 0:
        for i in range(2, 8):
            mask[i] = 1.0  # 6 raise sizes
        mask[8] = 1.0  # allin
    return mask


# ═══════════════════════════════════════════════════════════
# AlphaHoldem action → Slumbot incr string
# ═══════════════════════════════════════════════════════════

RAISE_FRACTIONS = [0.33, 0.50, 0.67, 0.75, 1.00, 1.50]
PREFLOP_RAISE_FRACTIONS = [0.50, 1.00, 1.50]
PREFLOP_RAISE_FRACTIONS_V2 = [0.50, 0.67, 0.75, 1.00, 1.50]


def closest_raise_slot(pot_frac: float) -> int:
    best_idx = 0
    best_dist = float('inf')
    for i, frac in enumerate(RAISE_FRACTIONS):
        dist = abs(pot_frac - frac)
        if dist < best_dist:
            best_idx = i
            best_dist = dist
    return best_idx + 2


def compute_commitments(state: dict) -> dict:
    """Approximate per-player commitments in chips from Slumbot's action string."""
    last_bet_size = state['last_bet_size']
    total_bet = state['total_last_bet_to']
    street_bet = state['street_last_bet_to']
    facing = last_bet_size > 0

    if facing:
        hero_total = max(total_bet - last_bet_size, 0)
        opp_total = total_bet
        hero_street = max(street_bet - last_bet_size, 0)
        opp_street = street_bet
        to_call = last_bet_size
    else:
        hero_total = total_bet
        opp_total = total_bet
        hero_street = street_bet
        opp_street = street_bet
        to_call = 0

    pot = hero_total + opp_total
    return {
        'facing': facing,
        'hero_total': hero_total,
        'opp_total': opp_total,
        'hero_street': hero_street,
        'opp_street': opp_street,
        'to_call': to_call,
        'pot': pot,
        'stack': max(STACK_SIZE - hero_total, 0),
    }


def build_action_table(
    state: dict,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> tuple[np.ndarray, list[str | None]]:
    """Mirror V5.5's sparse legal-mask + slot-to-action table for Slumbot."""
    if raise_action_mapping not in {
        "legacy_total_over_pot",
        "preflop_pot_fraction_v2",
        "pot_fraction_v2",
    }:
        raise ValueError(
            f"unknown raise action mapping: {raise_action_mapping}"
        )
    mask = np.zeros(NUM_ACTIONS, dtype=np.float32)
    slot_to_incr: list[str | None] = [None] * NUM_ACTIONS
    slot_dist = [float('inf')] * NUM_ACTIONS

    c = compute_commitments(state)
    facing = c['facing']
    to_call = c['to_call']
    pot = max(c['pot'], 1)
    stack = c['stack']
    street_bet = state['street_last_bet_to']
    last_bet_size = state['last_bet_size']

    if facing:
        mask[0] = 1.0
        slot_to_incr[0] = 'f'
    mask[1] = 1.0
    slot_to_incr[1] = 'c' if facing else 'k'

    if stack <= to_call:
        return mask, slot_to_incr

    max_target = STACK_SIZE - (c['hero_total'] - c['hero_street'])
    if max_target <= street_bet:
        return mask, slot_to_incr

    if state['st'] == 0:
        fractions = (
            PREFLOP_RAISE_FRACTIONS_V2
            if raise_action_mapping in {
                "preflop_pot_fraction_v2",
                "pot_fraction_v2",
            }
            else PREFLOP_RAISE_FRACTIONS
        )
    else:
        fractions = RAISE_FRACTIONS
    pot_after_call = pot + to_call
    min_bet_size = max(last_bet_size, BIG_BLIND)
    min_target = street_bet + min_bet_size

    for frac in fractions:
        if facing:
            target = street_bet + int(pot_after_call * frac)
        else:
            target = street_bet + int(pot * frac)
        target = max(target, min_target)
        if target >= max_target:
            continue

        use_corrected_fraction = (
            raise_action_mapping == "pot_fraction_v2"
            or (
                raise_action_mapping == "preflop_pot_fraction_v2"
                and int(state['st']) == 0
            )
        )
        if use_corrected_fraction:
            slot = closest_raise_slot(frac)
            dist = abs(frac - RAISE_FRACTIONS[slot - 2])
        else:
            slot = closest_raise_slot(target / pot)
            wanted = RAISE_FRACTIONS[slot - 2] * pot
            dist = abs(target - wanted)
        if dist < slot_dist[slot]:
            mask[slot] = 1.0
            slot_to_incr[slot] = f'b{target}'
            slot_dist[slot] = dist

    mask[8] = 1.0
    slot_to_incr[8] = f'b{max_target}'
    return mask, slot_to_incr


def action_idx_to_incr(
    action_idx: int,
    state: dict,
    raise_action_mapping: str = "legacy_total_over_pot",
) -> str:
    _, slot_to_incr = build_action_table(state, raise_action_mapping)
    if 0 <= action_idx < len(slot_to_incr) and slot_to_incr[action_idx] is not None:
        return slot_to_incr[action_idx]

    """Convert 9-slot action → Slumbot incr string."""
    last_bet_size = state['last_bet_size']
    total_bet = state['total_last_bet_to']
    street_bet = state['street_last_bet_to']

    # Compute pot for raise sizing
    # Pot after calling = total_bet * 2 (approximately)
    # Preflop: SB posts 50, BB posts 100. Total pot = 150 initially.
    pot_after_call = total_bet * 2

    # Max bet on THIS street = our total stack - chips committed on prior streets
    # total_bet counts all streets; street_bet counts current street only
    # chips committed on prior streets = total_bet - street_bet
    max_target = STACK_SIZE - (total_bet - street_bet)

    if action_idx == 0:
        return 'f'
    if action_idx == 1:
        return 'c' if last_bet_size > 0 else 'k'
    if action_idx == 8:
        # All-in: bet remaining stack on this street
        return f'b{max_target}'

    # Raise to X% pot
    frac = RAISE_FRACTIONS[action_idx - 2]
    target = street_bet + int(frac * pot_after_call)

    # Enforce min bet
    min_bet_size = max(last_bet_size, BIG_BLIND)
    min_target = street_bet + min_bet_size
    if target < min_target:
        target = min_target

    # Enforce max (all-in)
    if target >= max_target:
        return f'b{max_target}'

    return f'b{target}'


# ═══════════════════════════════════════════════════════════
# Slumbot client
# ═══════════════════════════════════════════════════════════

def new_hand(token: str | None) -> dict:
    data = {}
    if token:
        data['token'] = token
    r = requests.post(f'https://{HOST}/slumbot/api/new_hand', json=data, timeout=30)
    r.raise_for_status()
    return r.json()


def act(token: str, incr: str) -> dict:
    r = requests.post(f'https://{HOST}/slumbot/api/act',
                      json={'token': token, 'incr': incr}, timeout=30)
    r.raise_for_status()
    return r.json()


def resolve_obs_version(ckpt: dict, requested: str) -> str:
    if requested != 'auto':
        return requested
    obs_version = str(ckpt.get('obs_version', '')).lower()
    if obs_version in ('v4', 'v55'):
        return obs_version
    config = ckpt.get('config', {}) if isinstance(ckpt.get('config', {}), dict) else {}
    env_version = str(ckpt.get('env_version') or config.get('env_version') or '').lower()
    if env_version == 'v4':
        return 'v4'
    if env_version == 'v55cap1v4obs':
        return 'v4'
    if env_version in ('v55', 'v55cap1'):
        return 'v55'
    version = str(ckpt.get('version', '')).lower()
    if version.startswith('v5.5') or 'opponent_mode' in ckpt or 'mmd_anchor' in ckpt:
        return 'v55'
    return 'v4'


def current_street_index(state: dict) -> int:
    """Read the current street from live or synthetic parsed state."""
    return int(state.get('st', state.get('street', 0)))


class ProbabilityEnsemblePolicy(torch.nn.Module):
    """One greedy policy formed by averaging frozen member probabilities."""

    def __init__(self, models):
        super().__init__()
        if len(models) < 2:
            raise ValueError('probability ensemble requires at least two models')
        self.models = torch.nn.ModuleList(models)
        self.policy_logit_bias = None

    def forward(self, card, action_inp, extra, legal_mask=None):
        probabilities = []
        values = []
        for model in self.models:
            logits, value = model(card, action_inp, extra, legal_mask)
            probabilities.append(F.softmax(logits, dim=-1))
            values.append(value)
        mean_probability = torch.stack(probabilities, dim=0).mean(dim=0)
        ensemble_logits = mean_probability.clamp_min(1e-12).log()
        ensemble_value = torch.stack(values, dim=0).mean(dim=0)
        return ensemble_logits, ensemble_value


# ═══════════════════════════════════════════════════════════
# Play loop
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def guarded_action_probs(
    probs: torch.Tensor,
    legal_mask: torch.Tensor,
    state: dict,
    *,
    allin_max_spr: float = 2.0,
    allin_min_prob: float = 0.65,
) -> torch.Tensor:
    """Return a guarded one-forward-pass action distribution.

    The model still supplies all probabilities. The guard only suppresses
    high-SPR all-in choices when the model is not strongly committed to all-in,
    then renormalizes over the remaining legal actions.
    """
    guarded = probs.clone()
    if guarded.ndim != 2 or guarded.shape[-1] <= 8:
        return probs

    c = compute_commitments(state)
    pot_after_call = max(float(c.get('pot', 0.0) + c.get('to_call', 0.0)), 1.0)
    spr = float(c.get('stack', 0.0)) / pot_after_call
    allin_legal = bool(legal_mask[0, 8].item() > 0.0)
    allin_prob = guarded[:, 8]
    non_allin_legal_mass = (guarded[:, :8] * legal_mask[:, :8]).sum(dim=-1)

    suppress = (
        allin_legal
        and spr > allin_max_spr
    )
    if suppress:
        rows = (allin_prob < allin_min_prob) & (non_allin_legal_mass > 1e-12)
        guarded[rows, 8] = 0.0
        guarded = guarded * legal_mask
        guarded = guarded / guarded.sum(dim=-1, keepdim=True).clamp_min(1e-12)
    return guarded


def is_unopened_preflop_start(state: dict) -> bool:
    """True for the SB's first decision against only the posted blinds."""
    street_actions = state.get('street_actions') or [[] for _ in range(4)]
    return (
        int(state.get('st', 0)) == 0
        and int(state.get('pos', -1)) == 1
        and not street_actions[0]
        and int(state.get('street_last_bet_to', 0)) == BIG_BLIND
        and int(state.get('total_last_bet_to', 0)) == BIG_BLIND
        and int(state.get('last_bet_size', 0)) == BIG_BLIND - SMALL_BLIND
    )


def preflop_logit_bias_context(state: dict) -> str | None:
    """Return the checkpoint-bias context for the two first preflop decisions."""
    if is_unopened_preflop_start(state):
        return 'sb_open'
    street_actions = state.get('street_actions') or [[] for _ in range(4)]
    preflop_actions = street_actions[0]
    if (
        int(state.get('st', 0)) == 0
        and int(state.get('pos', -1)) == 0
        and len(preflop_actions) == 1
        and str(preflop_actions[0][0]) == 'b'
        and int(preflop_actions[0][1]) == 1
    ):
        return 'bb_vs_open'
    return None


def apply_checkpoint_policy_logit_bias(
    logits: torch.Tensor,
    model,
    state: dict,
) -> torch.Tensor:
    """Apply a frozen checkpoint-owned bias as part of direct model inference."""
    config = getattr(model, 'policy_logit_bias', None)
    if not isinstance(config, dict):
        return logits
    context = preflop_logit_bias_context(state)
    values = config.get(context) if context else None
    if not isinstance(values, (list, tuple)) or len(values) != logits.shape[-1]:
        return logits
    bias = torch.as_tensor(values, dtype=logits.dtype, device=logits.device)
    return logits + bias.unsqueeze(0)


def checkpoint_preflop_range_override(
    model,
    hole_cards: list,
    state: dict,
    client_pos: int,
    legal_mask: torch.Tensor,
    source_action: int,
) -> int:
    """Apply checkpoint-owned, hand-range-specific preflop overrides.

    Rules are evaluated in order and only replace the configured source action.
    This keeps the default model path unchanged outside explicitly listed hand
    percentile bands and contexts.
    """
    config = getattr(model, 'policy_range_override', None)
    if not isinstance(config, dict) or int(state.get('st', 0)) != 0:
        return int(source_action)
    context = preflop_logit_bias_context(state)
    if context == 'sb_open' and int(client_pos) != 1:
        return int(source_action)
    if context == 'bb_vs_open' and int(client_pos) != 0:
        return int(source_action)
    rules = config.get(context) if context else None
    if not isinstance(rules, list):
        return int(source_action)

    from heuristic_policy_v3 import _hand_notation
    from heuristic_policy_v4 import PREFLOP_PERCENTILE

    percentile = float(PREFLOP_PERCENTILE[_hand_notation(hole_cards)])
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        minimum = float(rule.get('percentile_min', 0.0))
        maximum = float(rule.get('percentile_max', 1.0))
        replace = int(rule.get('replace_action', source_action))
        selected = int(rule.get('force_action', source_action))
        if (
            minimum <= percentile < maximum
            and int(source_action) == replace
            and 0 <= selected < legal_mask.shape[-1]
            and bool(legal_mask[0, selected].item() > 0.0)
        ):
            return selected
    return int(source_action)


def checkpoint_preflop_strategy_override(
    model,
    hole_cards: list,
    state: dict,
    client_pos: int,
    legal_mask: torch.Tensor,
    source_action: int,
) -> dict | None:
    """Return a deterministic checkpoint-owned preflop action and sizing."""
    profile = getattr(model, 'preflop_strategy_profile', None)
    if (
        profile not in {
            'pokerskill_v1',
            'pokerskill_sb_v1',
            'pokerskill_sb_bbsize_v1',
            'pokerskill_sb_jamguard_v2',
            'pokerskill_v2',
        }
        or int(state.get('st', 0)) != 0
    ):
        return None

    from heuristic_policy_v3 import _hand_notation

    notation = _hand_notation(hole_cards)
    ranks = '23456789TJQKA'
    high, low = notation[0], notation[1]
    suited = notation.endswith('s')
    pair = len(notation) == 2
    high_index = ranks.index(high)
    low_index = ranks.index(low)

    context = preflop_logit_bias_context(state)
    street_actions = state.get('street_actions') or [[] for _ in range(4)]
    preflop_actions = street_actions[0]
    if (
        context is None
        and int(client_pos) == 0
        and len(street_actions[0]) == 1
        and str(street_actions[0][0][0]) == 'c'
        and int(street_actions[0][0][1]) == 1
    ):
        context = 'bb_vs_limp'
    if preflop_actions:
        last_action = preflop_actions[-1]
        last_move = str(last_action[0])
        last_amount = int(last_action[2]) if len(last_action) > 2 else 0
        if last_move == 'b' and last_amount >= STACK_SIZE:
            context = 'facing_jam'
        elif (
            context is None
            and int(client_pos) == 1
            and len(preflop_actions) == 2
            and last_move == 'b'
        ):
            context = (
                'sb_vs_limp_raise'
                if str(preflop_actions[0][0]) == 'c'
                else 'sb_vs_3bet'
            )
        elif (
            context is None
            and int(client_pos) == 0
            and len(preflop_actions) == 3
            and last_move == 'b'
        ):
            context = 'bb_vs_4bet'

    def legal(slot: int) -> bool:
        return (
            0 <= slot < legal_mask.shape[-1]
            and bool(legal_mask[0, slot].item() > 0.0)
        )

    def passive(slot: int, increment: str) -> dict | None:
        if not legal(slot):
            return None
        return {
            'slot': int(slot),
            'increment': increment,
            'context': context,
            'hand': notation,
        }

    def raise_to(target: int) -> dict | None:
        if not (legal(7) or legal(8)):
            return None
        commitments = compute_commitments(state)
        prior_street_commitment = (
            int(commitments['hero_total']) - int(commitments['hero_street'])
        )
        maximum = STACK_SIZE - prior_street_commitment
        minimum = int(state['street_last_bet_to']) + max(
            int(state['last_bet_size']), BIG_BLIND
        )
        target = min(max(int(target), minimum), maximum)
        if target >= maximum:
            return {
                'slot': 8,
                'increment': f'b{maximum}',
                'context': context,
                'hand': notation,
            }
        return {
            'slot': 7,
            'increment': f'b{target}',
            'context': context,
            'hand': notation,
        }

    if profile == 'pokerskill_sb_jamguard_v2' and context == 'facing_jam':
        if notation in {'AA', 'KK'}:
            return passive(1, 'c')
        return passive(0, 'f')

    if profile == 'pokerskill_v2':
        from heuristic_policy_v4 import PREFLOP_PERCENTILE

        percentile = float(PREFLOP_PERCENTILE[notation])
        if context == 'sb_open':
            if percentile < 0.65:
                return raise_to(250)
            if percentile < 0.935:
                return passive(1, 'c')
            return passive(0, 'f')
        if context == 'bb_vs_open':
            if percentile < 0.19:
                return raise_to(900)
            if percentile < 0.72:
                return passive(1, 'c')
            return passive(0, 'f')
        if context == 'bb_vs_limp':
            if percentile < 0.32:
                return raise_to(500)
            return passive(1, 'k')
        if context == 'sb_vs_3bet':
            if percentile < 0.08:
                return raise_to(2400)
            if percentile < 0.45:
                return passive(1, 'c')
            return passive(0, 'f')
        if context == 'sb_vs_limp_raise':
            if percentile < 0.08:
                return raise_to(1200)
            if percentile < 0.45:
                return passive(1, 'c')
            return passive(0, 'f')
        if context == 'bb_vs_4bet':
            if percentile < 0.03:
                return raise_to(9000)
            if percentile < 0.13:
                return passive(1, 'c')
            return passive(0, 'f')
        if context == 'facing_jam':
            if percentile < 0.025:
                return passive(1, 'c')
            return passive(0, 'f')
        if len(preflop_actions) >= 2:
            if percentile < 0.03:
                return raise_to(9000)
            if percentile < 0.13:
                return passive(1, 'c')
            return passive(0, 'f')
        return None

    if context == 'sb_open':
        if notation in {'82o', '72o', '62o', '52o', '42o', '32o'}:
            return passive(0, 'f')
        open_offsuit = (
            pair
            or (
                not suited
                and (
                    (high == 'A' and low_index >= ranks.index('3'))
                    or (high == 'K' and low_index >= ranks.index('3'))
                    or (high == 'Q' and low_index >= ranks.index('4'))
                    or (high == 'J' and low_index >= ranks.index('3'))
                    or (high == 'T' and low_index >= ranks.index('3'))
                    or (high == '9' and low_index >= ranks.index('2'))
                    or (high == '8' and low_index >= ranks.index('4'))
                    or (high == '7' and low_index >= ranks.index('4'))
                    or (high == '6' and low_index >= ranks.index('3'))
                    or notation in {'54o', '43o'}
                )
            )
        )
        open_suited = (
            suited
            and (
                high == 'A'
                or (high_index >= ranks.index('J') and low_index >= ranks.index('3'))
                or (
                    high_index - low_index <= 2
                    and low_index >= ranks.index('3')
                )
            )
        )
        if open_offsuit or open_suited:
            return raise_to(250)
        return passive(1, 'c')

    if profile in {'pokerskill_sb_v1', 'pokerskill_sb_jamguard_v2'}:
        return None

    if profile == 'pokerskill_sb_bbsize_v1':
        if int(source_action) != 7:
            return None
        if context == 'bb_vs_open':
            return raise_to(900)
        if context == 'bb_vs_limp':
            return raise_to(500)
        return None

    if context == 'bb_vs_open':
        three_bet = {
            'AA', 'KK', 'QQ', 'JJ', 'TT',
            'AKs', 'AQs', 'AJs', 'ATs', 'A5s', 'A2s',
            'KQs', 'KJs', 'KTs', 'QJs',
            'T9s', '98s', '87s', '76s', '65s', '86s', '97s',
        }
        call = {
            '99', '88', '77', '66', '55', '44', '33', '22',
            'A8s', 'A7s', 'A6s', 'A4s', 'A3s',
            'K9s', 'K8s', 'K7s', 'K6s', 'K5s', 'K4s', 'K3s', 'K2s',
            'Q9s', 'Q8s', 'Q7s', 'Q6s', 'Q5s', 'Q4s', 'Q3s',
            'J9s', 'J8s', 'J7s', 'J6s', 'J5s', 'J4s', 'J3s', 'J2s',
            'T8s', 'T7s', 'T6s', 'T5s', 'T4s', 'T3s', 'T2s',
            '54s', '43s',
            'ATo', 'A9o', 'A8o', 'A7o',
            'KJo', 'KTo', 'K9o', 'QJo', 'QTo', 'Q9o',
        }
        if notation in three_bet:
            return raise_to(900)
        if notation in call:
            return passive(1, 'c')
        return passive(0, 'f')

    if context == 'bb_vs_limp':
        raise_hands = {
            'AA', 'KK', 'QQ', 'JJ', 'TT', '99', '88', '77', '66',
            '55', '44', '33', '22',
            'AKs', 'AQs', 'AJs', 'ATs', 'A9s', 'A7s', 'A6s', 'A5s',
            'A4s', 'A3s', 'A2s',
            'KQs', 'KJs', 'KTs', 'QJs', 'QTs', 'JTs',
            'AKo', 'AQo', 'AJo', 'ATo', 'KQo',
            'T9s', '98s', '87s', '76s', '65s', '54s',
            '97s', '86s', '75s', '64s',
        }
        if notation in raise_hands:
            return raise_to(500)
        return passive(1, 'k')

    return None


def checkpoint_context_action_override(
    model,
    hole_cards: list,
    board: list,
    state: dict,
    client_pos: int,
    legal_mask: torch.Tensor,
    source_action: int,
) -> int:
    """Apply compact street/position/strength rules owned by a checkpoint."""
    config = getattr(model, 'policy_context_override', None)
    rules = config.get('rules') if isinstance(config, dict) else None
    if not isinstance(rules, list):
        return int(source_action)
    street = int(state.get('st', 0))
    commitments = compute_commitments(state)
    facing = int(float(commitments.get('to_call', 0.0)) > 0.0)
    to_call = float(commitments.get('to_call', 0.0))
    pot = max(float(commitments.get('pot', 0.0)), 1.0)
    to_call_pot_fraction = to_call / pot
    to_call_bb = to_call / float(BIG_BLIND)
    strength = None
    if street > 0:
        from heuristic_policy_v3 import _eval_postflop
        strength = int(_eval_postflop(hole_cards, board))
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_street = int(rule.get('street', -1))
        rule_position = int(rule.get('position', -1))
        rule_facing = int(rule.get('facing', -1))
        rule_strength = int(rule.get('strength', -1))
        minimum_call_fraction = float(
            rule.get('min_to_call_pot_fraction', float('-inf'))
        )
        maximum_call_fraction = float(
            rule.get('max_to_call_pot_fraction', float('inf'))
        )
        minimum_call_bb = float(
            rule.get('min_to_call_bb', float('-inf'))
        )
        maximum_call_bb = float(
            rule.get('max_to_call_bb', float('inf'))
        )
        replace = int(rule.get('replace_action', source_action))
        selected = int(rule.get('force_action', source_action))
        if (
            rule_street == street
            and (rule_position == -1 or rule_position == int(client_pos))
            and (rule_facing == -1 or rule_facing == facing)
            and (
                rule_strength == -1
                or (strength is not None and rule_strength == strength)
            )
            and minimum_call_fraction <= to_call_pot_fraction
            and to_call_pot_fraction < maximum_call_fraction
            and minimum_call_bb <= to_call_bb
            and to_call_bb < maximum_call_bb
            and int(source_action) == replace
            and 0 <= selected < legal_mask.shape[-1]
            and bool(legal_mask[0, selected].item() > 0.0)
        ):
            return selected
    return int(source_action)


@torch.no_grad()
def preflop_callguard_action(
    probs: torch.Tensor,
    legal_mask: torch.Tensor,
    state: dict,
    *,
    call_min_prob: float = 0.20,
    call_ratio: float = 0.65,
    include_open: bool = False,
) -> int | None:
    """Return slot 1 for close preflop call/defend spots, else None.

    This is a deterministic selector diagnostic, not a strategy override for
    official claims. It targets the observed failure mode where the policy puts
    meaningful probability on call, but pure argmax realizes a fold/raise-only
    preflop strategy.
    """
    if probs.ndim != 2 or probs.shape[-1] <= 1:
        return None
    if int(state.get('st', 0)) != 0:
        return None
    if bool(legal_mask[0, 1].item() <= 0.0):
        return None

    c = compute_commitments(state)
    if is_unopened_preflop_start(state) and not include_open:
        return None
    if c.get('to_call', 0) <= 0 and not include_open:
        return None

    legal_probs = probs * legal_mask
    top_prob = legal_probs.max(dim=-1).values
    call_prob = legal_probs[:, 1]
    choose_call = (
        (call_prob >= float(call_min_prob))
        & (call_prob >= float(call_ratio) * top_prob)
    )
    if bool(choose_call[0].item()):
        return 1
    return None


@torch.no_grad()
def decide_action(
    model,
    hole_cards,
    board,
    state: dict,
    client_pos: int,
    device: str,
    greedy: bool = True,
    temperature: float = 1.0,
    preflop_epsilon: float = 0.30,
    epsilon_streets: tuple[int, ...] = (0,),
    obs_version: str = 'v55',
    policy_mode: str = 'greedy',
    guarded_allin_max_spr: float = 2.0,
    guarded_allin_min_prob: float = 0.65,
    callguard_min_prob: float = 0.20,
    callguard_ratio: float = 0.65,
    callguard_include_open: bool = False,
    return_info: bool = False,
) -> int | tuple[int, dict]:
    """AlphaHoldem picks action (0-8)."""
    if hasattr(model, 'model_for_state'):
        model, obs_version = model.model_for_state(state, int(client_pos))
    elif hasattr(model, 'model_for_position'):
        model, obs_version = model.model_for_position(int(client_pos))
    current_pos = state['pos']
    st = state['st']

    # Encode tensors
    card_t = torch.tensor(encode_cards(hole_cards, board, st), device=device).unsqueeze(0)
    action_t = torch.tensor(
        encode_action_history(state, client_pos, current_pos, obs_version=obs_version),
        device=device,
    ).unsqueeze(0)

    c = compute_commitments(state)
    stacks = [STACK_SIZE - c['hero_total'], STACK_SIZE - c['opp_total']]
    extra_values = encode_extra(stacks)
    if (
        bool(getattr(model, 'requires_position_feature', False))
        or int(getattr(model, 'position_adapter_hidden', 0)) > 0
    ):
        extra_values = np.concatenate(
            [
                extra_values,
                np.asarray([float(client_pos)], dtype=np.float32),
            ]
        )
    extra_t = torch.tensor(extra_values, device=device).unsqueeze(0)

    raise_action_mapping = getattr(
        model,
        'raise_action_mapping',
        'legacy_total_over_pot',
    )
    mask = compute_legal_mask(state, raise_action_mapping)
    mask_t = torch.tensor(mask, device=device).unsqueeze(0)

    # Heuristic policy short-circuit: bypass encoded-tensor forward and decide
    # from high-level state (hole_cards, board, position, facing_bet).
    if hasattr(model, 'decide') and callable(getattr(model, 'decide')):
        state_with_call = {**state, 'to_call': int(c['to_call'])}
        selected = int(model.decide(
            hole_cards, board, state_with_call, client_pos, mask
        ))
        if not return_info:
            return selected
        return selected, {
            'policy_mode': 'heuristic',
            'temperature': float(temperature),
            'preflop_epsilon': float(preflop_epsilon),
            'legal_mask': [float(value) for value in mask],
            'behavior_probs': None,
            'behavior_action_probability': 1.0,
            'greedy_action_slot': selected,
        }

    logits, _ = model(card_t, action_t, extra_t, mask_t)
    logits = apply_checkpoint_policy_logit_bias(logits, model, state)
    if policy_mode not in ('greedy', 'greedy-guarded', 'preflop-callguard', 'preflop-epsilon', 'street-epsilon') or not greedy:
        logits = logits / max(float(temperature), 1e-6)
    probs = F.softmax(logits, dim=-1)
    greedy_action = int(torch.argmax(probs, dim=-1).item())
    range_override_action = checkpoint_preflop_range_override(
        model,
        hole_cards,
        state,
        client_pos,
        mask_t,
        greedy_action,
    )
    context_override_action = checkpoint_context_action_override(
        model,
        hole_cards,
        board,
        state,
        client_pos,
        mask_t,
        range_override_action,
    )
    behavior_probs = probs
    direct_increment = None

    if policy_mode == 'greedy' and greedy:
        selected = context_override_action
        profile_override = checkpoint_preflop_strategy_override(
            model,
            hole_cards,
            state,
            client_pos,
            mask_t,
            context_override_action,
        )
        if profile_override is not None:
            selected = int(profile_override['slot'])
            direct_increment = str(profile_override['increment'])
        behavior_probs = F.one_hot(
            torch.tensor([selected], device=probs.device),
            num_classes=probs.shape[-1],
        ).to(probs.dtype)

    elif policy_mode == 'greedy-guarded':
        probs = guarded_action_probs(
            probs,
            mask_t,
            state,
            allin_max_spr=guarded_allin_max_spr,
            allin_min_prob=guarded_allin_min_prob,
        )
        selected = int(torch.argmax(probs, dim=-1).item())
        behavior_probs = F.one_hot(
            torch.tensor([selected], device=probs.device),
            num_classes=probs.shape[-1],
        ).to(probs.dtype)

    elif policy_mode == 'preflop-callguard':
        if is_unopened_preflop_start(state) and not callguard_include_open:
            selected = greedy_action
        else:
            probs = guarded_action_probs(
                probs,
                mask_t,
                state,
                allin_max_spr=guarded_allin_max_spr,
                allin_min_prob=guarded_allin_min_prob,
            )
            callguard_action = preflop_callguard_action(
                probs,
                mask_t,
                state,
                call_min_prob=callguard_min_prob,
                call_ratio=callguard_ratio,
                include_open=callguard_include_open,
            )
            selected = (
                int(callguard_action)
                if callguard_action is not None
                else int(torch.argmax(probs, dim=-1).item())
            )
        behavior_probs = F.one_hot(
            torch.tensor([selected], device=probs.device),
            num_classes=probs.shape[-1],
        ).to(probs.dtype)

    elif policy_mode == 'guarded':
        probs = guarded_action_probs(
            probs,
            mask_t,
            state,
            allin_max_spr=guarded_allin_max_spr,
            allin_min_prob=guarded_allin_min_prob,
        )
        behavior_probs = probs
        from torch.distributions import Categorical
        selected = int(Categorical(probs).sample().item())
    elif policy_mode == 'preflop-mixed':
        if int(state.get('st', 0)) != 0:
            selected = greedy_action
            behavior_probs = F.one_hot(
                torch.tensor([selected], device=probs.device),
                num_classes=probs.shape[-1],
            ).to(probs.dtype)
        else:
            probs = guarded_action_probs(
                probs,
                mask_t,
                state,
                allin_max_spr=guarded_allin_max_spr,
                allin_min_prob=guarded_allin_min_prob,
            )
            behavior_probs = probs
            from torch.distributions import Categorical
            selected = int(Categorical(probs).sample().item())
    elif policy_mode in ('preflop-epsilon', 'street-epsilon'):
        explored_streets = (
            (0,) if policy_mode == 'preflop-epsilon' else epsilon_streets
        )
        if int(state.get('st', 0)) not in explored_streets:
            selected = greedy_action
            behavior_probs = F.one_hot(
                torch.tensor([selected], device=probs.device),
                num_classes=probs.shape[-1],
            ).to(probs.dtype)
        else:
            epsilon = min(max(float(preflop_epsilon), 0.0), 1.0)
            exploration_mask = mask_t.clone()
            commitments = compute_commitments(state)
            pot_after_call = max(
                float(commitments.get('pot', 0.0) + commitments.get('to_call', 0.0)),
                1.0,
            )
            spr = float(commitments.get('stack', 0.0)) / pot_after_call
            if (
                exploration_mask.shape[-1] > 8
                and spr > float(guarded_allin_max_spr)
                and bool(exploration_mask[0, :8].sum().item() > 0.0)
            ):
                exploration_mask[0, 8] = 0.0
            uniform = exploration_mask / exploration_mask.sum(
                dim=-1, keepdim=True
            ).clamp_min(1.0)
            source = F.one_hot(
                torch.tensor([greedy_action], device=probs.device),
                num_classes=probs.shape[-1],
            ).to(probs.dtype)
            behavior_probs = (1.0 - epsilon) * source + epsilon * uniform
            from torch.distributions import Categorical
            selected = int(Categorical(behavior_probs).sample().item())
    else:
        from torch.distributions import Categorical
        selected = int(Categorical(probs).sample().item())
        behavior_probs = probs

    if not return_info:
        return selected
    behavior_values = behavior_probs[0].detach().cpu().tolist()
    return selected, {
        'policy_mode': str(policy_mode),
        'temperature': float(temperature),
        'preflop_epsilon': float(preflop_epsilon),
        'legal_mask': [float(value) for value in mask],
        'behavior_probs': [float(value) for value in behavior_values],
        'behavior_action_probability': float(behavior_values[selected]),
        'greedy_action_slot': greedy_action,
        'direct_increment': direct_increment,
        'raise_action_mapping': raise_action_mapping,
    }


def _walk_action_string(action_str: str) -> list[tuple]:
    """Return list of (move_char, pos, amount, action_str_before_move, st, board_streets_revealed).
    board_streets_revealed = number of board-segments unlocked AFTER this move.
    Useful for reconstructing Slumbot's decision contexts post-hoc.
    """
    moves: list[tuple] = []
    if not action_str:
        return moves
    prefix = ''
    sz = len(action_str)
    i = 0
    last_action_str_before = ''
    while i < sz:
        action_str_before = action_str[:i]
        state = parse_action(action_str_before)
        if 'error' in state:
            break
        pos = state.get('pos', -1)
        st = state.get('st', 0)
        c = action_str[i]
        if c == 'b':
            j = i + 1
            while j < sz and action_str[j].isdigit():
                j += 1
            amount = int(action_str[i + 1:j])
            moves.append(('b', pos, amount, action_str_before, st))
            i = j
        elif c in 'kcf':
            moves.append((c, pos, 0, action_str_before, st))
            i += 1
        elif c == '/':
            i += 1
        else:
            i += 1
    return moves


def _board_for_street(board: list, st: int) -> list:
    if st <= 0:
        return []
    if st == 1:
        return board[:3]
    if st == 2:
        return board[:4]
    return board[:5]


def dump_hand_records(
    dump_fp,
    action_str: str,
    client_pos: int,
    hero_hole: list,
    opp_hole: list | None,
    board: list,
    winnings: int,
    hand_idx: int,
    hero_decision_trace: dict[str, dict] | None = None,
) -> None:
    """Walk completed hand's action_str and append one JSONL row per Slumbot decision."""
    if dump_fp is None:
        return
    opp_pos = 1 - client_pos
    # Dump BOTH hero and opponent moves (was: opp-only). 'who' field
    # distinguishes them so downstream analysis can do per-position breakdown.
    for move_idx, (mv, pos, amt, prefix, st) in enumerate(_walk_action_string(action_str)):
        is_hero_move = (pos == client_pos)
        st_state = parse_action(prefix)
        if 'error' in st_state:
            continue
        commit = compute_commitments({**st_state})
        record = {
            'hand_idx': hand_idx,
            'move_idx': move_idx,
            'who': 'hero' if is_hero_move else 'opp',
            'client_pos': client_pos,           # 0=hero BB, 1=hero SB
            'mover_pos': pos,                   # 0 or 1
            'action_str_before': prefix,
            'street': st,
            'board': _board_for_street(board, st),
            'opp_pos': opp_pos,
            'opp_hole': opp_hole,               # None if not shown down
            'hero_hole': hero_hole,
            'pot_before': commit['pot'],
            'to_call': commit['to_call'],
            'stack_remaining': commit['stack'],
            'last_bet_size': st_state.get('last_bet_size', 0),
            'street_last_bet_to': st_state.get('street_last_bet_to', 0),
            'total_last_bet_to': st_state.get('total_last_bet_to', 0),
            'action_move': mv,                  # 'b'=bet/raise, 'k'=check, 'c'=call, 'f'=fold
            'action_amount': amt,
            'winnings_hero': winnings,
            'showdown': opp_hole is not None,
        }
        if is_hero_move and hero_decision_trace is not None:
            decision = hero_decision_trace.get(prefix)
            if decision is not None:
                record.update({
                    'policy_action_slot': int(decision['selected_action_slot']),
                    'policy_mode': decision['policy_mode'],
                    'policy_temperature': float(decision['temperature']),
                    'policy_preflop_epsilon': float(
                        decision['preflop_epsilon']
                    ),
                    'policy_legal_mask': decision['legal_mask'],
                    'policy_behavior_probs': decision['behavior_probs'],
                    'policy_behavior_action_probability': float(
                        decision['behavior_action_probability']
                    ),
                    'policy_greedy_action_slot': int(
                        decision['greedy_action_slot']
                    ),
                })
        dump_fp.write(json.dumps(record) + '\n')
    dump_fp.flush()


def play_hand(
    model,
    token: str | None,
    device: str,
    verbose: bool = False,
    greedy: bool = True,
    temperature: float = 1.0,
    preflop_epsilon: float = 0.30,
    epsilon_streets: tuple[int, ...] = (0,),
    obs_version: str = 'v55',
    policy_mode: str = 'greedy',
    guarded_allin_max_spr: float = 2.0,
    guarded_allin_min_prob: float = 0.65,
    callguard_min_prob: float = 0.20,
    callguard_ratio: float = 0.65,
    callguard_include_open: bool = False,
    dump_fp=None,
    hand_idx: int = 0,
):
    r = new_hand(token)
    token = r.get('token', token)
    last_action_str = ''
    last_hero_hole: list = []
    last_board: list = []
    last_client_pos = 0
    hero_decision_trace: dict[str, dict] = {}

    while True:
        action_str = r.get('action', '')
        client_pos = r.get('client_pos', 0)
        hole_cards = r.get('hole_cards', [])
        board = r.get('board', [])
        winnings = r.get('winnings')

        if winnings is not None:
            if verbose:
                print(f'  Hand ended. Winnings: {winnings} chips ({winnings/BIG_BLIND:+.2f} BB)')
            opp_hole = r.get('bot_hole_cards')
            final_action = action_str or last_action_str
            final_board = board or last_board
            final_hero_hole = hole_cards or last_hero_hole
            final_client_pos = client_pos if action_str else last_client_pos
            dump_hand_records(
                dump_fp, final_action, final_client_pos,
                final_hero_hole, opp_hole, final_board, winnings, hand_idx,
                hero_decision_trace,
            )
            return token, winnings

        last_action_str = action_str
        last_hero_hole = hole_cards
        last_board = board
        last_client_pos = client_pos
        state = parse_action(action_str)
        if 'error' in state:
            print(f'Parse error: {state["error"]}')
            return token, 0

        # Our turn?
        if state['pos'] != client_pos:
            # This shouldn't happen if API behaves correctly — but fold as safety
            if verbose:
                print(f'  WARN: pos={state["pos"]} client_pos={client_pos} — folding')
            try:
                r = act(token, 'f' if state['last_bet_size'] > 0 else 'k')
                continue
            except Exception as e:
                print(f'  ERROR forcing action: {e}')
                return token, -state.get('total_last_bet_to', 0)

        # AlphaHoldem decides
        action_idx, decision_info = decide_action(
            model, hole_cards, board, state, client_pos, device,
            greedy=greedy,
            temperature=temperature,
            preflop_epsilon=preflop_epsilon,
            epsilon_streets=epsilon_streets,
            obs_version=obs_version,
            policy_mode=policy_mode,
            guarded_allin_max_spr=guarded_allin_max_spr,
            guarded_allin_min_prob=guarded_allin_min_prob,
            callguard_min_prob=callguard_min_prob,
            callguard_ratio=callguard_ratio,
            callguard_include_open=callguard_include_open,
            return_info=True,
        )
        hero_decision_trace[action_str] = {
            **decision_info,
            'selected_action_slot': int(action_idx),
        }
        incr = (
            decision_info.get('direct_increment')
            or action_idx_to_incr(
                action_idx,
                state,
                decision_info.get(
                    'raise_action_mapping',
                    'legacy_total_over_pot',
                ),
            )
        )

        if verbose:
            print(f'  Street {state["st"]} | action history: "{action_str}"')
            print(f'  Hole: {hole_cards} Board: {board} | AH chose slot {action_idx} → "{incr}"')

        try:
            r = act(token, incr)
        except requests.HTTPError as e:
            print(f'HTTP error on act: {e}')
            # Try folding instead
            try:
                r = act(token, 'f' if state['last_bet_size'] > 0 else 'k')
            except Exception:
                return token, -state['total_last_bet_to']


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='models/alpha_holdem_v3.pt')
    parser.add_argument('--hands', type=int, default=1000)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--verbose', action='store_true')
    parser.add_argument('--greedy', action='store_true', default=True)
    parser.add_argument('--sample', action='store_true',
                        help='Sample from the policy instead of taking argmax')
    parser.add_argument('--policy-mode', choices=('greedy', 'greedy-guarded', 'preflop-callguard', 'sample', 'guarded', 'preflop-mixed', 'preflop-epsilon', 'street-epsilon'), default='greedy',
                        help='Action selection for model strategy. --sample is kept as an alias for policy-mode=sample.')
    parser.add_argument('--temperature', type=float, default=1.0,
                        help='Sampling temperature when policy-mode is sample or guarded.')
    parser.add_argument('--preflop-epsilon', type=float, default=0.30,
                        help='Uniform legal-action exploration fraction for policy-mode=preflop-epsilon.')
    parser.add_argument('--epsilon-streets', default='0',
                        help='Comma-separated streets (0=preflop,...,3=river) explored by policy-mode=street-epsilon.')
    parser.add_argument('--guarded-allin-max-spr', type=float, default=2.0,
                        help='Guarded selector suppresses all-in above this SPR unless model confidence is high.')
    parser.add_argument('--guarded-allin-min-prob', type=float, default=0.65,
                        help='Guarded selector keeps high-SPR all-in only when raw all-in probability reaches this.')
    parser.add_argument('--callguard-min-prob', type=float, default=0.20,
                        help='preflop-callguard chooses call only if call probability is at least this value.')
    parser.add_argument('--callguard-ratio', type=float, default=0.65,
                        help='preflop-callguard chooses call only if call probability is at least this fraction of the top legal probability.')
    parser.add_argument('--callguard-include-open', action='store_true',
                        help='Allow preflop-callguard on unopened SB spots too. Default restricts it to facing-bet defense.')
    parser.add_argument('--obs-version', choices=('auto', 'v4', 'v55'), default='auto',
                        help='Observation encoder. auto uses checkpoint metadata.')
    parser.add_argument('--dump-slumbot', default=None,
                        help='JSONL path. If set, one row per Slumbot decision is appended.')
    parser.add_argument('--result-json', default=None,
                        help='Write benchmark summary statistics to this JSON path.')
    parser.add_argument('--hand-results-jsonl', default=None,
                        help='Write one JSONL row per successful hand for exact CI/audit replay.')
    parser.add_argument('--strategy', choices=['model', 'ensemble', 'seat_hybrid', 'postflop_hybrid', 'sb_preflop_hybrid', 'sb_open_hybrid', 'postflop_heuristic_v3', 'preflop_heuristic_v4', 'preflop_heuristic_v4_nolimp', 'fold', 'call', 'random', 'heuristic', 'heuristic_v2', 'heuristic_v3', 'heuristic_v3_1', 'heuristic_v4'], default='model',
                        help='Action policy. model=trained NN (default). fold/call/random=fixed baselines. '
                             'heuristic=v1. heuristic_v2=BB flat-call. heuristic_v3=polarized BB (1.5x raise). '
                             'heuristic_v3_1=v3 + BB jam-first sizing (diagnostic for fold-equity hypothesis). '
                             'heuristic_v4=wide positional ranges + OOP flop defense. '
                             'ensemble=greedy over the mean probabilities of frozen checkpoints. '
                             'seat_hybrid=separate frozen SB and BB checkpoints. '
                             'postflop_hybrid=fallback checkpoint preflop, primary checkpoint postflop. '
                             'sb_preflop_hybrid=fallback checkpoint only for SB preflop, primary checkpoint otherwise. '
                             'sb_open_hybrid=fallback checkpoint only for the unopened SB root action. '
                             'postflop_heuristic_v3=fallback checkpoint preflop, heuristic-v3 postflop. '
                             'preflop_heuristic_v4=heuristic-v4 preflop, checkpoint postflop. '
                             'preflop_heuristic_v4_nolimp=same hybrid with bottom-range SB open-limps folded.')
    parser.add_argument('--ensemble-models', default=None,
                        help='Comma-separated checkpoints for strategy=ensemble.')
    parser.add_argument('--sb-model', default=None,
                        help='SB checkpoint for strategy=seat_hybrid.')
    parser.add_argument('--bb-model', default=None,
                        help='BB checkpoint for strategy=seat_hybrid.')
    parser.add_argument('--fallback-model', default=None,
                        help='Preflop checkpoint for strategy=postflop_hybrid.')
    args = parser.parse_args()
    epsilon_streets = tuple(sorted({
        int(value.strip())
        for value in str(args.epsilon_streets).split(',')
        if value.strip()
    }))
    if any(street < 0 or street > 3 for street in epsilon_streets):
        raise SystemExit('--epsilon-streets values must be between 0 and 3')

    device = args.device
    print(f'Device: {device}')

    class _ConstantPolicyNet(torch.nn.Module):
        """Fake AlphaHoldemNet that ignores inputs and returns a fixed action preference.
        Used for baseline benches (fold-only / call-only / uniform-legal).

        For random strategy (prefer_slot=None), uses fresh random logits each call so
        greedy argmax picks a random legal action (otherwise argmax over zeros is
        deterministic on the lowest-index legal slot)."""
        def __init__(self, prefer_slot, num_actions=NUM_ACTIONS):
            super().__init__()
            self.prefer_slot = prefer_slot
            self.num_actions = num_actions

        def forward(self, card, action_inp, extra, legal_mask=None):
            B = card.shape[0]
            if self.prefer_slot is None:
                # Random: fresh draws each call so argmax over legal actions varies.
                logits = torch.randn(B, self.num_actions, device=card.device)
            else:
                logits = torch.zeros(B, self.num_actions, device=card.device)
                logits[:, self.prefer_slot] = 1e6
            if legal_mask is not None:
                logits = logits + (1 - legal_mask) * (-1e9)
            value = torch.zeros(B, 1, device=card.device)
            return logits, value

    def load_checkpoint_model(path):
        checkpoint = torch.load(path, map_location=device, weights_only=False)
        norm = checkpoint.get('norm_layer', 'bn')
        model_state = checkpoint.get('model', {})
        def build_checkpoint_actor(actor_checkpoint):
            actor_state = actor_checkpoint.get('model', {})
            actor_norm = actor_checkpoint.get('norm_layer', 'bn')
            actor_separate_preflop_head = bool(
                actor_checkpoint.get('separate_preflop_head')
                or (actor_checkpoint.get('config') or {}).get(
                    'separate_preflop_head'
                )
                or 'preflop_policy_head.weight' in actor_state
            )
            actor_position_adapter_hidden = int(
                actor_checkpoint.get('position_adapter_hidden')
                or (actor_checkpoint.get('config') or {}).get(
                    'position_adapter_hidden'
                )
                or (
                    actor_state[
                        'position_policy_adapters.0.0.weight'
                    ].shape[0]
                    if 'position_policy_adapters.0.0.weight' in actor_state
                    else 0
                )
            )
            actor = AlphaHoldemNet(
                num_actions=NUM_ACTIONS,
                norm_layer=actor_norm,
                separate_preflop_head=actor_separate_preflop_head,
                position_adapter_hidden=actor_position_adapter_hidden,
                critic_contract=str(
                    actor_checkpoint.get('critic_contract')
                    or (actor_checkpoint.get('config') or {}).get(
                        'critic_contract'
                    )
                    or 'critic_v1'
                ),
            ).to(device)
            actor.eval()
            actor(
                torch.zeros(2, 6, 4, 13, device=device),
                torch.zeros(2, 25, 4, 5, device=device),
                torch.zeros(
                    2,
                    3 if actor_position_adapter_hidden > 0 else 2,
                    device=device,
                ),
            )
            actor.load_state_dict(actor_state)
            return actor

        if checkpoint.get('architecture') == 'dual_seat_v1':
            from alpha_holdem.network_dual_seat import (
                DualSeatAlphaHoldemNet,
            )

            def load_seat_actor(prefix):
                seat_state = {
                    key[len(prefix):]: value
                    for key, value in model_state.items()
                    if key.startswith(prefix)
                }
                seat_checkpoint = {
                    **checkpoint,
                    'architecture': None,
                    'model': seat_state,
                }
                return build_checkpoint_actor(seat_checkpoint)

            net = DualSeatAlphaHoldemNet(
                sb_model=load_seat_actor('sb_model.'),
                bb_model=load_seat_actor('bb_model.'),
            ).to(device)
            net.eval()
            net.raise_action_mapping = checkpoint.get(
                'raise_action_mapping',
                'legacy_total_over_pot',
            )
            return net, checkpoint, norm

        separate_preflop_head = bool(
            checkpoint.get('separate_preflop_head')
            or (checkpoint.get('config') or {}).get('separate_preflop_head')
            or 'preflop_policy_head.weight' in model_state
        )
        preflop_adapter_hidden = int(
            checkpoint.get('preflop_adapter_hidden')
            or (checkpoint.get('config') or {}).get('preflop_adapter_hidden')
            or (
                model_state['preflop_policy_adapter.0.weight'].shape[0]
                if 'preflop_policy_adapter.0.weight' in model_state
                else 0
            )
        )
        preflop_raw_adapter_hidden = int(
            checkpoint.get('preflop_raw_adapter_hidden')
            or (checkpoint.get('config') or {}).get(
                'preflop_raw_adapter_hidden'
            )
            or (
                model_state[
                    'preflop_raw_policy_adapter.0.weight'
                ].shape[0]
                if 'preflop_raw_policy_adapter.0.weight' in model_state
                else 0
            )
        )
        preflop_raw_action_scale = float(
            checkpoint.get('preflop_raw_action_scale')
            or (checkpoint.get('config') or {}).get(
                'preflop_raw_action_scale'
            )
            or 1.0
        )
        preflop_raw_gate = str(
            checkpoint.get('preflop_raw_gate')
            or (checkpoint.get('config') or {}).get('preflop_raw_gate')
            or 'none'
        )
        flop_adapter_hidden = int(
            checkpoint.get('flop_adapter_hidden')
            or (checkpoint.get('config') or {}).get('flop_adapter_hidden')
            or (
                model_state['flop_policy_adapter.0.weight'].shape[0]
                if 'flop_policy_adapter.0.weight' in model_state
                else 0
            )
        )
        postflop_adapter_hidden = int(
            checkpoint.get('postflop_adapter_hidden')
            or (checkpoint.get('config') or {}).get('postflop_adapter_hidden')
            or (
                model_state['postflop_policy_adapter.0.weight'].shape[0]
                if 'postflop_policy_adapter.0.weight' in model_state
                else 0
            )
        )
        position_adapter_hidden = int(
            checkpoint.get('position_adapter_hidden')
            or (checkpoint.get('config') or {}).get(
                'position_adapter_hidden'
            )
            or (
                model_state[
                    'position_policy_adapters.0.0.weight'
                ].shape[0]
                if 'position_policy_adapters.0.0.weight' in model_state
                else 0
            )
        )
        critic_contract = str(
            checkpoint.get('critic_contract')
            or (checkpoint.get('config') or {}).get('critic_contract')
            or 'critic_v1'
        )
        net = AlphaHoldemNet(
            num_actions=NUM_ACTIONS,
            norm_layer=norm,
            separate_preflop_head=separate_preflop_head,
            preflop_adapter_hidden=preflop_adapter_hidden,
            preflop_raw_adapter_hidden=preflop_raw_adapter_hidden,
            preflop_raw_action_scale=preflop_raw_action_scale,
            preflop_raw_gate=preflop_raw_gate,
            flop_adapter_hidden=flop_adapter_hidden,
            postflop_adapter_hidden=postflop_adapter_hidden,
            position_adapter_hidden=position_adapter_hidden,
            critic_contract=critic_contract,
        ).to(device)
        net.eval()
        net(
            torch.zeros(2, 6, 4, 13, device=device),
            torch.zeros(2, 25, 4, 5, device=device),
            torch.zeros(
                2,
                3 if position_adapter_hidden > 0 else 2,
                device=device,
            ),
        )
        net.load_state_dict(checkpoint['model'])
        net.policy_logit_bias = checkpoint.get('policy_logit_bias')
        net.policy_range_override = checkpoint.get('policy_range_override')
        net.policy_context_override = checkpoint.get('policy_context_override')
        net.preflop_strategy_profile = checkpoint.get(
            'preflop_strategy_profile'
        )
        net.raise_action_mapping = checkpoint.get(
            'raise_action_mapping',
            (
                'pot_fraction_v2'
                if checkpoint.get('action_space_version')
                == '9slot_pot_fraction_v2'
                else 'legacy_total_over_pot'
            ),
        )
        net.eval()
        return net, checkpoint, norm

    class _SeatHybridPolicy(torch.nn.Module):
        def __init__(self, sb_model, bb_model, sb_obs_version, bb_obs_version):
            super().__init__()
            self.sb_model = sb_model
            self.bb_model = bb_model
            self.sb_obs_version = sb_obs_version
            self.bb_obs_version = bb_obs_version

        def model_for_position(self, client_pos):
            if int(client_pos) == 1:
                return self.sb_model, self.sb_obs_version
            return self.bb_model, self.bb_obs_version

    class _PostflopHybridPolicy(torch.nn.Module):
        def __init__(
            self,
            postflop_model,
            preflop_model,
            postflop_obs_version,
            preflop_obs_version,
        ):
            super().__init__()
            self.postflop_model = postflop_model
            self.preflop_model = preflop_model
            self.postflop_obs_version = postflop_obs_version
            self.preflop_obs_version = preflop_obs_version

        def model_for_state(self, state, client_pos):
            # parse_action exposes the current street as ``st``.  Accept the
            # verbose alias for synthetic callers, but never silently default a
            # real postflop state to preflop.
            street = current_street_index(state)
            if street == 0:
                return self.preflop_model, self.preflop_obs_version
            return self.postflop_model, self.postflop_obs_version

    class _SBPreflopHybridPolicy(torch.nn.Module):
        def __init__(
            self,
            base_model,
            sb_preflop_model,
            base_obs_version,
            sb_preflop_obs_version,
            open_only=False,
        ):
            super().__init__()
            self.base_model = base_model
            self.sb_preflop_model = sb_preflop_model
            self.base_obs_version = base_obs_version
            self.sb_preflop_obs_version = sb_preflop_obs_version
            self.open_only = bool(open_only)

        def model_for_state(self, state, client_pos):
            use_sb_preflop = (
                current_street_index(state) == 0
                and int(client_pos) == 1
                and (not self.open_only or is_unopened_preflop_start(state))
            )
            if use_sb_preflop:
                return self.sb_preflop_model, self.sb_preflop_obs_version
            return self.base_model, self.base_obs_version

    if args.strategy == 'model':
        print(f'Loading model from {args.model}...')
        model, ckpt, ckpt_norm = load_checkpoint_model(args.model)
    elif args.strategy == 'ensemble':
        ensemble_paths = [
            value.strip()
            for value in str(args.ensemble_models or '').split(',')
            if value.strip()
        ]
        if len(ensemble_paths) < 2:
            raise SystemExit(
                'strategy=ensemble requires at least two --ensemble-models'
            )
        members = []
        member_checkpoints = []
        member_norms = []
        member_obs_versions = []
        for path in ensemble_paths:
            member, member_checkpoint, member_norm = load_checkpoint_model(path)
            if getattr(member, 'policy_logit_bias', None) is not None:
                raise SystemExit(
                    'strategy=ensemble does not support checkpoint logit bias: '
                    f'{path}'
                )
            members.append(member)
            member_checkpoints.append(member_checkpoint)
            member_norms.append(member_norm)
            member_obs_versions.append(
                resolve_obs_version(member_checkpoint, 'auto')
            )
        if len(set(member_obs_versions)) != 1:
            raise SystemExit(
                'strategy=ensemble requires one shared observation version; '
                f'got {member_obs_versions}'
            )
        model = ProbabilityEnsemblePolicy(members).to(device)
        model.eval()
        ckpt = {
            'env_version': 'probability_ensemble',
            'obs_version': member_obs_versions[0],
            'ensemble_models': ensemble_paths,
            'ensemble_method': 'mean_probability_then_greedy',
        }
        ckpt_norm = ','.join(str(value) for value in member_norms)
        print(
            'Strategy: PROBABILITY ENSEMBLE '
            f'obs={member_obs_versions[0]} members={ensemble_paths}'
        )
    elif args.strategy == 'seat_hybrid':
        if not args.sb_model or not args.bb_model:
            raise SystemExit('strategy=seat_hybrid requires --sb-model and --bb-model')
        sb_model, sb_ckpt, sb_norm = load_checkpoint_model(args.sb_model)
        bb_model, bb_ckpt, bb_norm = load_checkpoint_model(args.bb_model)
        sb_obs = resolve_obs_version(sb_ckpt, 'auto')
        bb_obs = resolve_obs_version(bb_ckpt, 'auto')
        model = _SeatHybridPolicy(sb_model, bb_model, sb_obs, bb_obs).to(device)
        ckpt = {
            'env_version': 'seat_hybrid',
            # The wrapper overrides this per position inside decide_action.
            # A valid fallback keeps the shared result/report path compatible.
            'obs_version': 'v4',
            'sb_model': str(args.sb_model),
            'bb_model': str(args.bb_model),
        }
        ckpt_norm = f'sb={sb_norm},bb={bb_norm}'
        print(
            f'Strategy: SEAT HYBRID SB={args.sb_model} ({sb_obs}) '
            f'BB={args.bb_model} ({bb_obs})'
        )
    elif args.strategy == 'postflop_hybrid':
        if not args.model or not args.fallback_model:
            raise SystemExit(
                'strategy=postflop_hybrid requires --model and --fallback-model'
            )
        postflop_model, postflop_ckpt, postflop_norm = load_checkpoint_model(
            args.model
        )
        preflop_model, preflop_ckpt, preflop_norm = load_checkpoint_model(
            args.fallback_model
        )
        postflop_obs = resolve_obs_version(postflop_ckpt, 'auto')
        preflop_obs = resolve_obs_version(preflop_ckpt, 'auto')
        model = _PostflopHybridPolicy(
            postflop_model,
            preflop_model,
            postflop_obs,
            preflop_obs,
        ).to(device)
        ckpt = {
            'env_version': 'postflop_hybrid',
            'obs_version': preflop_obs,
            'postflop_model': str(args.model),
            'preflop_model': str(args.fallback_model),
        }
        ckpt_norm = f'postflop={postflop_norm},preflop={preflop_norm}'
        print(
            f'Strategy: POSTFLOP HYBRID preflop={args.fallback_model} '
            f'({preflop_obs}) postflop={args.model} ({postflop_obs})'
        )
    elif args.strategy == 'sb_preflop_hybrid':
        if not args.model or not args.fallback_model:
            raise SystemExit(
                'strategy=sb_preflop_hybrid requires --model and '
                '--fallback-model'
            )
        base_model, base_ckpt, base_norm = load_checkpoint_model(args.model)
        sb_preflop_model, sb_preflop_ckpt, sb_preflop_norm = (
            load_checkpoint_model(args.fallback_model)
        )
        base_obs = resolve_obs_version(base_ckpt, 'auto')
        sb_preflop_obs = resolve_obs_version(sb_preflop_ckpt, 'auto')
        model = _SBPreflopHybridPolicy(
            base_model,
            sb_preflop_model,
            base_obs,
            sb_preflop_obs,
        ).to(device)
        ckpt = {
            'env_version': 'sb_preflop_hybrid',
            'obs_version': base_obs,
            'base_model': str(args.model),
            'sb_preflop_model': str(args.fallback_model),
        }
        ckpt_norm = f'base={base_norm},sb_preflop={sb_preflop_norm}'
        print(
            f'Strategy: SB-PREFLOP HYBRID sb_preflop={args.fallback_model} '
            f'({sb_preflop_obs}) base={args.model} ({base_obs})'
        )
    elif args.strategy == 'sb_open_hybrid':
        if not args.model or not args.fallback_model:
            raise SystemExit(
                'strategy=sb_open_hybrid requires --model and '
                '--fallback-model'
            )
        base_model, base_ckpt, base_norm = load_checkpoint_model(args.model)
        sb_open_model, sb_open_ckpt, sb_open_norm = load_checkpoint_model(
            args.fallback_model
        )
        base_obs = resolve_obs_version(base_ckpt, 'auto')
        sb_open_obs = resolve_obs_version(sb_open_ckpt, 'auto')
        model = _SBPreflopHybridPolicy(
            base_model,
            sb_open_model,
            base_obs,
            sb_open_obs,
            open_only=True,
        ).to(device)
        ckpt = {
            'env_version': 'sb_open_hybrid',
            'obs_version': base_obs,
            'base_model': str(args.model),
            'sb_open_model': str(args.fallback_model),
        }
        ckpt_norm = f'base={base_norm},sb_open={sb_open_norm}'
        print(
            f'Strategy: SB-OPEN HYBRID sb_open={args.fallback_model} '
            f'({sb_open_obs}) base={args.model} ({base_obs})'
        )
    elif args.strategy == 'postflop_heuristic_v3':
        if not args.fallback_model:
            raise SystemExit(
                'strategy=postflop_heuristic_v3 requires --fallback-model'
            )
        from heuristic_policy_v3 import HeuristicV3Policy
        preflop_model, preflop_ckpt, preflop_norm = load_checkpoint_model(
            args.fallback_model
        )
        preflop_obs = resolve_obs_version(preflop_ckpt, 'auto')
        postflop_model = HeuristicV3Policy().to(device)
        model = _PostflopHybridPolicy(
            postflop_model,
            preflop_model,
            'v4',
            preflop_obs,
        ).to(device)
        ckpt = {
            'env_version': 'postflop_heuristic_v3',
            'obs_version': preflop_obs,
            'postflop_policy': 'heuristic_v3',
            'preflop_model': str(args.fallback_model),
        }
        ckpt_norm = f'postflop=heuristic_v3,preflop={preflop_norm}'
        print(
            f'Strategy: BC PREFLOP + HEURISTIC-V3 POSTFLOP '
            f'preflop={args.fallback_model} ({preflop_obs})'
        )
    elif args.strategy in ('preflop_heuristic_v4', 'preflop_heuristic_v4_nolimp'):
        if not args.model:
            raise SystemExit(
                'strategy=preflop_heuristic_v4 requires --model'
            )
        from heuristic_policy_v4 import (
            HeuristicV4NoLimpPolicy,
            HeuristicV4Policy,
        )
        postflop_model, postflop_ckpt, postflop_norm = load_checkpoint_model(
            args.model
        )
        postflop_obs = resolve_obs_version(postflop_ckpt, 'auto')
        preflop_model = (
            HeuristicV4NoLimpPolicy()
            if args.strategy == 'preflop_heuristic_v4_nolimp'
            else HeuristicV4Policy()
        ).to(device)
        model = _PostflopHybridPolicy(
            postflop_model,
            preflop_model,
            postflop_obs,
            'v4',
        ).to(device)
        ckpt = {
            'env_version': args.strategy,
            'obs_version': 'v4',
            'preflop_policy': (
                'heuristic_v4_nolimp'
                if args.strategy == 'preflop_heuristic_v4_nolimp'
                else 'heuristic_v4'
            ),
            'postflop_model': str(args.model),
        }
        ckpt_norm = f'preflop=heuristic_v4,postflop={postflop_norm}'
        print(
            f'Strategy: {args.strategy} + CHECKPOINT POSTFLOP '
            f'postflop={args.model} ({postflop_obs})'
        )
    elif args.strategy == 'heuristic':
        from heuristic_policy import HeuristicPolicy
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        model = HeuristicPolicy().to(device)
        print(f'Strategy: HEURISTIC v1 (tight-passive; pos-bug-fixed; treys required for postflop)')
    elif args.strategy == 'heuristic_v2':
        from heuristic_policy_v2 import HeuristicV2Policy
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        model = HeuristicV2Policy().to(device)
        print(f'Strategy: HEURISTIC v2 (tighter; BB flat-call range; size-aware postflop)')
    elif args.strategy == 'heuristic_v3':
        from heuristic_policy_v3 import HeuristicV3Policy
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        model = HeuristicV3Policy().to(device)
        print(f'Strategy: HEURISTIC v3 (v2 SB + Path B polarized BB; no flat-call BB)')
    elif args.strategy == 'heuristic_v3_1':
        from heuristic_policy_v3_1 import HeuristicV3_1Policy
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        model = HeuristicV3_1Policy().to(device)
        print(f'Strategy: HEURISTIC v3.1 (v3 + BB jam-first sizing; diagnostic for fold-equity hypothesis)')
    elif args.strategy == 'heuristic_v4':
        from heuristic_policy_v4 import HeuristicV4Policy
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        model = HeuristicV4Policy().to(device)
        print('Strategy: HEURISTIC v4 (wide positional preflop ranges + OOP flop defense)')
    else:
        # Baseline strategies — no checkpoint load. Slot map (vec_game_state):
        #   0=fold, 1=check/call, 2..7=raise sizes, 8=all-in.
        ckpt = {'env_version': 'v4'}
        ckpt_norm = 'n/a'
        if args.strategy == 'fold':
            prefer = 0  # mask kills it when no bet to face → falls back to slot 1 via softmax
        elif args.strategy == 'call':
            prefer = 1
        elif args.strategy == 'random':
            prefer = None  # uniform legal: all logits 0 → softmax uniform → masked to legal
        else:
            raise ValueError(f'Unknown strategy: {args.strategy}')
        model = _ConstantPolicyNet(prefer_slot=prefer).to(device)
        print(f'Strategy: BASELINE "{args.strategy}" (no checkpoint)')
    model.eval()
    print(f'  norm_layer={ckpt_norm}')
    print(f'Loaded (params: {count_parameters(model):,})')
    obs_version = resolve_obs_version(ckpt, args.obs_version)
    policy_mode = 'sample' if args.sample else args.policy_mode
    greedy = policy_mode in ('greedy', 'greedy-guarded', 'preflop-callguard')
    if policy_mode == 'greedy':
        mode = 'greedy'
    elif policy_mode == 'greedy-guarded':
        mode = (
            f'greedy-guarded/'
            f'allin_spr>{args.guarded_allin_max_spr:g}/'
            f'allin_p<{args.guarded_allin_min_prob:g}'
        )
    elif policy_mode == 'preflop-callguard':
        include = 'include_open' if args.callguard_include_open else 'facing_only'
        mode = (
            f'preflop-callguard/'
            f'min_p={args.callguard_min_prob:g}/'
            f'ratio={args.callguard_ratio:g}/'
            f'{include}/'
            f'allin_spr>{args.guarded_allin_max_spr:g}/'
            f'allin_p<{args.guarded_allin_min_prob:g}'
        )
    elif policy_mode == 'guarded':
        mode = (
            f'guarded/temp={args.temperature:g}/'
            f'allin_spr>{args.guarded_allin_max_spr:g}/'
            f'allin_p<{args.guarded_allin_min_prob:g}'
        )
    elif policy_mode == 'preflop-mixed':
        mode = (
            f'preflop-mixed/temp={args.temperature:g}/'
            f'allin_spr>{args.guarded_allin_max_spr:g}/'
            f'allin_p<{args.guarded_allin_min_prob:g}/'
            'postflop=greedy'
        )
    elif policy_mode == 'preflop-epsilon':
        mode = (
            f'preflop-epsilon/epsilon={args.preflop_epsilon:g}/'
            f'allin_spr>{args.guarded_allin_max_spr:g}/'
            'postflop=greedy'
        )
    elif policy_mode == 'street-epsilon':
        mode = (
            f'street-epsilon/streets={",".join(map(str, epsilon_streets))}/'
            f'epsilon={args.preflop_epsilon:g}/'
            f'allin_spr>{args.guarded_allin_max_spr:g}'
        )
    else:
        mode = f'sample/temp={args.temperature:g}'
    print(f'Observation encoding: {obs_version} | policy mode: {mode}')

    print(f'\nPlaying {args.hands} hands vs Slumbot...')
    print('-' * 60)

    token = None
    total_chips = 0
    hand_winnings = []
    t0 = time.time()

    dump_fp = None
    if args.dump_slumbot:
        dump_path = Path(args.dump_slumbot)
        dump_path.parent.mkdir(parents=True, exist_ok=True)
        dump_fp = dump_path.open('a', encoding='utf-8')
        print(f'Dumping Slumbot decisions to {dump_path}')

    hand_results_fp = None
    if args.hand_results_jsonl:
        hand_results_path = Path(args.hand_results_jsonl)
        hand_results_path.parent.mkdir(parents=True, exist_ok=True)
        hand_results_fp = hand_results_path.open('a', encoding='utf-8')
        print(f'Dumping per-hand results to {hand_results_path}')

    if args.hands <= 0:
        if dump_fp is not None:
            dump_fp.close()
        if hand_results_fp is not None:
            hand_results_fp.close()
        print('Dry-run complete: model and selector loaded; no Slumbot hands requested.')
        if args.result_json:
            result_path = Path(args.result_json)
            result_path.parent.mkdir(parents=True, exist_ok=True)
            result = {
                'model': args.model,
                'strategy': args.strategy,
                'requested_hands': int(args.hands),
                'successful_hands': 0,
                'dry_run': True,
                'device': args.device,
                'obs_version': obs_version,
                'policy_mode': mode,
                'policy_mode_raw': policy_mode,
                'guarded_allin_max_spr': float(args.guarded_allin_max_spr),
                'guarded_allin_min_prob': float(args.guarded_allin_min_prob),
                'callguard_min_prob': float(args.callguard_min_prob),
                'callguard_ratio': float(args.callguard_ratio),
                'callguard_include_open': bool(args.callguard_include_open),
                'total_chips': 0,
                'avg_bb_per_hand': None,
                'bb_per_100': None,
                'mbb_per_hand': None,
                'std_bb_per_hand': None,
                'ci95_bb_per_hand': None,
                'ci95_bb_per_100': None,
                'lower_bound_bb_per_100': None,
                'upper_bound_bb_per_100': None,
                'significant_winner': None,
                'elapsed_seconds': float(time.time() - t0),
                'hands_per_minute': None,
            }
            result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
            print(f'Wrote result JSON: {result_path}')
        return

    for h in range(args.hands):
        try:
            token, winnings = play_hand(
                model, token, device,
                verbose=args.verbose,
                greedy=greedy,
                temperature=args.temperature,
                preflop_epsilon=args.preflop_epsilon,
                epsilon_streets=epsilon_streets,
                obs_version=obs_version,
                policy_mode=policy_mode,
                guarded_allin_max_spr=args.guarded_allin_max_spr,
                guarded_allin_min_prob=args.guarded_allin_min_prob,
                callguard_min_prob=args.callguard_min_prob,
                callguard_ratio=args.callguard_ratio,
                callguard_include_open=args.callguard_include_open,
                dump_fp=dump_fp,
                hand_idx=h,
            )
            total_chips += winnings
            hand_winnings.append(winnings)
            if hand_results_fp is not None:
                successful_hands = len(hand_winnings)
                hand_results_fp.write(json.dumps({
                    'attempted_hand': h + 1,
                    'successful_hand': successful_hands,
                    'winnings_chips': int(winnings),
                    'winnings_bb': float(winnings / BIG_BLIND),
                    'cumulative_chips': int(total_chips),
                    'cumulative_bb': float(total_chips / BIG_BLIND),
                }) + '\n')
                hand_results_fp.flush()
        except requests.HTTPError as e:
            print(f'  Hand {h+1}: HTTP error {e}, skipping')
            continue
        except Exception as e:
            print(f'  Hand {h+1}: error {e}, skipping')
            continue

        if (h + 1) % 100 == 0:
            n = len(hand_winnings)
            avg_bb = (total_chips / n) / BIG_BLIND
            std_bb = (
                float(np.std(hand_winnings, ddof=1)) / BIG_BLIND
                if n > 1
                else 0.0
            )
            ci95_bb_per_100 = 1.96 * std_bb / math.sqrt(n) * 100.0
            bb_per_100 = avg_bb * 100.0
            print(
                f'  [{h+1:5d}] avg {avg_bb:+.3f} BB/hand '
                f'({bb_per_100:+.2f} bb/100, 95% CI '
                f'[{bb_per_100-ci95_bb_per_100:+.2f}, '
                f'{bb_per_100+ci95_bb_per_100:+.2f}]) | '
                f'{total_chips:+d} chips'
            )

    if dump_fp is not None:
        dump_fp.close()
    if hand_results_fp is not None:
        hand_results_fp.close()

    n = len(hand_winnings)
    if n == 0:
        print('No hands played successfully.')
        raise SystemExit(1)

    avg_bb = (total_chips / n) / BIG_BLIND
    std_bb = (np.std(hand_winnings, ddof=1) / BIG_BLIND) if n > 1 else 0.0
    ci95 = 1.96 * std_bb / math.sqrt(n)
    bb_per_100 = avg_bb * 100.0
    ci95_bb_per_100 = ci95 * 100.0
    lower_bb_per_100 = bb_per_100 - ci95_bb_per_100
    upper_bb_per_100 = bb_per_100 + ci95_bb_per_100
    significant_winner = None
    if abs(avg_bb) > ci95:
        significant_winner = 'AlphaHoldem' if avg_bb > 0 else 'Slumbot'

    elapsed = time.time() - t0
    print('\n' + '=' * 60)
    print(f'Results vs Slumbot ({n:,} hands):')
    print(f'  Avg:          {avg_bb:+.4f} BB/hand')
    print(f'  bb/100:       {bb_per_100:+.2f}')
    print(f'  mbb/hand:     {avg_bb*1000:+.1f}')
    print(f'  95% CI:       +/-{ci95:.4f} BB/hand (+/-{ci95_bb_per_100:.2f} bb/100)')
    print(f'  95% CI bb/100: [{lower_bb_per_100:+.2f}, {upper_bb_per_100:+.2f}]')
    print(f'  Total:        {total_chips:+d} chips ({total_chips/BIG_BLIND:+.1f} BB)')
    print(f'  Time:         {elapsed/60:.1f} min ({n/elapsed*60:.1f} hands/min)')
    print('=' * 60)
    if significant_winner:
        print(f'  {significant_winner} wins (statistically significant)')
    else:
        print('  No statistically significant winner (need more hands)')

    if args.result_json:
        result_path = Path(args.result_json)
        result_path.parent.mkdir(parents=True, exist_ok=True)
        result = {
            'model': args.model,
            'strategy': args.strategy,
            'requested_hands': int(args.hands),
            'successful_hands': int(n),
            'device': args.device,
            'obs_version': obs_version,
            'policy_mode': mode,
            'policy_mode_raw': policy_mode,
            'guarded_allin_max_spr': float(args.guarded_allin_max_spr),
            'guarded_allin_min_prob': float(args.guarded_allin_min_prob),
            'callguard_min_prob': float(args.callguard_min_prob),
            'callguard_ratio': float(args.callguard_ratio),
            'callguard_include_open': bool(args.callguard_include_open),
            'total_chips': int(total_chips),
            'avg_bb_per_hand': float(avg_bb),
            'bb_per_100': float(bb_per_100),
            'mbb_per_hand': float(avg_bb * 1000.0),
            'std_bb_per_hand': float(std_bb),
            'ci95_bb_per_hand': float(ci95),
            'ci95_bb_per_100': float(ci95_bb_per_100),
            'lower_bound_bb_per_100': float(lower_bb_per_100),
            'upper_bound_bb_per_100': float(upper_bb_per_100),
            'significant_winner': significant_winner,
            'elapsed_seconds': float(elapsed),
            'hands_per_minute': float(n / elapsed * 60.0) if elapsed > 0 else None,
        }
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding='utf-8')
        print(f'Wrote result JSON: {result_path}')


if __name__ == '__main__':
    main()

