"""
Ralph Loop for SD-CFR: auto-converge training loop.

Continuously trains SD-CFR and checks exploitability until convergence.
If exploitability stalls, automatically adjusts hyperparameters and retries.

This implements the "ralph loop" pattern:
  while not converged:
      train(...)
      exploit = verify(...)
      if stalled: adjust_params(...)

Usage:
  python -m scripts.deep_cfr.auto_converge --game leduc --target 100
  python -m scripts.deep_cfr.auto_converge --game leduc --target 50 --max-rounds 10
"""

from __future__ import annotations

import argparse
import json
import os
import time

import torch

from .train import train_sdcfr
from .eval_agent import load_agent, compute_exploitability_leduc, compute_lbr_exploitability_hunl
from .tabular_cfr import TabularCFR


# ---------- Hyperparameter schedules ----------

LEDUC_PARAM_SCHEDULE = [
    # Round 0: paper-matched (Brown et al. 2019 + Steinberger PokerRL)
    {
        'iterations': 200,
        'traversals': 5000,
        'train_steps': 1200,
        'batch_size': 2048,
        'lr': 0.001,
        'buffer_size': 1_000_000,
        'label': 'paper-matched (200 iter, batch 2048, buf 1M)',
    },
    # Round 1: more iterations
    {
        'iterations': 300,
        'traversals': 5000,
        'train_steps': 1200,
        'batch_size': 2048,
        'lr': 0.001,
        'buffer_size': 2_000_000,
        'label': 'more iters (300 iter, 1.2K steps)',
    },
    # Round 2: more traversals per iteration
    {
        'iterations': 300,
        'traversals': 10000,
        'train_steps': 2000,
        'batch_size': 2048,
        'lr': 0.001,
        'buffer_size': 2_000_000,
        'label': 'more traversals (300 iter, 10K trav)',
    },
    # Round 3: aggressive
    {
        'iterations': 500,
        'traversals': 10000,
        'train_steps': 4000,
        'batch_size': 2048,
        'lr': 0.0005,
        'buffer_size': 5_000_000,
        'label': 'aggressive (500 iter, 10K trav, 4K steps)',
    },
    # Round 4: max effort
    {
        'iterations': 500,
        'traversals': 20000,
        'train_steps': 4000,
        'batch_size': 2048,
        'lr': 0.0003,
        'buffer_size': 10_000_000,
        'label': 'max effort (500 iter, 20K trav)',
    },
]

HUNL_PARAM_SCHEDULE = [
    # Round 0: Warm-up — small buffer, fast iterations to bootstrap strategy buffer
    {
        'iterations': 200,
        'traversals': 10000,
        'train_steps': 2000,
        'batch_size': 4096,
        'lr': 0.001,
        'buffer_size': 3_000_000,
        'hidden_dims': (256, 256, 256),
        'label': 'warmup (200 iter, 10K trav, [256,256,256], buf 3M)',
    },
    # Round 1: Continue from round 0 checkpoint — more traversals, same buffer cap
    {
        'iterations': 500,
        'traversals': 20000,
        'train_steps': 4000,
        'batch_size': 4096,
        'lr': 0.001,
        'buffer_size': 3_000_000,
        'hidden_dims': (256, 256, 256),
        'label': 'main (500 iter, 20K trav, [256,256,256], buf 3M)',
    },
    # Round 2: Continue — lower LR for fine-tuning
    {
        'iterations': 800,
        'traversals': 20000,
        'train_steps': 4000,
        'batch_size': 4096,
        'lr': 0.0005,
        'buffer_size': 3_000_000,
        'hidden_dims': (256, 256, 256),
        'label': 'refine (800 iter, 20K trav, lr=5e-4, buf 3M)',
    },
    # Round 3: Max effort — most traversals
    {
        'iterations': 1000,
        'traversals': 30000,
        'train_steps': 4000,
        'batch_size': 4096,
        'lr': 0.0003,
        'buffer_size': 3_000_000,
        'hidden_dims': (256, 256, 256),
        'label': 'max (1000 iter, 30K trav, lr=3e-4, buf 3M)',
    },
    # Round 4: Final push
    {
        'iterations': 1500,
        'traversals': 30000,
        'train_steps': 4000,
        'batch_size': 4096,
        'lr': 0.0002,
        'buffer_size': 3_000_000,
        'hidden_dims': (256, 256, 256),
        'label': 'final (1500 iter, 30K trav, lr=2e-4, buf 3M)',
    },
]

