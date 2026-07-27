#!/usr/bin/env python3
"""Profile a single worker's per-hand time breakdown.

Goal: identify what's actually slow in the Python game simulation
so we know where to focus C++ rewriting effort.
"""
import cProfile
import pstats
import os
import sys
import time
import random
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.environment import HUNLEnvironment


def simulate_hands(n_hands: int, starting_stack: float = 200.0) -> tuple[int, float]:
    """Run n_hands of self-play with random actions (no GPU). Return (hands, seconds)."""
    env = HUNLEnvironment(starting_stack=starting_stack)
    actions = 0
    t0 = time.perf_counter()
    for _ in range(n_hands):
        obs = env.reset()
        done = False
        while not done:
            legal = np.where(obs['legal_mask'] > 0)[0]
            if len(legal) == 0:
                break
            action = int(random.choice(legal))
            obs, reward, done = env.step(action)
            actions += 1
        env.chips_committed(0)
        env.chips_committed(1)
    elapsed = time.perf_counter() - t0
    return n_hands, actions, elapsed


def main():
    # Warmup
    print('Warmup...')
    simulate_hands(100)

    # Speed measurement (no profiling overhead)
    print('Speed measurement (no profile)...')
    h, a, dt = simulate_hands(2000)
    print(f'  {h} hands, {a} actions in {dt:.2f}s')
    print(f'  hands/sec/worker: {h/dt:.1f}')
    print(f'  actions/sec/worker: {a/dt:.1f}')
    print(f'  avg actions per hand: {a/h:.1f}')

    # cProfile breakdown
    print('\ncProfile breakdown over 500 hands...')
    pr = cProfile.Profile()
    pr.enable()
    simulate_hands(500)
    pr.disable()
    s = pstats.Stats(pr).sort_stats('cumulative')
    s.print_stats(25)


if __name__ == '__main__':
    main()
