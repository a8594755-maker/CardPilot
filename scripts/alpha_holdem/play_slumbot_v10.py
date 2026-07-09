#!/usr/bin/env python3
"""
V10 (CFR value network) vs Slumbot — for fair comparison with AlphaHoldem.

Uses same Slumbot API client as play_slumbot.py, but the bot is:
  - Preflop: simple call/raise chart based on hole-card strength
  - Postflop: V10 predicts (raise, call, fold) + sizing → game action

Same 200bb HUNL as AlphaHoldem ran, same 2000 hands benchmark.
"""

import argparse
import json
import os
import sys
import time
import math
import random

import numpy as np
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.play_slumbot import (
    HOST, SMALL_BLIND, BIG_BLIND, STACK_SIZE, NUM_STREETS,
    parse_action, new_hand, act,
)

# ═══════════════════════════════════════════════════════════
# V10 Loader (Python reimpl of mlp.ts forwardV2)
# ═══════════════════════════════════════════════════════════

def relu(x): return np.maximum(x, 0)
def softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()

class V10Model:
    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            w = json.load(f)
        self.layers = []
        for layer in w['layers']:
            self.layers.append((
                np.array(layer['weights'], dtype=np.float32),
                np.array(layer['biases'], dtype=np.float32),
            ))
        self.action_w = np.array(w['actionHead']['weights'], dtype=np.float32)
        self.action_b = np.array(w['actionHead']['biases'], dtype=np.float32)
        self.sizing_w = np.array(w['sizingHead']['weights'], dtype=np.float32)
        self.sizing_b = np.array(w['sizingHead']['biases'], dtype=np.float32)

    def predict(self, features):
        """Returns (action_probs[3], sizing_probs[5])
        action: [raise, call, fold]
        sizing: [third, half, twoThirds, pot, allIn]
        """
        x = features
        for W, b in self.layers:
            x = relu(W @ x + b)
        ap = softmax(self.action_w @ x + self.action_b)
        sp = softmax(self.sizing_w @ x + self.sizing_b)
        return ap, sp


# ═══════════════════════════════════════════════════════════
# V10 Feature Encoding (matches encodeCfrFeatures in cfr-to-training-data.ts)
# ═══════════════════════════════════════════════════════════

RANK_VALUES = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9,
               'T':10, 'J':11, 'Q':12, 'K':13, 'A':14}
SUIT_INDEX = {'s':0, 'h':1, 'd':2, 'c':3}


def encode_v10_features(hole_cards, board, street, client_pos, state):
    """Encode 54-dim V10 feature vector.

    Args:
        hole_cards: ['As', 'Kh']
        board: ['2c', '7d', '9h'] (0-5 cards)
        street: 0-3 (preflop, flop, turn, river)
        client_pos: 0=BB, 1=SB
        state: parsed state dict from parse_action()
    """
    feats = []

    # Hole cards (5 features)
    s0, s1 = hole_cards[0], hole_cards[1]
    r1 = RANK_VALUES.get(s0[0], 0)
    r2 = RANK_VALUES.get(s1[0], 0)
    suited = 1.0 if s0[1] == s1[1] else 0.0
    paired = 1.0 if s0[0] == s1[0] else 0.0
    gap = abs(r1 - r2) / 12.0
    feats.extend([r1/14.0, r2/14.0, suited, paired, gap])

    # Board cards (25 = 5 slots × 5 each)
    for i in range(5):
        if i < len(board):
            c = board[i]
            r = RANK_VALUES.get(c[0], 0) / 14.0
            sidx = SUIT_INDEX.get(c[1], 0)
            feats.extend([r,
                          1.0 if sidx == 0 else 0.0,
                          1.0 if sidx == 1 else 0.0,
                          1.0 if sidx == 2 else 0.0,
                          1.0 if sidx == 3 else 0.0])
        else:
            feats.extend([0.0, 0.0, 0.0, 0.0, 0.0])

    # Street one-hot (3)
    feats.extend([
        1.0 if street == 1 else 0.0,  # FLOP
        1.0 if street == 2 else 0.0,  # TURN
        1.0 if street == 3 else 0.0,  # RIVER
    ])

    # Position one-hot (7) + inPosition (1)
    # HU: BTN (SB) = IP = slot 4, BB = OOP = slot 6
    # client_pos: 0 = BB, 1 = SB
    # Per V10 training data: player 0 = BB (OOP), player 1 = SB (BTN, IP)
    pos = [0.0] * 7
    is_ip = client_pos == 1
    if is_ip:
        pos[4] = 1.0
    else:
        pos[6] = 1.0
    feats.extend(pos)
    feats.append(1.0 if is_ip else 0.0)

    # Pot geometry (4)
    # state has total_last_bet_to (chips both players committed in current bet)
    # Pot = ~2 * total_last_bet_to (approximation if symmetric)
    pot = state['total_last_bet_to'] * 2  # rough
    to_call = state['last_bet_size']
    eff_stack = STACK_SIZE - state['total_last_bet_to']
    pot_norm = min(pot / 100.0, 5.0)  # normalize by BB
    to_call_norm = min(to_call / 100.0, 5.0)
    spr = min(eff_stack / pot, 20.0) if pot > 0 else 20.0
    pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0
    feats.extend([pot_norm, to_call_norm, spr, pot_odds])

    # Action context (3)
    facing_bet = 1.0 if to_call > 0 else 0.0
    feats.extend([1.0/5.0, facing_bet, 0.0])

    # Betting history (6) — simplified
    feats.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    return np.array(feats, dtype=np.float32)