# Full-game schedule (preflop→river): larger buffers needed due to deeper game tree
FULL_GAME_PARAM_SCHEDULE = [
    {
        'iterations': 100,
        'traversals': 5000,
        'train_steps': 2000,
        'batch_size': 4096,
        'lr': 0.001,
        'buffer_size': 4_000_000,
        'hidden_dims': (256, 256),
        'label': 'full-game baseline (100 iter, 5K trav, [256,256])',
    },
    {
        'iterations': 200,
        'traversals': 10000,
        'train_steps': 4000,
        'batch_size': 4096,
        'lr': 0.001,
        'buffer_size': 10_000_000,
        'hidden_dims': (256, 256),
        'label': 'full-game scaled (200 iter, 10K trav, [256,256])',
    },
    {
        'iterations': 300,
        'traversals': 20000,
        'train_steps': 4000,
        'batch_size': 8192,
        'lr': 0.001,
        'buffer_size': 20_000_000,
        'hidden_dims': (512, 512),
        'label': 'full-game wide (300 iter, 20K trav, [512,512])',
    },
    {
        'iterations': 400,
        'traversals': 30000,
        'train_steps': 4000,
        'batch_size': 10240,
        'lr': 0.0005,
        'buffer_size': 40_000_000,
        'hidden_dims': (512, 512, 512),
        'label': 'full-game deep (400 iter, 30K trav, [512,512,512])',
    },
    {
        'iterations': 500,
        'traversals': 50000,
        'train_steps': 4000,
        'batch_size': 10240,
        'lr': 0.0003,
        'buffer_size': 80_000_000,
        'hidden_dims': (512, 512, 512),
        'label': 'full-game max (500 iter, 50K trav, [512,512,512])',
    },
]


