"""
Experiment: SD-CFR with Policy Network for average strategy.

Key insight from Deep CFR paper (Brown et al., 2019):
- Advantage networks approximate cumulative regrets (current strategy)
- A separate POLICY NETWORK approximates the average strategy directly
- This is more accurate than ensembling 100 advantage network snapshots

The policy network:
1. Takes same input as advantage network
2. Outputs action probabilities (softmax) instead of advantages
3. Trained with cross-entropy loss on regret-matched strategies
4. Uses Linear CFR weighting (later iterations count more)

Expected result: should converge close to tabular SD-CFR (27.5 mbb/g).
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
from scripts.deep_cfr.networks import LeducAdvantageNetwork, LeducPolicyNetwork, StrategyBuffer
from scripts.deep_cfr.reservoir import ReservoirBuffer, AdvantageSample
from scripts.deep_cfr.train import batched_traverse_leduc, _regret_match, _reinit_weights
from scripts.deep_cfr.eval_agent import compute_exploitability_leduc, SDCFRAgent

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
MAX_ACTIONS = 4
ITERS = 150
TRAVERSALS = 5000
HIDDEN = (64, 64, 64)
POLICY_HIDDEN = (128, 128)


# ---------- Policy buffer: stores (state, strategy) pairs ----------

class PolicySample:
    __slots__ = ('state', 'strategy', 'legal_mask', 'iteration')
    def __init__(self, state, strategy, legal_mask, iteration):
        self.state = state
        self.strategy = strategy
        self.legal_mask = legal_mask
        self.iteration = iteration


class PolicyBuffer:
    """Stores (state, strategy) pairs for policy network training."""
    def __init__(self, max_size=2_000_000):
        self.max_size = max_size
        self.buffer: list[PolicySample] = []
        self.n_seen = 0
        self._max_iteration = 0

    def add(self, sample: PolicySample):
        self.n_seen += 1
        if sample.iteration > self._max_iteration:
            self._max_iteration = sample.iteration
        if len(self.buffer) < self.max_size:
            self.buffer.append(sample)
        else:
            idx = random.randint(0, self.n_seen - 1)
            if idx < self.max_size:
                self.buffer[idx] = sample

    def __len__(self):
        return len(self.buffer)

    def sample_batch(self, batch_size, device):
        indices = random.sample(range(len(self.buffer)), min(batch_size, len(self.buffer)))
        max_iter = max(self._max_iteration, 1)
        states = np.stack([self.buffer[i].state for i in indices])
        strategies = np.stack([self.buffer[i].strategy for i in indices])
        masks = np.stack([self.buffer[i].legal_mask for i in indices])
        weights = np.array([self.buffer[i].iteration / max_iter for i in indices], dtype=np.float32)
        return (
            torch.from_numpy(states).to(device),
            torch.from_numpy(strategies).to(device),
            torch.from_numpy(masks).to(device),
            torch.from_numpy(weights).to(device),
        )


# ---------- Traversal that collects policy samples ----------

ACTION_SLOT_MAP = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}

def _traverse_coro_with_policy(state, traverser, adv_buffer, policy_buffer, iteration, max_actions=4):
    """Generator traversal that also collects policy network training data."""
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    # Yield for batched NN eval
    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    action_slots = [ACTION_SLOT_MAP[a] for a in actions]

    # Store policy sample: the regret-matched strategy at this state
    # This is the current strategy that will be averaged for the final policy
    policy_buffer.add(PolicySample(
        state=raw.copy(),
        strategy=strategy.copy(),
        legal_mask=legal_mask.copy(),
        iteration=iteration + 1,
    ))

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[action_slots[i]] = yield from _traverse_coro_with_policy(
                child, traverser, adv_buffer, policy_buffer, iteration, max_actions)

        ev = float(np.sum(strategy * values))
        inst_advantages = (values - ev) * legal_mask
        adv_buffer.add(AdvantageSample(
            state=raw, advantages=inst_advantages,
            legal_mask=legal_mask, iteration=iteration + 1))
        return ev
    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return (yield from _traverse_coro_with_policy(
            child, traverser, adv_buffer, policy_buffer, iteration, max_actions))


def batched_traverse_with_policy(
    n_traversals, traverser, adv_nets, adv_buffer, policy_buffer,
    iteration, device, max_actions=4, concurrent=1024,
):
    """Batched traversal that also collects policy samples."""
    ev_sum = 0.0
    n_spawned = 0
    fibers = []

    def _spawn():
        nonlocal n_spawned
        state = LeducGameState().deal_new_hand()
        gen = _traverse_coro_with_policy(
            state, traverser, adv_buffer, policy_buffer, iteration, max_actions)
        req = next(gen)
        fibers.append((gen, req))
        n_spawned += 1

    for _ in range(min(concurrent, n_traversals)):
        _spawn()

    while fibers:
        p0_idx, p0_raws, p0_masks = [], [], []
        p1_idx, p1_raws, p1_masks = [], [], []

        for i, (_, req) in enumerate(fibers):
            player, raw, mask = req
            if player == 0:
                p0_idx.append(i); p0_raws.append(raw); p0_masks.append(mask)
            else:
                p1_idx.append(i); p1_raws.append(raw); p1_masks.append(mask)

        results = [None] * len(fibers)
        for indices, raws, masks, net in [
            (p0_idx, p0_raws, p0_masks, adv_nets[0]),
            (p1_idx, p1_raws, p1_masks, adv_nets[1]),
        ]:
            if not indices:
                continue
            raw_t = torch.from_numpy(np.stack(raws)).to(device)
            mask_t = torch.from_numpy(np.stack(masks)).to(device)
            with torch.inference_mode():
                out = net(raw_t, mask_t).cpu().numpy()
            for j, idx in enumerate(indices):
                results[idx] = out[j]

        new_fibers = []
        for i, (gen, _) in enumerate(fibers):
            try:
                new_req = gen.send(results[i])
                new_fibers.append((gen, new_req))
            except StopIteration as e:
                ev_sum += e.value
                if n_spawned < n_traversals:
                    _spawn()
                    new_fibers.append(fibers[-1])
                    fibers.pop()
        fibers = new_fibers

    return ev_sum


# ---------- Train advantage network (aggregated targets + warm-start) ----------

def train_advantage_aggregated(net, buffer, device, max_iter, epochs=100, lr=0.001):
    """Train on per-info-set aggregated targets."""
    net.to(device).train()
    agg = {}
    for s in buffer.buffer:
        key = s.state.tobytes()
        if key not in agg:
            agg[key] = {'state': s.state, 'mask': s.legal_mask,
                        'wadv': np.zeros(MAX_ACTIONS, dtype=np.float64), 'wsum': 0.0}
        w = s.iteration / max(max_iter, 1)
        agg[key]['wadv'] += w * s.advantages.astype(np.float64)
        agg[key]['wsum'] += w

    if not agg:
        return 0.0

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

    for _ in range(epochs):
        idx = torch.randperm(n, device=device)
        for start in range(0, n, batch_size):
            i = idx[start:start + batch_size]
            preds = net(states_t[i], masks_t[i])
            diff = (preds - targets_t[i]) ** 2 * masks_t[i]
            loss = diff.sum(dim=-1).mean()
            opt.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(net.parameters(), 1.0)
            opt.step()
            total_loss += loss.item()
            total_steps += 1

    return total_loss / max(total_steps, 1)


# ---------- Train policy network ----------

def train_policy_net(policy_net, policy_buffer, device, steps=2000, batch_size=512, lr=0.001, reinit=False):
    """Train policy network with weighted cross-entropy on strategy targets."""
    if reinit:
        _reinit_weights(policy_net)
    policy_net.to(device).train()
    opt = optim.Adam(policy_net.parameters(), lr=lr)
    total_loss = 0.0

    for step in range(steps):
        states, strategies, masks, weights = policy_buffer.sample_batch(batch_size, device)

        # Policy network outputs probabilities (via softmax in forward)
        pred_probs = policy_net(states, masks)  # Already softmaxed

        # Cross-entropy: -Σ target * log(pred), weighted by iteration
        # Add small epsilon to avoid log(0)
        log_pred = torch.log(pred_probs + 1e-8) * masks
        ce_loss = -(strategies * log_pred).sum(dim=-1)  # Per-sample CE
        weighted_loss = (ce_loss * weights).mean()

        opt.zero_grad()
        weighted_loss.backward()
        nn.utils.clip_grad_norm_(policy_net.parameters(), 1.0)
        opt.step()
        total_loss += weighted_loss.item()

    return total_loss / max(steps, 1)


# ---------- Policy agent for exploitability ----------

class PolicyNetAgent:
    """Agent that uses the policy network directly for action probabilities."""
    def __init__(self, policy_net, device):
        self.net = policy_net.to(device)
        self.net.eval()
        self.device = device

    def get_strategy(self, state):
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])

        raw = LeducEncoder.encode(state)
        legal_mask = LeducEncoder.encode_legal_mask(state, MAX_ACTIONS)
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(self.device)

        with torch.no_grad():
            probs = self.net(raw_t, mask_t).squeeze(0).cpu().numpy()

        action_probs = np.array([probs[ACTION_SLOT_MAP[a]] for a in actions])
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)
        return actions, action_probs.astype(np.float32)


# ---------- Main experiment ----------

print(f"SD-CFR with Policy Network: {ITERS} iters, {TRAVERSALS} trav/iter", flush=True)
print(f"Device: {device}", flush=True)
print(f"Advantage net: {HIDDEN}, Policy net: {POLICY_HIDDEN}", flush=True)
print(f"Advantage: aggregated targets, warm-start, 100 epochs", flush=True)
print(f"Policy: warm-start, 2000 steps, cross-entropy\n", flush=True)

# Networks
adv_nets = [LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN).to(device) for _ in range(2)]
policy_nets = [LeducPolicyNetwork(MAX_ACTIONS, POLICY_HIDDEN).to(device) for _ in range(2)]

# Buffers
adv_bufs = [ReservoirBuffer(2_000_000), ReservoirBuffer(2_000_000)]
policy_bufs = [PolicyBuffer(2_000_000), PolicyBuffer(2_000_000)]

# Also keep strategy buffer for comparison
strategy_bufs = [StrategyBuffer(), StrategyBuffer()]

t_start = time.time()

for t in range(ITERS):
    for p in range(2):
        # Traverse with both advantage and policy sample collection
        batched_traverse_with_policy(
            TRAVERSALS, p, adv_nets, adv_bufs[p], policy_bufs[p],
            t, device, MAX_ACTIONS, 1024,
        )

        # Train advantage network (aggregated + warm-start)
        adv_loss = train_advantage_aggregated(
            adv_nets[p], adv_bufs[p], device, max_iter=t+1, epochs=100, lr=0.001)

        # Store snapshot for ensemble comparison
        strategy_bufs[p].add(adv_nets[p], t)

        # Train policy network (warm-start, cross-entropy)
        policy_steps = min(2000, max(len(policy_bufs[p]) // 128, 200))
        policy_loss = train_policy_net(
            policy_nets[p], policy_bufs[p], device,
            steps=policy_steps, batch_size=512, lr=0.0005, reinit=False)

    if (t + 1) % 10 == 0:
        elapsed = time.time() - t_start

        # Exploitability via policy network (average strategy)
        a0_pol = PolicyNetAgent(policy_nets[0], torch.device('cpu'))
        a1_pol = PolicyNetAgent(policy_nets[1], torch.device('cpu'))
        exploit_policy = compute_exploitability_leduc([a0_pol, a1_pol])

        # Exploitability via ensemble (for comparison)
        sb0, sb1 = StrategyBuffer(), StrategyBuffer()
        sb0.networks = list(strategy_bufs[0].networks)
        sb1.networks = list(strategy_bufs[1].networks)
        a0_ens = SDCFRAgent(sb0, LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN), torch.device('cpu'), mode='ensemble')
        a1_ens = SDCFRAgent(sb1, LeducAdvantageNetwork(MAX_ACTIONS, HIDDEN), torch.device('cpu'), mode='ensemble')
        exploit_ensemble = compute_exploitability_leduc([a0_ens, a1_ens])

        print(
            f"  Iter {t+1:4d}: "
            f"policy={exploit_policy:8.1f} | "
            f"ensemble={exploit_ensemble:8.1f} mbb/g | "
            f"adv_loss={adv_loss:.4f} | "
            f"pol_loss={policy_loss:.4f} | "
            f"buf={len(adv_bufs[0]):,} | "
            f"elapsed={elapsed:.0f}s",
            flush=True,
        )

print("\nDone!", flush=True)
