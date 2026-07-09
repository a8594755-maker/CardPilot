#!/usr/bin/env python3
"""
Head-to-head match: AlphaHoldem V3 vs V10 (CFR-trained VNet).

AlphaHoldem: PyTorch model, 9 discrete actions, sees card tensors
V10:         JSON weights, 54-dim features, outputs action(3) + sizing(5)

Both play the same HUNL game. Each hand alternates positions.
Reports bb/hand and 95% CI.
"""

import argparse
import json
import os
import sys
import math
import random
import time

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.environment import (
    HUNLEnvironment, NUM_ACTIONS,
    encode_cards, encode_action_history, encode_extra, get_legal_mask,
    action_index_to_game_action, RAISE_FRACTIONS,
)
from deep_cfr.game_state import HUNLGameState, Street, ActionType, Action


# ═══════════════════════════════════════════════════════════
# V10 Loader (Python reimplementation of mlp.ts V2 forward)
# ═══════════════════════════════════════════════════════════

def relu(x): return np.maximum(x, 0)

def softmax(x):
    e = np.exp(x - np.max(x))
    return e / e.sum()


class V10Model:
    """V10 value network — 54D features → action(3) + sizing(5)."""

    def __init__(self, json_path: str):
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

    def predict(self, features: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        """Returns (action_probs[3], sizing_probs[5]).
        action: [raise, call, fold]
        sizing: [third, half, twoThirds, pot, allIn]
        """
        x = features
        for W, b in self.layers:
            x = relu(W @ x + b)
        action_logits = self.action_w @ x + self.action_b
        sizing_logits = self.sizing_w @ x + self.sizing_b
        return softmax(action_logits), softmax(sizing_logits)


# ═══════════════════════════════════════════════════════════
# V10 Feature Encoding (matches cfr-to-training-data.ts encodeCfrFeatures)
# ═══════════════════════════════════════════════════════════

RANK_VALUES = {'2':2, '3':3, '4':4, '5':5, '6':6, '7':7, '8':8, '9':9,
               'T':10, 'J':11, 'Q':12, 'K':13, 'A':14}
SUIT_INDEX = {'s':0, 'h':1, 'd':2, 'c':3}


def card_idx_to_str(c: int) -> str:
    """Convert card idx (0-51) to string. card = rank*4 + suit."""
    rank = c // 4
    suit = c % 4
    rank_chars = '23456789TJQKA'
    suit_chars = 'cdhs'
    return rank_chars[rank] + suit_chars[suit]


def encode_v10_features(state: HUNLGameState, player: int) -> np.ndarray:
    """Encode game state → 54D feature vector for V10."""
    features = []

    # Hole cards (5 features)
    hole = state.hole_cards[player]
    s0 = card_idx_to_str(hole[0])
    s1 = card_idx_to_str(hole[1])
    r1 = RANK_VALUES.get(s0[0], 0)
    r2 = RANK_VALUES.get(s1[0], 0)
    suited = 1.0 if s0[1] == s1[1] else 0.0
    paired = 1.0 if s0[0] == s1[0] else 0.0
    gap = abs(r1 - r2) / 12.0
    features.extend([r1 / 14.0, r2 / 14.0, suited, paired, gap])

    # Board cards (25 features: 5 slots × 5 each)
    board = state.board
    for i in range(5):
        if i < len(board):
            cs = card_idx_to_str(board[i])
            r = RANK_VALUES.get(cs[0], 0) / 14.0
            s_idx = SUIT_INDEX.get(cs[1], 0)
            features.extend([
                r,
                1.0 if s_idx == 0 else 0.0,
                1.0 if s_idx == 1 else 0.0,
                1.0 if s_idx == 2 else 0.0,
                1.0 if s_idx == 3 else 0.0,
            ])
        else:
            features.extend([0.0, 0.0, 0.0, 0.0, 0.0])

    # Street one-hot (3)
    st = state.street
    features.extend([
        1.0 if st == Street.FLOP else 0.0,
        1.0 if st == Street.TURN else 0.0,
        1.0 if st == Street.RIVER else 0.0,
    ])

    # Position one-hot (7): HU → P0 (BB)=index 6, P1 (BTN)=index 4
    pos = [0.0] * 7
    if player == 1:
        pos[4] = 1.0  # IP / BTN
    else:
        pos[6] = 1.0  # OOP / BB
    features.extend(pos)

    # In position (1)
    is_ip = 1.0 if player == 1 else 0.0
    features.append(is_ip)

    # Pot geometry (4): potNorm, toCallNorm, SPR, potOdds
    pot = state.pot
    my_committed = state.street_committed[player]
    opp_committed = state.street_committed[1 - player]
    to_call = max(0.0, opp_committed - my_committed)
    eff_stack = min(state.stacks[0], state.stacks[1])
    pot_norm = min(pot / 100.0, 5.0)
    to_call_norm = min(to_call / 100.0, 5.0)
    spr = min(eff_stack / pot, 20.0) if pot > 0 else 20.0
    pot_odds = to_call / (pot + to_call) if to_call > 0 else 0.0
    features.extend([pot_norm, to_call_norm, spr, pot_odds])

    # Action context (3): numVillains, facingBet, isAggressor
    facing_bet = 1.0 if to_call > 0 else 0.0
    features.extend([1.0 / 5.0, facing_bet, 0.0])

    # Betting history (6) — simplified defaults
    features.extend([0.0, 0.0, 0.0, 0.0, 0.0, 0.0])

    return np.array(features, dtype=np.float32)


# ═══════════════════════════════════════════════════════════
# V10 Decision: map (raise, call, fold) + sizing → game action
# ═══════════════════════════════════════════════════════════

def v10_decide(model: V10Model, state: HUNLGameState, player: int) -> Action:
    """V10 samples an action given current state."""
    features = encode_v10_features(state, player)
    action_probs, sizing_probs = model.predict(features)
    # action_probs: [raise, call, fold]

    legal = state.legal_actions()

    # Sample high-level action
    raise_p, call_p, fold_p = action_probs[0], action_probs[1], action_probs[2]

    # Check legal actions available
    legal_types = {a.type for a in legal}

    # Renormalize over legal action types
    probs = []
    choices = []
    if ActionType.FOLD in legal_types:
        probs.append(fold_p); choices.append('fold')
    if ActionType.CHECK in legal_types or ActionType.CALL in legal_types:
        probs.append(call_p); choices.append('call')
    if any(t in legal_types for t in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN)):
        probs.append(raise_p); choices.append('raise')

    total = sum(probs)
    if total <= 0:
        # All probs collapsed — default check/call
        for a in legal:
            if a.type in (ActionType.CHECK, ActionType.CALL):
                return a
        return legal[0]

    probs_arr = np.array(probs, dtype=np.float64) / total
    probs_arr = probs_arr / probs_arr.sum()  # re-normalize against float drift
    chosen = np.random.choice(choices, p=probs_arr)

    if chosen == 'fold':
        for a in legal:
            if a.type == ActionType.FOLD:
                return a
        # No fold available — fallback
        for a in legal:
            if a.type in (ActionType.CHECK, ActionType.CALL):
                return a

    if chosen == 'call':
        for a in legal:
            if a.type in (ActionType.CHECK, ActionType.CALL):
                return a

    # Raise: pick sizing
    # sizing_probs: [third, half, twoThirds, pot, allIn]
    sizing_fracs = [0.33, 0.50, 0.67, 1.00]  # first 4
    # allin handled separately

    # Find available raise actions
    raise_actions = [a for a in legal if a.type in (ActionType.BET, ActionType.RAISE, ActionType.ALLIN)]
    if not raise_actions:
        # Fallback to call
        for a in legal:
            if a.type in (ActionType.CHECK, ActionType.CALL):
                return a
        return legal[0]

    # Check if allin should be picked
    allin_p = sizing_probs[4]
    bet_p = 1 - allin_p
    if np.random.random() < allin_p:
        for a in raise_actions:
            if a.type == ActionType.ALLIN:
                return a
        # No allin — pick largest raise
        return max(raise_actions, key=lambda a: a.amount)

    # Pick sizing by fraction of pot
    # Renormalize first 4 sizing probs
    sp = np.array(sizing_probs[:4], dtype=np.float64)
    if sp.sum() > 0:
        sp = sp / sp.sum()
        sp = sp / sp.sum()  # re-normalize against float drift
    else:
        sp = np.array([0.25, 0.25, 0.25, 0.25])
    chosen_idx = np.random.choice(4, p=sp)
    target_frac = sizing_fracs[chosen_idx]
    target_amount = target_frac * state.pot

    # Find closest raise
    best = None
    best_dist = float('inf')
    for a in raise_actions:
        if a.type == ActionType.ALLIN:
            continue
        dist = abs(a.amount - target_amount)
        if dist < best_dist:
            best_dist = dist
            best = a
    if best is None:
        return max(raise_actions, key=lambda a: a.amount)
    return best