# ═══════════════════════════════════════════════════════════
# Preflop strategy (simple chart based on hand strength)
# ═══════════════════════════════════════════════════════════

def hand_strength_preflop(hole_cards):
    """Simple hand strength 0-100 for preflop decisions."""
    c1, c2 = hole_cards[0], hole_cards[1]
    r1, r2 = RANK_VALUES.get(c1[0], 0), RANK_VALUES.get(c2[0], 0)
    suited = c1[1] == c2[1]
    paired = c1[0] == c2[0]
    hi = max(r1, r2)
    lo = min(r1, r2)

    if paired:
        # Pocket pairs
        return 50 + (r1 - 2) * 4  # 22=58, AA=98

    score = hi + lo  # base score
    if suited:
        score += 4
    if hi - lo <= 4:  # connected/1-gap
        score += 3
    # Premium hands
    if hi == 14 and lo >= 11:  # AK, AQ, AJ
        score += 10
    if hi >= 13 and lo >= 10:  # broadway
        score += 5
    return score


def preflop_decide(hole_cards, state, client_pos):
    """
    Simple preflop strategy:
      - HS < 15: fold to any raise, check if can
      - HS 15-25: call 1 bet, fold to 3bet+
      - HS 25-40: call/small raise
      - HS > 40: raise 2.5x
    """
    hs = hand_strength_preflop(hole_cards)
    last_bet_size = state['last_bet_size']
    street_bet = state['street_last_bet_to']
    total_bet = state['total_last_bet_to']

    facing_bet = last_bet_size > 0

    # No bet to call (we can check)
    if not facing_bet:
        if hs >= 30:
            # Raise to 3x BB
            target = street_bet + 3 * BIG_BLIND
            return f'b{target}'
        return 'k'  # check

    # Facing a bet
    if hs < 15:
        return 'f'
    if hs < 25:
        # Call only if bet is small (<= 3x BB)
        if street_bet <= 3 * BIG_BLIND:
            return 'c'
        return 'f'
    if hs < 40:
        # Call small, fold big
        if street_bet <= 4 * BIG_BLIND:
            return 'c'
        return 'f'
    # Strong hand: raise or call big
    if street_bet >= 10 * BIG_BLIND:
        return 'c'  # call 3bet+ with premium
    # Raise to 3x their bet
    new_bet = min(3 * street_bet, STACK_SIZE - (total_bet - street_bet))
    return f'b{new_bet}'


# ═══════════════════════════════════════════════════════════
# Postflop V10 decision
# ═══════════════════════════════════════════════════════════

def v10_postflop_decide(model, hole_cards, board, street, client_pos, state):
    """V10 picks action given postflop state."""
    features = encode_v10_features(hole_cards, board, street, client_pos, state)
    action_probs, sizing_probs = model.predict(features)
    raise_p, call_p, fold_p = action_probs[0], action_probs[1], action_probs[2]

    last_bet_size = state['last_bet_size']
    street_bet = state['street_last_bet_to']
    total_bet = state['total_last_bet_to']
    facing_bet = last_bet_size > 0

    # Renormalize over legal options
    probs = []
    choices = []
    if facing_bet:
        probs.append(fold_p); choices.append('fold')
    probs.append(call_p); choices.append('call')
    probs.append(raise_p); choices.append('raise')

    total = sum(probs)
    if total <= 0:
        return 'c' if facing_bet else 'k'

    probs = np.array(probs, dtype=np.float64) / total
    probs = probs / probs.sum()
    chosen = np.random.choice(choices, p=probs)

    if chosen == 'fold':
        return 'f'
    if chosen == 'call':
        return 'c' if facing_bet else 'k'

    # Raise: pick sizing
    # sizing_probs: [third, half, twoThirds, pot, allIn]
    allin_p = sizing_probs[4]
    max_target = STACK_SIZE - (total_bet - street_bet)

    if np.random.random() < allin_p:
        return f'b{max_target}'

    sizing_fracs = [0.33, 0.50, 0.67, 1.00]
    sp = np.array(sizing_probs[:4], dtype=np.float64)
    if sp.sum() > 0:
        sp = sp / sp.sum()
    else:
        sp = np.array([0.25, 0.25, 0.25, 0.25])

    idx = np.random.choice(4, p=sp)
    frac = sizing_fracs[idx]

    # Pot = 2 * total_bet (both players committed equally so far)
    pot_after_call = total_bet * 2
    target = street_bet + int(frac * pot_after_call)

    # Enforce min bet
    min_bet = max(last_bet_size, BIG_BLIND)
    min_target = street_bet + min_bet
    if target < min_target:
        target = min_target
    if target >= max_target:
        return f'b{max_target}'
    return f'b{target}'


