"""
Fast experiment: compare 3 neural SD-CFR configs on Leduc.
A) Original: reinit, 1200 steps, batch 2048, lr 0.001
B) Warm-start: no reinit, 2000 steps, batch 512, lr 0.0005
C) Aggregated: compute per-info-set avg targets, train on clean data
"""
import time
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

from scripts.deep_cfr.game_state import LeducGameState
from scripts.deep_cfr.encoding import LeducEncoder
from scripts.deep_cfr.networks import LeducAdvantageNetwork, StrategyBuffer
from scripts.deep_cfr.reservoir import ReservoirBuffer, AdvantageSample
from scripts.deep_cfr.train import batched_traverse_leduc, _regret_match, _reinit_weights
from scripts.deep_cfr.eval_agent import compute_exploitability_leduc, SDCFRAgent

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
MAX_ACTIONS = 4
ITERS = 100
TRAVERSALS = 5000
HIDDEN = (64, 64, 64)


def train_standard(net, buf, max_iter, steps, batch_size, lr, reinit):
    if reinit:
        _reinit_weights(net)
    net.to(device).train()
    opt = optim.Adam(net.parameters(), lr=lr)
    total_loss = 0.0
    for _ in range(steps):
        states, targets, masks, weights = buf.sample_batch(batch_size, device)
        preds = net(states, masks)
        diff = (preds - targets) ** 2 * masks
        loss = (diff.sum(dim=-1) * weights).mean()
        opt.zero_grad()
        loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        opt.step()
        total_loss += loss.item()
    return total_loss / max(steps, 1)


def train_aggregated(net, buf, max_iter, steps_per_epoch, lr, reinit):
    """Aggregate buffer by info set encoding, train on clean targets."""
    if reinit:
        _reinit_weights(net)
    net.to(device).train()

    agg: dict[bytes, dict] = {}
    for s in buf.buffer:
        key = s.state.tobytes()
        if key not in agg:
            agg[key] = {'state': s.state, 'mask': s.legal_mask,
                        'wadv': np.zeros(MAX_ACTIONS, dtype=np.float64), 'wsum': 0.0}
        w = s.iteration / max(max_iter, 1)
        agg[key]['wadv'] += w * s.advantages.astype(np.float64)
        agg[key]['wsum'] += w

    states_t = torch.from_numpy(np.stack([v['state'] for v in agg.values()])).to(device)
    targets_t = torch.from_numpy(np.stack([
        (v['wadv'] / max(v['wsum'], 1e-8)).astype(np.float32) for v in agg.values()
    ])).to(device)
    masks_t = torch.from_numpy(np.stack([v['mask'] for v in agg.values()])).to(device)
    n = len(agg)

    opt = optim.Adam(net.parameters(), lr=lr)
    total_loss = 0.0
    total_steps = 0
    batch_size = min(64, n)

    for epoch in range(steps_per_epoch):
        indices = torch.randperm(n, device=device)
        for start in range(0, n, batch_size):
            idx = indices[start:start + batch_size]
            preds = net(states_t[idx], masks_t[idx])
            diff = (preds - targets_t[idx]) ** 2 * masks_t[idx]
            loss = diff.sum(dim=-1).mean()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            total_loss += loss.item()
            total_steps += 1

    return total_loss / max(total_steps, 1)


def compute_exploit(strategy_buffers):
    sb0, sb1 = StrategyBuffer(), StrategyBuffer()
    sb0.networks = list(strategy_buffers[0].networks)
    sb1.networks = list(strategy_buffers[1].networks)
    a0 = SDCFRAgent(sb0, LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN), torch.device('cpu'), mode='ensemble')
    a1 = SDCFRAgent(sb1, LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN), torch.device('cpu'), mode='ensemble')
    return compute_exploitability_leduc([a0, a1])


def run(name, train_fn, **kwargs):
    print(f"\n--- {name} ---", flush=True)
    nets = [LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN).to(device) for _ in range(2)]
    bufs = [ReservoirBuffer(2_000_000), ReservoirBuffer(2_000_000)]
    sbufs = [StrategyBuffer(), StrategyBuffer()]

    t0 = time.time()
    for t in range(ITERS):
        for p in range(2):
            batched_traverse_leduc(TRAVERSALS, p, nets, bufs[p], t, device, MAX_ACTIONS, 1024)
            loss = train_fn(nets[p], bufs[p], max_iter=t+1, **kwargs)
            sbufs[p].add(nets[p], t)

        if (t + 1) % 25 == 0:
            exploit = compute_exploit(sbufs)
            print(f"  Iter {t+1:3d}: exploit={exploit:8.1f} mbb/g | "
                  f"loss={loss:.4f} | buf={len(bufs[0]):,} | "
                  f"elapsed={time.time()-t0:.0f}s", flush=True)

    return sbufs


# A) Original
run("A: Original (reinit, 1200 steps, batch 2048, lr 0.001)",
    train_standard, steps=1200, batch_size=2048, lr=0.001, reinit=True)

# B) Warm-start
run("B: Warm-start (no reinit, 2000 steps, batch 512, lr 0.0005)",
    train_standard, steps=2000, batch_size=512, lr=0.0005, reinit=False)

# C) Aggregated targets with reinit
run("C: Aggregated targets (reinit, 300 epochs)",
    train_aggregated, steps_per_epoch=300, lr=0.001, reinit=True)

# D) Aggregated targets with warm-start
run("D: Aggregated targets + warm-start (100 epochs)",
    train_aggregated, steps_per_epoch=100, lr=0.001, reinit=False)

print("\nAll done!", flush=True)