# ═══════════════════════════════════════════════════════════
# AlphaHoldem Decision
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def alpha_decide(model: AlphaHoldemNet, env: HUNLEnvironment, device: str, greedy: bool = True) -> int:
    """AlphaHoldem decides action index (0-8)."""
    state = env.state
    player = state.current_player
    card_info = encode_cards(state, player)
    action_info = encode_action_history(state, player)
    extra = encode_extra(state, player)
    mask = get_legal_mask(state)

    card_t = torch.tensor(card_info, dtype=torch.float32, device=device).unsqueeze(0)
    action_t = torch.tensor(action_info, dtype=torch.float32, device=device).unsqueeze(0)
    extra_t = torch.tensor(extra, dtype=torch.float32, device=device).unsqueeze(0)
    mask_t = torch.tensor(mask, dtype=torch.float32, device=device).unsqueeze(0)

    logits, _ = model(card_t, action_t, extra_t, mask_t)
    probs = F.softmax(logits, dim=-1)
    if greedy:
        return int(torch.argmax(probs, dim=-1).item())
    else:
        dist = Categorical(probs)
        return int(dist.sample().item())


# ═══════════════════════════════════════════════════════════
# Head-to-Head Match
# ═══════════════════════════════════════════════════════════

def run_match(alpha_model, v10_model, num_hands: int, device: str, alpha_greedy: bool = True):
    """
    Play num_hands. Alpha and V10 alternate positions.
    Returns stats.
    """
    env = HUNLEnvironment(starting_stack=50.0)

    alpha_total = 0.0
    v10_total = 0.0
    alpha_rewards = []
    alpha_wins = 0
    alpha_losses = 0
    draws = 0

    for hand_idx in range(num_hands):
        obs = env.reset()
        done = False
        alpha_player = hand_idx % 2  # Alpha alternates between P0 and P1
        hand_reward = 0.0

        while not done:
            player = env.state.current_player

            if player == alpha_player:
                # AlphaHoldem's turn
                action_idx = alpha_decide(alpha_model, env, device, greedy=alpha_greedy)
                obs, reward, done = env.step(action_idx)
                if done:
                    hand_reward = reward  # reward is from alpha's perspective
            else:
                # V10's turn — map V10 Action to action_idx
                v10_action = v10_decide(v10_model, env.state, player)
                # Apply action directly by finding its match in legal_mask space
                # Simpler: convert v10_action back to action_idx for env.step()
                mask = get_legal_mask(env.state)
                # Find the action_idx that maps to v10_action
                a_idx = _action_to_idx(v10_action, env.state)
                obs, reward, done = env.step(a_idx)
                if done:
                    hand_reward = -reward  # reward is V10's, flip for alpha

        alpha_total += hand_reward
        alpha_rewards.append(hand_reward)
        if hand_reward > 0.01: alpha_wins += 1
        elif hand_reward < -0.01: alpha_losses += 1
        else: draws += 1

        if (hand_idx + 1) % 500 == 0:
            avg = alpha_total / (hand_idx + 1)
            print(f'  [{hand_idx+1:5d}] alpha avg={avg:+.3f} bb/hand W/L/D={alpha_wins}/{alpha_losses}/{draws}')

    n = num_hands
    avg = alpha_total / n
    std = np.std(alpha_rewards)
    ci95 = 1.96 * std / math.sqrt(n)

    return {
        'hands': n,
        'alpha_avg_bb': avg,
        'alpha_mbb_per_hand': avg * 1000,
        'alpha_total_bb': alpha_total,
        'ci95_bb': ci95,
        'alpha_wins': alpha_wins,
        'alpha_losses': alpha_losses,
        'draws': draws,
        'alpha_win_rate': alpha_wins / n,
    }


