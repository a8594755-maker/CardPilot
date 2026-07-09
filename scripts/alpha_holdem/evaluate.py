#!/usr/bin/env python3
"""
Evaluate AlphaHoldem model against baselines.

Baselines:
  - random: uniform random legal action
  - call-station: always check/call
  - v10: our CFR-trained VNet (via fast-model inference)

Usage:
  python scripts/alpha_holdem/evaluate.py --model models/alpha_holdem_v1.pt --opponent random --hands 10000
  python scripts/alpha_holdem/evaluate.py --model models/alpha_holdem_v1.pt --opponent call-station --hands 10000
"""

import argparse
import os
import sys
import time
import random

import numpy as np
import torch
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet
from alpha_holdem.environment import (
    HUNLEnvironment, NUM_ACTIONS, encode_cards,
    encode_action_history, encode_extra, get_legal_mask,
    action_index_to_game_action,
)


# ═══════════════════════════════════════════════════════════
# Opponent Policies
# ═══════════════════════════════════════════════════════════

def random_policy(obs: dict) -> int:
    """Pick a random legal action."""
    legal = np.where(obs['legal_mask'] > 0)[0]
    return random.choice(legal)


def call_station_policy(obs: dict) -> int:
    """Always check/call. Never fold, never raise."""
    mask = obs['legal_mask']
    if mask[1] > 0:  # check/call
        return 1
    if mask[0] > 0:  # fold (forced if can't check/call)
        return 0
    # Shouldn't happen
    legal = np.where(mask > 0)[0]
    return legal[0]


def aggressive_policy(obs: dict) -> int:
    """Always raise max or allin. Call if can't raise."""
    mask = obs['legal_mask']
    if mask[8] > 0:  # allin
        return 8
    # Find highest raise
    for i in range(7, 1, -1):
        if mask[i] > 0:
            return i
    if mask[1] > 0:  # call
        return 1
    return 0  # fold


OPPONENTS = {
    'random': random_policy,
    'call-station': call_station_policy,
    'aggressive': aggressive_policy,
}


# ═══════════════════════════════════════════════════════════
# Evaluation
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def evaluate(
    model: AlphaHoldemNet,
    opponent_fn,
    num_hands: int,
    device: str,
    starting_stack: float = 50.0,
) -> dict:
    """
    Play num_hands, alternating positions.
    Returns stats dict.
    """
    model.eval()
    env = HUNLEnvironment(starting_stack=starting_stack)

    total_reward = 0.0
    wins = 0
    losses = 0
    draws = 0
    hand_rewards = []

    for hand_idx in range(num_hands):
        obs = env.reset()
        done = False
        hero_player = hand_idx % 2

        while not done:
            player = obs['player']
            is_hero = (player == hero_player)

            if is_hero:
                # Model plays
                card_t = torch.tensor(obs['card_info'], dtype=torch.float32, device=device).unsqueeze(0)
                action_t = torch.tensor(obs['action_info'], dtype=torch.float32, device=device).unsqueeze(0)
                extra_t = torch.tensor(obs['extra_info'], dtype=torch.float32, device=device).unsqueeze(0)
                mask_t = torch.tensor(obs['legal_mask'], dtype=torch.float32, device=device).unsqueeze(0)

                logits, _ = model(card_t, action_t, extra_t, mask_t)
                probs = F.softmax(logits, dim=-1)
                action_idx = torch.argmax(probs, dim=-1).item()  # greedy
            else:
                # Opponent plays
                action_idx = opponent_fn(obs)

            obs, reward, done = env.step(action_idx)

            if done:
                if is_hero:
                    hand_reward = reward
                else:
                    hand_reward = -reward

        total_reward += hand_reward
        hand_rewards.append(hand_reward)

        if hand_reward > 0.01:
            wins += 1
        elif hand_reward < -0.01:
            losses += 1
        else:
            draws += 1

        if (hand_idx + 1) % 1000 == 0:
            avg = total_reward / (hand_idx + 1)
            print(f'  [{hand_idx+1:6d}] avg={avg:+.3f} bb/hand  W/L/D={wins}/{losses}/{draws}')

    n = num_hands
    avg_reward = total_reward / n
    std = np.std(hand_rewards)
    stderr = std / np.sqrt(n)

    return {
        'hands': n,
        'avg_reward_bb': avg_reward,
        'total_reward_bb': total_reward,
        'std': std,
        'stderr': stderr,
        'ci95': 1.96 * stderr,
        'wins': wins,
        'losses': losses,
        'draws': draws,
        'win_rate': wins / n,
        'mbb_per_hand': avg_reward * 1000,  # milli-BB per hand
    }


def main():
    parser = argparse.ArgumentParser(description='Evaluate AlphaHoldem')
    parser.add_argument('--model', required=True, help='Path to model checkpoint')
    parser.add_argument('--opponent', default='random', choices=list(OPPONENTS.keys()))
    parser.add_argument('--hands', type=int, default=10000)
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--starting-stack', type=float, default=50.0, help='BB units')
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')

    # Load model — peek at checkpoint norm_layer (default bn for legacy ckpts).
    ckpt = torch.load(args.model, map_location=device, weights_only=False)
    ckpt_norm = ckpt.get('norm_layer', 'bn')
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=ckpt_norm).to(device)
    model.eval()
    dummy_c = torch.zeros(2, 6, 4, 13, device=device)
    dummy_a = torch.zeros(2, 25, 4, 5, device=device)
    dummy_e = torch.zeros(2, 2, device=device)
    model(dummy_c, dummy_a, dummy_e)

    model.load_state_dict(ckpt['model'])
    iteration = ckpt.get('iteration', '?')
    print(f'Loaded model from {args.model} (iteration {iteration})')

    opponent_fn = OPPONENTS[args.opponent]
    print(f'\nEvaluating vs {args.opponent} ({args.hands:,} hands)...')
    print('-' * 60)

    t0 = time.time()
    stats = evaluate(model, opponent_fn, args.hands, device, starting_stack=args.starting_stack)
    elapsed = time.time() - t0

    print('-' * 60)
    print(f'Results vs {args.opponent}:')
    print(f'  Avg reward:    {stats["avg_reward_bb"]:+.4f} BB/hand ({stats["mbb_per_hand"]:+.1f} mbb/hand)')
    print(f'  Total reward:  {stats["total_reward_bb"]:+.1f} BB')
    print(f'  95% CI:        ±{stats["ci95"]:.4f} BB/hand')
    print(f'  Win/Loss/Draw: {stats["wins"]}/{stats["losses"]}/{stats["draws"]}')
    print(f'  Win rate:      {stats["win_rate"]*100:.1f}%')
    print(f'  Time:          {elapsed:.1f}s ({args.hands/elapsed:.0f} hands/sec)')


if __name__ == '__main__':
    main()
