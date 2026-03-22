"""
Quick validation: verify SD-CFR fixes improve Leduc convergence.

Pre-fix baseline: ~230 mbb/g at 200 iterations (auto_converge v5)
Target: <100 mbb/g at 200 iterations

Fixes applied:
  1. Argmax fallback in _regret_match (Brown et al. 2019 Sec 4.1)
  2. Network architecture 3x64 (paper-matched)
  3. Hyperparameters: batch=2048, steps=1200, buffer=1M

Usage:
  python -m scripts.deep_cfr.validate_fixes
  python -m scripts.deep_cfr.validate_fixes --iterations 100 --device cpu
"""

from __future__ import annotations

import argparse
import os
import time

import torch

from .train import train_sdcfr
from .eval_agent import load_agent, compute_exploitability_leduc
from .tabular_cfr import TabularCFR


def validate(
    iterations: int = 200,
    device_str: str = 'auto',
    checkpoint_dir: str = 'checkpoints/sdcfr_fix_validate',
) -> None:
    if device_str == 'auto':
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
    else:
        device = device_str

    print("=" * 60)
    print("SD-CFR Fix Validation — Leduc Hold'em")
    print("=" * 60)

    # Tabular baseline
    print("\nComputing tabular CFR baseline (1000 iter)...")
    tab = TabularCFR()
    tab.train(1000)
    tab_exploit = tab.compute_exploitability()
    print(f"Tabular CFR exploitability: {tab_exploit:.2f} mbb/g\n")

    # Paper-matched hyperparams
    print("Training SD-CFR with paper-matched hyperparams...")
    print(f"  Network: 3x64, Batch: 2048, Steps: 1200, Buffer: 1M")
    print(f"  Device: {device}\n")

    t0 = time.time()
    train_sdcfr(
        game='leduc',
        iterations=iterations,
        traversals_per_iter=5000,
        train_steps=1200,
        batch_size=2048,
        lr=0.001,
        buffer_size=1_000_000,
        device_str=device,
        checkpoint_dir=checkpoint_dir,
        checkpoint_interval=25,
        disable_tqdm=True,
    )
    total_time = time.time() - t0

    # Evaluate at all checkpoints
    print(f"\n{'=' * 60}")
    print("Exploitability Convergence Trajectory")
    print(f"{'=' * 60}")
    print(f"{'Iter':>6} | {'Exploit (mbb/g)':>16} | {'vs Baseline':>12}")
    print("-" * 42)

    ckpt_files = sorted(
        [f for f in os.listdir(checkpoint_dir) if f.endswith('.pt')],
        key=lambda f: int(f.split('iter')[1].split('.')[0]),
    )

    baseline = 230.42  # auto_converge v5 result
    for ckpt_file in ckpt_files:
        ckpt_path = os.path.join(checkpoint_dir, ckpt_file)
        iter_num = int(ckpt_file.split('iter')[1].split('.')[0])

        agent0 = load_agent(ckpt_path, player=0, device=device, mode='ensemble')
        agent1 = load_agent(ckpt_path, player=1, device=device, mode='ensemble')
        exploit = compute_exploitability_leduc([agent0, agent1])

        improvement = ((baseline - exploit) / baseline) * 100
        print(f"{iter_num:>6} | {exploit:>13.2f}    | {improvement:>+9.1f}%")

    print("-" * 42)
    print(f"Tabular CFR reference: {tab_exploit:.2f} mbb/g")
    print(f"Pre-fix baseline (v5): {baseline:.2f} mbb/g")
    print(f"Total training time: {total_time:.0f}s")
    print(f"{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(description='SD-CFR Fix Validation')
    parser.add_argument('--iterations', type=int, default=200)
    parser.add_argument('--device', type=str, default='auto')
    parser.add_argument('--checkpoint-dir', type=str, default='checkpoints/sdcfr_fix_validate')
    args = parser.parse_args()

    validate(
        iterations=args.iterations,
        device_str=args.device,
        checkpoint_dir=args.checkpoint_dir,
    )


if __name__ == '__main__':
    main()