def auto_converge(
    game: str = 'leduc',
    target_exploit: float = 100.0,
    max_rounds: int = 5,
    device_str: str = 'auto',
    checkpoint_base: str = 'checkpoints/sdcfr_auto',
    game_config: str = 'srp_50bb',
    start_round: int = 0,
    train_mode: str = 'auto',
) -> dict:
    """
    Ralph loop: train SD-CFR until exploitability < target, or max_rounds exhausted.

    Returns:
        dict with 'converged', 'best_exploit', 'best_checkpoint', 'rounds', 'history'
    """
    if device_str == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(device_str)

    is_leduc = game == 'leduc'
    if is_leduc:
        schedule = LEDUC_PARAM_SCHEDULE
    elif game_config.startswith('full_'):
        schedule = FULL_GAME_PARAM_SCHEDULE
    else:
        schedule = HUNL_PARAM_SCHEDULE

    history = []
    best_exploit = float('inf')
    best_checkpoint = None

    # Also compute tabular baseline for reference (Leduc only)
    tabular_exploit = None
    if is_leduc:
        print("Computing tabular CFR baseline (1000 iter)...")
        tab = TabularCFR()
        tab.train(1000)
        tabular_exploit = tab.compute_exploitability()
        print(f"Tabular CFR exploitability: {tabular_exploit:.2f} mbb/g\n")

    prev_best_ckpt = None  # Track best checkpoint for cross-round resume

    for round_idx in range(start_round, min(max_rounds, len(schedule))):
        params = schedule[round_idx]
        round_dir = f"{checkpoint_base}/round{round_idx}"

        print(f"\n{'='*60}")
        print(f"RALPH LOOP — Round {round_idx + 1}/{max_rounds}")
        print(f"Config: {params['label']}")
        print(f"Target: {target_exploit:.0f} mbb/g | Best so far: {best_exploit:.1f} mbb/g")
        print(f"{'='*60}\n")

        t0 = time.time()

        # Resume strategy: prefer existing checkpoint in this round (crash recovery),
        # then fall back to previous round's best checkpoint (cross-round continuity)
        resume_path = None
        if os.path.isdir(round_dir):
            existing_ckpts = sorted(
                [f for f in os.listdir(round_dir) if f.endswith('.pt')],
                key=lambda f: int(f.split('iter')[1].split('.')[0]),
            )
            if existing_ckpts:
                resume_path = os.path.join(round_dir, existing_ckpts[-1])
                print(f"  Resuming from existing checkpoint: {resume_path}")

        if resume_path is None and prev_best_ckpt is not None:
            resume_path = prev_best_ckpt
            print(f"  Continuing from previous round checkpoint: {resume_path}")

        # Use built-in eval_interval for periodic LBR during training
        eval_interval = max(params['iterations'] // 4, 50)

        # Train
        train_sdcfr(
            game=game,
            iterations=params['iterations'],
            traversals_per_iter=params['traversals'],
            train_steps=params['train_steps'],
            batch_size=params['batch_size'],
            lr=params['lr'],
            buffer_size=params['buffer_size'],
            device_str=device_str,
            checkpoint_dir=round_dir,
            checkpoint_interval=max(params['iterations'] // 4, 25),
            game_config=game_config,
            hidden_dims=params.get('hidden_dims'),
            train_mode=train_mode,
            resume_path=resume_path,
            eval_interval=eval_interval if not is_leduc else 0,
            eval_samples=5000,
        )

        elapsed = time.time() - t0

        # Find the latest checkpoint
        ckpt_files = sorted(
            [f for f in os.listdir(round_dir) if f.endswith('.pt')],
            key=lambda f: int(f.split('iter')[1].split('.')[0]),
        )
        if not ckpt_files:
            print(f"  No checkpoints found in {round_dir}, skipping evaluation")
            continue

        latest_ckpt = os.path.join(round_dir, ckpt_files[-1])

        # Verify: compute exploitability
        print(f"\nVerifying: computing exploitability...")
        if is_leduc:
            agent0 = load_agent(latest_ckpt, player=0, device=str(device), mode='ensemble')
            agent1 = load_agent(latest_ckpt, player=1, device=str(device), mode='ensemble')
            exploit = compute_exploitability_leduc([agent0, agent1])
        else:
            from .game_state import GameConfig
            configs = {
                'srp_50bb': GameConfig.srp_50bb,
                'bet3_50bb': GameConfig.bet3_50bb,
                'srp_100bb': GameConfig.srp_100bb,
                'bet3_100bb': GameConfig.bet3_100bb,
                'full_50bb': GameConfig.full_50bb,
                'full_100bb': GameConfig.full_100bb,
                'expanded_srp_50bb': GameConfig.expanded_srp_50bb,
            }
            cf = configs.get(game_config, GameConfig.srp_50bb)
            # Use 'average' mode for LBR — ensemble is too slow (loads state_dict per call × 100 nets)
            agent0 = load_agent(latest_ckpt, player=0, device=str(device), mode='average')
            agent1 = load_agent(latest_ckpt, player=1, device=str(device), mode='average')
            n_lbr = 10000  # Fixed for comparability across rounds
            exploit = compute_lbr_exploitability_hunl(
                [agent0, agent1], config_factory=cf, n_samples=n_lbr)

        round_result = {
            'round': round_idx,
            'params': params['label'],
            'exploitability': exploit,
            'checkpoint': latest_ckpt,
            'time_s': elapsed,
        }
        history.append(round_result)

        if exploit < best_exploit:
            best_exploit = exploit
            best_checkpoint = latest_ckpt

        # Track for cross-round resume
        prev_best_ckpt = latest_ckpt

        print(f"\n{'-'*40}")
        print(f"Round {round_idx + 1} result:")
        print(f"  Exploitability: {exploit:.2f} mbb/g")
        print(f"  Best so far:    {best_exploit:.2f} mbb/g")
        print(f"  Target:         {target_exploit:.0f} mbb/g")
        if tabular_exploit is not None:
            print(f"  Tabular ref:    {tabular_exploit:.2f} mbb/g")
        print(f"  Time:           {elapsed:.0f}s")
        print(f"  Checkpoint:     {latest_ckpt}")
        print(f"{'-'*40}")

        # Check convergence
        if exploit <= target_exploit:
            print(f"\n[OK] CONVERGED! Exploitability {exploit:.2f} <= target {target_exploit:.0f} mbb/g")
            break
        else:
            print(f"\n[X] Not converged yet. Escalating to next parameter set...")

    # Summary
    converged = best_exploit <= target_exploit
    print(f"\n{'='*60}")
    print(f"RALPH LOOP COMPLETE")
    print(f"  Converged: {'YES' if converged else 'NO'}")
    print(f"  Best exploitability: {best_exploit:.2f} mbb/g")
    print(f"  Best checkpoint: {best_checkpoint}")
    print(f"  Rounds used: {len(history)}/{max_rounds}")
    print(f"{'='*60}")

    # Save summary
    summary = {
        'converged': converged,
        'best_exploit': best_exploit,
        'best_checkpoint': best_checkpoint,
        'target': target_exploit,
        'rounds': len(history),
        'history': history,
        'tabular_exploit': tabular_exploit,
    }
    summary_path = f"{checkpoint_base}/auto_converge_summary.json"
    os.makedirs(checkpoint_base, exist_ok=True)
    with open(summary_path, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"Summary saved: {summary_path}")

    return summary


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='SD-CFR Auto-Converge (Ralph Loop)')
    parser.add_argument('--game', type=str, default='leduc', choices=['leduc', 'hunl'])
    parser.add_argument('--target', type=float, default=100.0,
                        help='Target exploitability in mbb/g')
    parser.add_argument('--max-rounds', type=int, default=5,
                        help='Maximum number of training rounds')
    parser.add_argument('--device', type=str, default='auto')
    parser.add_argument('--checkpoint-base', type=str, default='checkpoints/sdcfr_auto')
    parser.add_argument('--game-config', type=str, default='srp_50bb')
    parser.add_argument('--start-round', type=int, default=0,
                        help='Skip to this round (for resuming after crash)')
    parser.add_argument('--train-mode', type=str, default='auto',
                        choices=['standard', 'warm', 'aggregated', 'auto'],
                        help='Training mode (default: auto — aggregated for Leduc, warm for HUNL)')

    args = parser.parse_args()

    auto_converge(
        game=args.game,
        target_exploit=args.target,
        max_rounds=args.max_rounds,
        device_str=args.device,
        checkpoint_base=args.checkpoint_base,
        game_config=args.game_config,
        start_round=args.start_round,
        train_mode=args.train_mode,
    )


if __name__ == '__main__':
    main()
