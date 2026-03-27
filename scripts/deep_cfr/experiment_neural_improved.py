"""
Experiment: Neural SD-CFR with improved training regime.

Key insights from tabular SD-CFR:
1. The algorithm works — average strategy converges to 27.5 mbb/g
2. The neural net's per-iteration strategies are too inaccurate
3. Root cause: at iter 80, buffer has 1.4M samples but only 683 training steps = ~1 epoch
4. Fix: more training + warm-start + lower LR

This experiment tests several configurations:
A) Original: 1200 steps, batch 2048, lr 0.001, reinit from scratch
B) More training: 5000 steps, batch 512, lr 0.0005, reinit from scratch
C) Warm-start: same as B but initialize from previous iteration's weights
D) Aggregated targets: compute per-info-set weighted average before training
"""
import time
import random
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from scripts.deep_cfr.game_state import LeducGameState
from scripts.deep_cfr.encoding import LeducEncoder
from scripts.deep_cfr.networks import LeducAdvantageNetwork, StrategyBuffer
from scripts.deep_cfr.reservoir import ReservoirBuffer, AdvantageSample
from scripts.deep_cfr.train import _regret_match, _reinit_weights
from scripts.deep_cfr.eval_agent import compute_exploitability_leduc, SDCFRAgent


device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
MAX_ACTIONS = 4
ITERS = 150
TRAVERSALS = 5000


def batched_traverse(n_trav, traverser, nets, buf, iteration, device):
    """Simplified batched traversal."""
    from scripts.deep_cfr.train import batched_traverse_leduc
    return batched_traverse_leduc(n_trav, traverser, nets, buf, iteration, device, MAX_ACTIONS, 1024)


def train_net_standard(net, buffer, device, max_iter, steps, batch_size, lr, reinit=True):
    """Train advantage network with standard approach."""
    if reinit:
        _reinit_weights(net)
    net.to(device)
    net.train()
    optimizer = optim.Adam(net.parameters(), lr=lr)
    total_loss = 0.0

    for step in range(steps):
        states, targets, masks, weights = buffer.sample_batch(batch_size, device)
        preds = net(states, masks)
        diff = (preds - targets) ** 2 * masks
        per_sample_loss = diff.sum(dim=-1)
        weighted_loss = (per_sample_loss * weights).mean()

        optimizer.zero_grad()
        weighted_loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        optimizer.step()
        total_loss += weighted_loss.item()

    return total_loss / max(steps, 1)


def train_net_aggregated(net, buffer, device, max_iter, steps, batch_size, lr, reinit=True):
    """Train on per-info-key aggregated targets (cleaner signal)."""
    if reinit:
        _reinit_weights(net)
    net.to(device)
    net.train()

    # Aggregate samples by their feature encoding (unique per info set)
    agg: dict[bytes, dict] = {}
    for sample in buffer.buffer:
        key = sample.state.tobytes()
        if key not in agg:
            agg[key] = {
                'state': sample.state,
                'mask': sample.legal_mask,
                'weighted_adv': np.zeros(MAX_ACTIONS, dtype=np.float64),
                'weight_sum': 0.0,
            }
        w = sample.iteration / max(max_iter, 1)
        agg[key]['weighted_adv'] += w * sample.advantages.astype(np.float64)
        agg[key]['weight_sum'] += w

    # Build clean dataset: each info set → single averaged target
    states = []
    targets = []
    masks = []
    for v in agg.values():
        states.append(v['state'])
        targets.append((v['weighted_adv'] / max(v['weight_sum'], 1e-8)).astype(np.float32))
        masks.append(v['mask'])

    states_t = torch.from_numpy(np.stack(states)).to(device)
    targets_t = torch.from_numpy(np.stack(targets)).to(device)
    masks_t = torch.from_numpy(np.stack(masks)).to(device)

    optimizer = optim.Adam(net.parameters(), lr=lr)
    total_loss = 0.0
    n = len(states)

    for step in range(steps):
        # Shuffle and batch
        indices = torch.randperm(n)
        for start in range(0, n, batch_size):
            idx = indices[start:start + batch_size]
            preds = net(states_t[idx], masks_t[idx])
            diff = (preds - targets_t[idx]) ** 2 * masks_t[idx]
            loss = diff.sum(dim=-1).mean()

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            optimizer.step()
            total_loss += loss.item()

    return total_loss / max(steps, 1)


def run_experiment(name, train_fn, steps, batch_size, lr, reinit, hidden_dims=(64, 64, 64)):
    print(f"\n{'='*60}")
    print(f"Config: {name}")
    print(f"  steps={steps}, batch={batch_size}, lr={lr}, reinit={reinit}, hidden={hidden_dims}")
    print(f"{'='*60}", flush=True)

    nets = [LeducAdvantageNetwork(MAX_ACTIONS, hidden_dims).to(device) for _ in range(2)]
    buffers = [ReservoirBuffer(2_000_000), ReservoirBuffer(2_000_000)]
    strategy_buffers = [StrategyBuffer(), StrategyBuffer()]

    t_start = time.time()

    for t in range(ITERS):
        for p in range(2):
            batched_traverse(TRAVERSALS, p, nets, buffers[p], t, device)

            actual_steps = steps  # Fixed steps for this experiment
            loss = train_fn(
                nets[p], buffers[p], device,
                max_iter=t + 1,
                steps=actual_steps,
                batch_size=batch_size,
                lr=lr,
                reinit=reinit,
            )

            strategy_buffers[p].add(nets[p], t)

        if (t + 1) % 25 == 0:
            # Compute exploitability with ensemble (average strategy)
            sb0, sb1 = StrategyBuffer(), StrategyBuffer()
            sb0.networks = list(strategy_buffers[0].networks)
            sb1.networks = list(strategy_buffers[1].networks)
            a0 = SDCFRAgent(sb0, LeducAdvantageNetwork(MAX_ACTIONS, hidden_dims), torch.device('cpu'), mode='ensemble')
            a1 = SDCFRAgent(sb1, LeducAdvantageNetwork(MAX_ACTIONS, hidden_dims), torch.device('cpu'), mode='ensemble')
            exploit = compute_exploitability_leduc([a0, a1])
            elapsed = time.time() - t_start
            print(
                f"  Iter {t+1:4d}: exploit={exploit:8.1f} mbb/g | "
                f"loss={loss:.4f} | buf={len(buffers[0]):,} | "
                f"elapsed={elapsed:.0f}s",
                flush=True,
            )

    return strategy_buffers


# Config A: Original (baseline)
run_experiment(
    "A: Original (baseline)",
    train_net_standard, steps=1200, batch_size=2048, lr=0.001, reinit=True,
)

# Config B: More training, smaller batch, lower LR
run_experiment(
    "B: More training (reinit)",
    train_net_standard, steps=5000, batch_size=512, lr=0.0005, reinit=True,
)

# Config C: Warm-start (no reinit)
run_experiment(
    "C: Warm-start + more training",
    train_net_standard, steps=5000, batch_size=512, lr=0.0005, reinit=False,
)

# Config D: Aggregated targets (no sample noise)
run_experiment(
    "D: Aggregated targets (reinit)",
    train_net_aggregated, steps=200, batch_size=64, lr=0.001, reinit=True,
)

# Config E: Aggregated targets + warm-start
run_experiment(
    "E: Aggregated targets + warm-start",
    train_net_aggregated, steps=200, batch_size=64, lr=0.001, reinit=False,
)

print("\nAll experiments done!", flush=True)
