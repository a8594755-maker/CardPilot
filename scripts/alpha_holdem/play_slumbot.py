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
                # Legacy AlphaHoldem evaluation treated all Slumbot "b" actions
                # as BET and normalized by total_last_bet_to.
                atype = {'f': 0, 'k': 1, 'c': 2, 'b': 3}.get(act, 1)
                denom = max(state['total_last_bet_to'], 1)
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

            t[ch, 1, min(atype, 4)] = 1.0
            if amt > 0:
                t[ch, 2, 0] = min(amt / denom, 2.0) / 2.0
            t[ch, 3, 0] = 1.0  # slot filled
    # Channel 24: current player indicator
    t[24, 0, 0] = 1.0 if current_pos == client_pos else 0.0
    return t


def encode_extra(stacks_remaining: list, starting: float = STACK_SIZE) -> np.ndarray:
    return np.array([stacks_remaining[0] / starting, stacks_remaining[1] / starting], dtype=np.float32)


def compute_legal_mask(state: dict) -> np.ndarray:
    """9-slot legal actions: [fold, check/call, 6 raise sizes, allin]."""
    mask, _ = build_action_table(state)
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


def build_action_table(state: dict) -> tuple[np.ndarray, list[str | None]]:
    """Mirror V5.5's sparse legal-mask + slot-to-action table for Slumbot."""
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

    fractions = PREFLOP_RAISE_FRACTIONS if state['st'] == 0 else RAISE_FRACTIONS
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


def action_idx_to_incr(action_idx: int, state: dict) -> str:
    _, slot_to_incr = build_action_table(state)
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
    obs_version: str = 'v55',
    policy_mode: str = 'greedy',
    guarded_allin_max_spr: float = 2.0,
    guarded_allin_min_prob: float = 0.65,
    callguard_min_prob: float = 0.20,
    callguard_ratio: float = 0.65,
    callguard_include_open: bool = False,
) -> int:
    """AlphaHoldem picks action (0-8)."""
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
    extra_t = torch.tensor(encode_extra(stacks), device=device).unsqueeze(0)

    mask = compute_legal_mask(state)
    mask_t = torch.tensor(mask, device=device).unsqueeze(0)

    # Heuristic policy short-circuit: bypass encoded-tensor forward and decide
    # from high-level state (hole_cards, board, position, facing_bet).
    if hasattr(model, 'decide') and callable(getattr(model, 'decide')):
        state_with_call = {**state, 'to_call': int(c['to_call'])}
        return int(model.decide(hole_cards, board, state_with_call, client_pos, mask))

    logits, _ = model(card_t, action_t, extra_t, mask_t)
    if policy_mode not in ('greedy', 'greedy-guarded', 'preflop-callguard') or not greedy:
        logits = logits / max(float(temperature), 1e-6)
    probs = F.softmax(logits, dim=-1)

    if policy_mode == 'greedy' and greedy:
        return int(torch.argmax(probs, dim=-1).item())

    if policy_mode == 'greedy-guarded':
        probs = guarded_action_probs(
            probs,
            mask_t,
            state,
            allin_max_spr=guarded_allin_max_spr,
            allin_min_prob=guarded_allin_min_prob,
        )
        return int(torch.argmax(probs, dim=-1).item())

    if policy_mode == 'preflop-callguard':
        if is_unopened_preflop_start(state) and not callguard_include_open:
            return int(torch.argmax(probs, dim=-1).item())
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
        if callguard_action is not None:
            return int(callguard_action)
        return int(torch.argmax(probs, dim=-1).item())

    if policy_mode == 'guarded':
        probs = guarded_action_probs(
            probs,
            mask_t,
            state,
            allin_max_spr=guarded_allin_max_spr,
            allin_min_prob=guarded_allin_min_prob,
        )
    elif policy_mode == 'preflop-mixed':
        if int(state.get('st', 0)) != 0:
            return int(torch.argmax(probs, dim=-1).item())
        probs = guarded_action_probs(
            probs,
            mask_t,
            state,
            allin_max_spr=guarded_allin_max_spr,
            allin_min_prob=guarded_allin_min_prob,
        )

    from torch.distributions import Categorical
    return int(Categorical(probs).sample().item())


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
        dump_fp.write(json.dumps(record) + '\n')


def play_hand(
    model,
    token: str | None,
    device: str,
    verbose: bool = False,
    greedy: bool = True,
    temperature: float = 1.0,
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
        action_idx = decide_action(
            model, hole_cards, board, state, client_pos, device,
            greedy=greedy,
            temperature=temperature,
            obs_version=obs_version,
            policy_mode=policy_mode,
            guarded_allin_max_spr=guarded_allin_max_spr,
            guarded_allin_min_prob=guarded_allin_min_prob,
            callguard_min_prob=callguard_min_prob,
            callguard_ratio=callguard_ratio,
            callguard_include_open=callguard_include_open,
        )
        incr = action_idx_to_incr(action_idx, state)

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
    parser.add_argument('--policy-mode', choices=('greedy', 'greedy-guarded', 'preflop-callguard', 'sample', 'guarded', 'preflop-mixed'), default='greedy',
                        help='Action selection for model strategy. --sample is kept as an alias for policy-mode=sample.')
    parser.add_argument('--temperature', type=float, default=1.0,
                        help='Sampling temperature when policy-mode is sample or guarded.')
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
    parser.add_argument('--strategy', choices=['model', 'fold', 'call', 'random', 'heuristic', 'heuristic_v2', 'heuristic_v3', 'heuristic_v3_1'], default='model',
                        help='Action policy. model=trained NN (default). fold/call/random=fixed baselines. '
                             'heuristic=v1. heuristic_v2=BB flat-call. heuristic_v3=polarized BB (1.5x raise). '
                             'heuristic_v3_1=v3 + BB jam-first sizing (diagnostic for fold-equity hypothesis).')
    args = parser.parse_args()

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

    if args.strategy == 'model':
        print(f'Loading model from {args.model}...')
        # Peek at checkpoint metadata to pick the right norm layer before constructing
        # the model (BN ckpt has running_mean/var keys; GN ckpt does not — strict load
        # would fail with the wrong norm layer).
        ckpt = torch.load(args.model, map_location=device, weights_only=False)
        ckpt_norm = ckpt.get('norm_layer', 'bn')
        model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=ckpt_norm).to(device)
        # Build lazy trunk in eval mode (avoids BN B=1 crash).
        model.eval()
        dc = torch.zeros(2, 6, 4, 13, device=device)
        da = torch.zeros(2, 25, 4, 5, device=device)
        de = torch.zeros(2, 2, device=device)
        model(dc, da, de)

        model.load_state_dict(ckpt['model'])
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
            print(f'  [{h+1:5d}] avg {avg_bb:+.3f} BB/hand ({avg_bb*1000:+.1f} mbb/hand) | {total_chips:+d} chips')

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