def _action_to_idx(action: Action, state: HUNLGameState) -> int:
    """Convert V10's game Action back to env action_idx (0-8)."""
    if action.type == ActionType.FOLD:
        return 0
    if action.type in (ActionType.CHECK, ActionType.CALL):
        return 1
    if action.type == ActionType.ALLIN:
        return 8
    # BET or RAISE — map to closest fraction slot
    pot = state.pot
    if pot <= 0:
        return 2
    frac = action.amount / pot
    best_idx = 0
    best_dist = float('inf')
    for i, f in enumerate(RAISE_FRACTIONS):
        d = abs(frac - f)
        if d < best_dist:
            best_dist = d
            best_idx = i
    return best_idx + 2  # slots 2-7


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--alpha', default='models/alpha_holdem_v3.pt')
    parser.add_argument('--v10', default='models/vnet-v10-v3data.json')
    parser.add_argument('--hands', type=int, default=5000)
    parser.add_argument('--device', default='cpu')
    parser.add_argument('--sample', action='store_true', help='Alpha samples (not greedy)')
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    print(f'Loading AlphaHoldem from {args.alpha}...')
    ckpt = torch.load(args.alpha, map_location=device, weights_only=False)
    ckpt_norm = ckpt.get('norm_layer', 'bn')
    alpha = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=ckpt_norm).to(device)
    alpha.eval()
    dc = torch.zeros(2, 6, 4, 13, device=device)
    da = torch.zeros(2, 25, 4, 5, device=device)
    de = torch.zeros(2, 2, device=device)
    alpha(dc, da, de)  # lazy init
    alpha.load_state_dict(ckpt['model'])
    alpha.eval()
    print(f'  norm_layer={ckpt_norm}')
    print(f'  AlphaHoldem loaded (iteration {ckpt.get("iteration", "?")})')

    print(f'Loading V10 from {args.v10}...')
    v10 = V10Model(args.v10)
    print(f'  V10 loaded')

    print(f'\nHead-to-head: AlphaHoldem (greedy={not args.sample}) vs V10')
    print(f'Hands: {args.hands:,}')
    print('-' * 60)

    t0 = time.time()
    stats = run_match(alpha, v10, args.hands, device, alpha_greedy=not args.sample)
    elapsed = time.time() - t0

    print('-' * 60)
    print(f'Results (Alpha perspective):')
    print(f'  Alpha reward:  {stats["alpha_avg_bb"]:+.4f} BB/hand')
    print(f'                 ({stats["alpha_mbb_per_hand"]:+.1f} mbb/hand)')
    print(f'  95% CI:        ±{stats["ci95_bb"]:.4f} BB/hand')
    print(f'  Total:         {stats["alpha_total_bb"]:+.1f} BB')
    print(f'  W/L/D:         {stats["alpha_wins"]}/{stats["alpha_losses"]}/{stats["draws"]}')
    print(f'  Alpha win rate: {stats["alpha_win_rate"]*100:.1f}%')
    print(f'  Time:          {elapsed:.1f}s ({args.hands/elapsed:.0f} hands/sec)')
    print()
    if stats['alpha_avg_bb'] > stats['ci95_bb']:
        print(f'  ✓ AlphaHoldem wins (statistically significant)')
    elif stats['alpha_avg_bb'] < -stats['ci95_bb']:
        print(f'  ✓ V10 wins (statistically significant)')
    else:
        print(f'  ∼ No statistically significant winner')


if __name__ == '__main__':
    main()