# ═══════════════════════════════════════════════════════════
# Play hand
# ═══════════════════════════════════════════════════════════

def play_hand(v10_model, token, verbose=False):
    r = new_hand(token)
    token = r.get('token', token)

    while True:
        action_str = r.get('action', '')
        client_pos = r.get('client_pos', 0)
        hole_cards = r.get('hole_cards', [])
        board = r.get('board', [])
        winnings = r.get('winnings')

        if winnings is not None:
            if verbose:
                print(f'  Hand ended. Winnings: {winnings} chips ({winnings/BIG_BLIND:+.2f} BB)')
            return token, winnings

        state = parse_action(action_str)
        if 'error' in state:
            print(f'Parse error: {state["error"]}')
            return token, 0

        if state['pos'] != client_pos:
            # Shouldn't happen, but safety fold
            if verbose:
                print(f'  WARN: pos={state["pos"]} client_pos={client_pos}')
            try:
                r = act(token, 'f' if state['last_bet_size'] > 0 else 'k')
                continue
            except Exception:
                return token, -state['total_last_bet_to']

        street = state['st']

        # Pick action
        if street == 0:
            incr = preflop_decide(hole_cards, state, client_pos)
        else:
            incr = v10_postflop_decide(v10_model, hole_cards, board, street, client_pos, state)

        if verbose:
            print(f'  Street {street} action="{action_str}" V10 → "{incr}"')

        try:
            r = act(token, incr)
        except requests.HTTPError as e:
            if verbose:
                print(f'  HTTP error: {e}, trying fold')
            try:
                r = act(token, 'f' if state['last_bet_size'] > 0 else 'k')
            except Exception:
                return token, -state['total_last_bet_to']


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--model', default='models/vnet-v10-v3data.json')
    parser.add_argument('--hands', type=int, default=2000)
    parser.add_argument('--verbose', action='store_true')
    args = parser.parse_args()

    print(f'Loading V10 from {args.model}...')
    v10 = V10Model(args.model)
    print(f'V10 loaded')

    print(f'\nPlaying {args.hands} hands vs Slumbot (V10 + preflop chart)...')
    print('-' * 60)

    token = None
    total_chips = 0
    winnings_list = []
    t0 = time.time()

    for h in range(args.hands):
        try:
            token, winnings = play_hand(v10, token, verbose=args.verbose)
            total_chips += winnings
            winnings_list.append(winnings)
        except Exception as e:
            print(f'  Hand {h+1}: {e}, skipping')
            continue

        if (h + 1) % 100 == 0:
            n = len(winnings_list)
            avg_bb = (total_chips / n) / BIG_BLIND
            print(f'  [{h+1:5d}] avg {avg_bb:+.3f} BB ({avg_bb*1000:+.1f} mbb) | {total_chips:+d} chips')

    n = len(winnings_list)
    if n == 0:
        print('No hands played')
        return

    avg_bb = (total_chips / n) / BIG_BLIND
    std_bb = np.std(winnings_list) / BIG_BLIND
    ci95 = 1.96 * std_bb / math.sqrt(n)
    elapsed = time.time() - t0

    print('\n' + '=' * 60)
    print(f'V10 vs Slumbot ({n:,} hands):')
    print(f'  Avg:         {avg_bb:+.4f} BB/hand')
    print(f'  mbb/hand:    {avg_bb*1000:+.1f}')
    print(f'  95% CI:      +/-{ci95:.4f} BB/hand')
    print(f'  Total:       {total_chips:+d} chips ({total_chips/BIG_BLIND:+.1f} BB)')
    print(f'  Time:        {elapsed/60:.1f} min')
    print('=' * 60)

    if abs(avg_bb) > ci95:
        winner = 'V10' if avg_bb > 0 else 'Slumbot'
        print(f'  {winner} wins (statistically significant)')
    else:
        print(f'  No significant winner (need more hands)')


if __name__ == '__main__':
    main()
