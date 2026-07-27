"""Correctness + speed validation for VecHUNLState.

Runs the vectorized state through M parallel random-policy hands and compares
the distribution of outcomes (avg reward, fold rate, showdown rate, hand length)
against the Python HUNLEnvironment reference at the same scale.

Differences should be within Monte Carlo CI (a few bb/100).
"""
from __future__ import annotations

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
sys.path.insert(0, os.path.dirname(__file__))

from vec_game_state import VecHUNLState, NUM_ACTIONS
from alpha_holdem.environment import HUNLEnvironment


def run_vec(N: int, M_hands: int, seed: int = 1):
    """Play M_hands by running N parallel games + reset_done until M reached."""
    state = VecHUNLState(N=N, effective_stack=200.0, seed=seed)
    state.reset_all()
    rng = np.random.default_rng(seed + 1)

    rewards = []  # all hand rewards from hero's perspective
    fold_count = 0
    showdown_count = 0
    actions_per_hand = []
    actions_taken = np.zeros(N, dtype=np.int64)  # this hand's action count per slot

    t0 = time.perf_counter()
    total_steps = 0
    while len(rewards) < M_hands:
        mask = state.legal_mask()  # (N, 9)
        # Vectorized random legal action selection
        # For each row, choose uniformly among legal slots
        actions = np.zeros(N, dtype=np.int64)
        for i in range(N):
            legal = np.where(mask[i] > 0)[0]
            if len(legal) == 0:
                actions[i] = 1  # fallback check/call
            else:
                actions[i] = rng.choice(legal)
        state.step(actions)
        total_steps += 1
        actions_taken += (~state.is_done | True).astype(np.int64) * 0  # placeholder
        actions_taken += 1

        # Collect rewards from terminal games
        if state.is_done.any():
            r = state.terminal_rewards()
            done_idx = np.where(state.is_done)[0]
            for i in done_idx:
                rewards.append(float(r[i]))
                if state.folded_player[i] >= 0:
                    fold_count += 1
                else:
                    showdown_count += 1
                actions_per_hand.append(int(actions_taken[i]))
            actions_taken[done_idx] = 0
            state.reset_done()
    elapsed = time.perf_counter() - t0

    return {
        'hands': len(rewards),
        'avg_bb_per_hand': float(np.mean(rewards)),
        'std_bb': float(np.std(rewards)),
        'fold_rate': fold_count / len(rewards),
        'showdown_rate': showdown_count / len(rewards),
        'avg_actions_per_hand': float(np.mean(actions_per_hand)),
        'time_sec': elapsed,
        'hands_per_sec': len(rewards) / elapsed,
    }


def run_python(M_hands: int, seed: int = 1):
    """Reference Python sim playing M_hands of random policy."""
    import random as pyrand
    pyrand.seed(seed)
    np_rng = np.random.default_rng(seed)
    env = HUNLEnvironment(starting_stack=200.0)

    rewards = []
    fold_count = 0
    showdown_count = 0
    actions_per_hand = []
    total_actions = 0

    t0 = time.perf_counter()
    for h in range(M_hands):
        obs = env.reset()
        hero = h % 2  # alternate
        done = False
        hand_actions = 0
        hero_reward = 0.0
        while not done:
            mask = obs['legal_mask']
            legal = np.where(mask > 0)[0]
            if len(legal) == 0:
                action = 1
            else:
                action = int(pyrand.choice(legal.tolist()))
            player = obs['player']
            obs, reward, done = env.step(action)
            hand_actions += 1
            if done:
                # reward is from the player who just acted
                if player == hero:
                    hero_reward = reward
                else:
                    hero_reward = -reward
        rewards.append(hero_reward)
        if env.state.folded_player >= 0:
            fold_count += 1
        else:
            showdown_count += 1
        actions_per_hand.append(hand_actions)
        total_actions += hand_actions
    elapsed = time.perf_counter() - t0

    return {
        'hands': len(rewards),
        'avg_bb_per_hand': float(np.mean(rewards)),
        'std_bb': float(np.std(rewards)),
        'fold_rate': fold_count / len(rewards),
        'showdown_rate': showdown_count / len(rewards),
        'avg_actions_per_hand': float(np.mean(actions_per_hand)),
        'time_sec': elapsed,
        'hands_per_sec': len(rewards) / elapsed,
    }


def main():
    M = 5000
    print('=== Python reference (M=5000) ===')
    py = run_python(M, seed=42)
    for k, v in py.items():
        print(f'  {k}: {v}')

    print()
    print('=== Vec sim N=256 (M=5000) ===')
    vec256 = run_vec(N=256, M_hands=M, seed=42)
    for k, v in vec256.items():
        print(f'  {k}: {v}')

    print()
    print('=== Vec sim N=1024 (M=5000) ===')
    vec1024 = run_vec(N=1024, M_hands=M, seed=42)
    for k, v in vec1024.items():
        print(f'  {k}: {v}')

    print()
    print('=== Comparison ===')
    print(f'  bb/hand:  python={py["avg_bb_per_hand"]:+.3f}  vec256={vec256["avg_bb_per_hand"]:+.3f}  vec1024={vec1024["avg_bb_per_hand"]:+.3f}')
    print(f'  fold:     python={py["fold_rate"]:.3f}  vec256={vec256["fold_rate"]:.3f}  vec1024={vec1024["fold_rate"]:.3f}')
    print(f'  actions:  python={py["avg_actions_per_hand"]:.2f}  vec256={vec256["avg_actions_per_hand"]:.2f}  vec1024={vec1024["avg_actions_per_hand"]:.2f}')
    print(f'  speedup:  vec256={vec256["hands_per_sec"]/py["hands_per_sec"]:.1f}x  vec1024={vec1024["hands_per_sec"]/py["hands_per_sec"]:.1f}x')


if __name__ == '__main__':
    main()
