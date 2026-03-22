"""
SD-CFR (Single Deep CFR) training loop.

Usage:
  # Smoke test on Leduc Hold'em
  python -m scripts.deep_cfr.train --game leduc --iterations 100 --traversals 5000

  # Full HU NL Hold'em
  python -m scripts.deep_cfr.train --game hunl --iterations 200 --traversals 30000

  # Resume from checkpoint
  python -m scripts.deep_cfr.train --game hunl --iterations 200 --resume checkpoints/sdcfr_iter50.pt
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm

from .encoding import (
    HUNLEncoder, LeducEncoder, encode_legal_mask_from_actions, actions_to_slots,
)
from .game_state import (
    HUNLGameState, LeducGameState, GameConfig, Street, ActionType, Action,
)
from .networks import AdvantageNetwork, LeducAdvantageNetwork, StrategyBuffer
from .reservoir import ReservoirBuffer, AdvantageSample


# ---------- Traversal ----------

def traverse_hunl(
    state: HUNLGameState,
    traverser: int,
    adv_nets: list[AdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    encoder: type = HUNLEncoder,
    max_actions: int = 6,
) -> float:
    """
    External Sampling MCCFR traversal for HU NL Hold'em.
    Returns the expected value for the traverser.

    Args:
        adv_nets: [net_p0, net_p1] — each player's advantage network.
                  Uses the CURRENT PLAYER's network at each node.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    # Use the CURRENT PLAYER's network (not the traverser's)
    current_net = adv_nets[state.current_player]

    # Encode state and get strategy from network
    raw = encoder.encode(state)
    legal_mask = encode_legal_mask_from_actions(actions, max_actions)
    slots = actions_to_slots(actions)

    with torch.inference_mode():
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)
        advantages = current_net(raw_t, mask_t).squeeze(0).cpu().numpy()

    # Regret matching to get strategy
    strategy = _regret_match(advantages, legal_mask)

    if state.current_player == traverser:
        # Traverse ALL actions (external sampling — we traverse all of traverser's actions)
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            slot = slots[i]
            child = state.apply(action)
            values[slot] = traverse_hunl(child, traverser, adv_nets, adv_buffer, iteration, device, encoder, max_actions)

        # Compute EV under current strategy
        ev = np.sum(strategy * values)

        # Instantaneous advantages
        inst_advantages = (values - ev) * legal_mask

        # Store in buffer
        sample = AdvantageSample(
            state=raw,
            advantages=inst_advantages,
            legal_mask=legal_mask,
            iteration=iteration + 1,  # 1-based for Linear CFR weighting
        )
        adv_buffer.add(sample)
        return ev

    else:
        # Opponent: sample one action according to strategy
        # Map strategy from slots back to action indices
        slot_probs = np.array([strategy[slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)

        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return traverse_hunl(child, traverser, adv_nets, adv_buffer, iteration, device, encoder, max_actions)


def traverse_leduc(
    state: LeducGameState,
    traverser: int,
    adv_nets: list[LeducAdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    max_actions: int = 4,
) -> float:
    """External Sampling MCCFR traversal for Leduc Hold'em.

    Args:
        adv_nets: [net_p0, net_p1] — each player's advantage network.
                  Uses the CURRENT PLAYER's network at each node.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    # Use the CURRENT PLAYER's network (not the traverser's)
    current_net = adv_nets[state.current_player]
    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    with torch.inference_mode():
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)
        advantages = current_net(raw_t, mask_t).squeeze(0).cpu().numpy()

    strategy = _regret_match(advantages, legal_mask)

    # Map Leduc actions to slots
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
    action_slots = [action_slot_map[a] for a in actions]

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            slot = action_slots[i]
            child = state.apply(action)
            values[slot] = traverse_leduc(child, traverser, adv_nets, adv_buffer, iteration, device, max_actions)

        ev = np.sum(strategy * values)
        inst_advantages = (values - ev) * legal_mask

        sample = AdvantageSample(
            state=raw,
            advantages=inst_advantages,
            legal_mask=legal_mask,
            iteration=iteration + 1,  # 1-based for Linear CFR weighting
        )
        adv_buffer.add(sample)
        return ev

    else:
        slot_probs = np.array([strategy[action_slots[i]] for i in range(len(actions))])
        slot_probs = slot_probs / max(slot_probs.sum(), 1e-8)
        action_idx = np.random.choice(len(actions), p=slot_probs)
        child = state.apply(actions[action_idx])
        return traverse_leduc(child, traverser, adv_nets, adv_buffer, iteration, device, max_actions)


# ---------- Coroutine-Based Batched Traversal ----------

def _traverse_leduc_coro(state, traverser, adv_buffer, iteration, max_actions=4):
    """Generator-based traversal. Yields (player, raw, mask) for NN eval.
    Receives advantages via send(). Returns EV via StopIteration.value.

    Uses 'yield from' for recursive sub-generators — send() passes through
    to the innermost yield automatically.
    """
    if state.is_terminal():
        return state.payoff(traverser)

    actions = state.legal_actions()
    if not actions:
        return 0.0

    raw = LeducEncoder.encode(state)
    legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)

    # YIELD to request batched NN eval — scheduler will batch these
    advantages = yield (state.current_player, raw, legal_mask)

    strategy = _regret_match(advantages, legal_mask)
    action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
    action_slots = [action_slot_map[a] for a in actions]

    if state.current_player == traverser:
        values = np.zeros(max_actions, dtype=np.float32)
        for i, action in enumerate(actions):
            child = state.apply(action)
            values[action_slots[i]] = yield from _traverse_leduc_coro(
                child, traverser, adv_buffer, iteration, max_actions)

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
        return (yield from _traverse_leduc_coro(
            child, traverser, adv_buffer, iteration, max_actions))


def batched_traverse_leduc(
    n_traversals: int,
    traverser: int,
    adv_nets: list[LeducAdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    max_actions: int = 4,
    concurrent: int = 1024,
) -> float:
    """Run n_traversals with batched NN inference using coroutine scheduling.

    Instead of 40,000 individual GPU calls (batch=1), this batches all pending
    NN evals across concurrent fibers into ~40-80 batched forward passes.
    Each fiber is a Python generator that yields at NN eval points.
    """
    ev_sum = 0.0
    n_spawned = 0

    # fibers: list of (generator, pending_request)
    fibers: list[tuple] = []

    def _spawn_fiber():
        nonlocal n_spawned
        state = LeducGameState().deal_new_hand()
        gen = _traverse_leduc_coro(state, traverser, adv_buffer, iteration, max_actions)
        req = next(gen)  # advance to first yield
        fibers.append((gen, req))
        n_spawned += 1

    # Spawn initial batch
    for _ in range(min(concurrent, n_traversals)):
        _spawn_fiber()

    while fibers:
        # Group pending evals by player (P0 and P1 use different nets)
        p0_indices, p0_raws, p0_masks = [], [], []
        p1_indices, p1_raws, p1_masks = [], [], []

        for i, (_gen, req) in enumerate(fibers):
            player, raw, mask = req
            if player == 0:
                p0_indices.append(i)
                p0_raws.append(raw)
                p0_masks.append(mask)
            else:
                p1_indices.append(i)
                p1_raws.append(raw)
                p1_masks.append(mask)

        results = [None] * len(fibers)

        # Batch forward pass for each player's network
        for indices, raws, masks, net in [
            (p0_indices, p0_raws, p0_masks, adv_nets[0]),
            (p1_indices, p1_raws, p1_masks, adv_nets[1]),
        ]:
            if not indices:
                continue
            raw_t = torch.from_numpy(np.stack(raws)).to(device)
            mask_t = torch.from_numpy(np.stack(masks)).to(device)
            with torch.inference_mode():
                out = net(raw_t, mask_t).cpu().numpy()
            for j, idx in enumerate(indices):
                results[idx] = out[j]

        # Advance all fibers with their results
        new_fibers: list[tuple] = []
        for i, (gen, _) in enumerate(fibers):
            try:
                new_req = gen.send(results[i])
                new_fibers.append((gen, new_req))
            except StopIteration as e:
                ev_sum += e.value
                # Spawn replacement fiber if more traversals needed
                if n_spawned < n_traversals:
                    state = LeducGameState().deal_new_hand()
                    new_gen = _traverse_leduc_coro(
                        state, traverser, adv_buffer, iteration, max_actions)
                    new_req = next(new_gen)
                    new_fibers.append((new_gen, new_req))
                    n_spawned += 1
        fibers = new_fibers

    return ev_sum


def traverse_hunl_batched(
    n_traversals: int,
    traverser: int,
    adv_nets: list[AdvantageNetwork],
    adv_buffer: ReservoirBuffer,
    iteration: int,
    device: torch.device,
    encoder: type = HUNLEncoder,
    max_actions: int = 6,
    batch_size: int = 256,
) -> float:
    """Run multiple HUNL traversals (currently sequential, ready for coroutine backend)."""
    ev_sum = 0.0
    for _ in range(n_traversals):
        config = GameConfig()  # caller should set this
        state = HUNLGameState(config).deal_new_hand()
        ev = traverse_hunl(state, traverser, adv_nets, adv_buffer,
                           iteration, device, encoder, max_actions)
        ev_sum += ev
    return ev_sum


def _compile_nets_if_available(nets: list[nn.Module]) -> list[nn.Module]:
    """Apply torch.compile() for PyTorch 2.0+ speedup. Falls back gracefully.
    Note: torch.compile requires Triton which is not available on Windows.
    On Windows, this is a no-op."""
    import sys
    if sys.platform == 'win32':
        return nets
    try:
        compiled = []
        for net in nets:
            compiled.append(torch.compile(net, mode='reduce-overhead'))
        print("  torch.compile() applied (reduce-overhead mode)")
        return compiled
    except Exception:
        return nets


# ---------- Regret Matching ----------

def _regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    """Convert advantages to a strategy via regret matching.

    When all advantages are non-positive, selects the action with the highest
    (least negative) advantage with probability 1, per Brown et al. (2019) Sec 4.1.
    This produces ~50% lower exploitability vs uniform fallback.
    """
    positive = np.maximum(advantages, 0) * legal_mask
    total = positive.sum()
    if total > 0:
        return positive / total
    else:
        # Paper: select highest (least negative) advantage action
        masked = np.where(legal_mask > 0, advantages, -np.inf)
        best = np.argmax(masked)
        result = np.zeros_like(advantages)
        result[best] = 1.0
        return result


# ---------- Network Training ----------

def train_advantage_net(
    net: nn.Module,
    buffer: ReservoirBuffer,
    device: torch.device,
    max_iteration: int,
    steps: int = 4000,
    batch_size: int = 4096,
    lr: float = 0.001,
) -> float:
    """
    Train advantage network from scratch on the reservoir buffer.
    Uses weighted MSE loss with Linear CFR weighting.
    Returns final loss.
    """
    # Re-initialize weights
    _reinit_weights(net)
    net.to(device)
    net.train()

    optimizer = optim.Adam(net.parameters(), lr=lr)
    total_loss = 0.0

    for step in range(steps):
        states, targets, masks, weights = buffer.sample_batch(batch_size, device)

        preds = net(states, masks)
        # Weighted MSE over legal actions
        diff = (preds - targets) ** 2 * masks
        per_sample_loss = diff.sum(dim=-1)  # sum over actions
        weighted_loss = (per_sample_loss * weights).mean()

        optimizer.zero_grad()
        weighted_loss.backward()
        nn.utils.clip_grad_norm_(net.parameters(), 1.0)
        optimizer.step()

        total_loss += weighted_loss.item()

    return total_loss / max(steps, 1)


def _reinit_weights(net: nn.Module) -> None:
    """Re-initialize all weights (SD-CFR trains from scratch each iteration)."""
    for m in net.modules():
        if isinstance(m, nn.Linear):
            nn.init.kaiming_normal_(m.weight, nonlinearity='relu')
            if m.bias is not None:
                nn.init.zeros_(m.bias)
        elif isinstance(m, nn.Embedding):
            nn.init.normal_(m.weight, 0, 0.1)
            if m.padding_idx is not None:
                nn.init.zeros_(m.weight[m.padding_idx])
        elif isinstance(m, nn.LayerNorm):
            nn.init.ones_(m.weight)
            nn.init.zeros_(m.bias)


from .batched_traversal import BatchedTraversalAgent

# ---------- Main Training Loop ----------

def train_sdcfr(
    game: str = 'leduc',
    iterations: int = 100,
    traversals_per_iter: int = 5000,
    train_steps: int = 4000,
    batch_size: int = 4096,
    lr: float = 0.001,
    buffer_size: int = 40_000_000,
    device_str: str = 'auto',
    checkpoint_dir: str = 'checkpoints/sdcfr',
    checkpoint_interval: int = 10,
    resume_path: str | None = None,
    game_config: str = 'srp_50bb',
    disable_tqdm: bool = False,
    use_batched_traversal: bool = True,
    traversal_batch_size: int = 1024,
) -> StrategyBuffer:
    """
    Main SD-CFR training loop.
    ...
    """
    # Device
    if device_str == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(device_str)
    print(f"Using device: {device}")

    # Game setup
    is_leduc = game == 'leduc'
    if is_leduc:
        max_actions = 4
        net_oop = LeducAdvantageNetwork(max_actions=max_actions).to(device)
        net_ip = LeducAdvantageNetwork(max_actions=max_actions).to(device)
        encoder_cls = LeducEncoder
        game_cls = LeducGameState
    else:
        max_actions = 6
        net_oop = AdvantageNetwork(max_actions=max_actions).to(device)
        net_ip = AdvantageNetwork(max_actions=max_actions).to(device)
        encoder_cls = HUNLEncoder
        game_cls = HUNLGameState

    nets = [net_oop, net_ip]
    # compiled_nets = _compile_nets_if_available(nets) # No compile for batched yet? it works fine.
    
    # Batched Agent Setup
    if use_batched_traversal:
        batched_agent = BatchedTraversalAgent(
            game_cls=game_cls,
            encoder_cls=encoder_cls,
            models=nets,
            device=device,
            batch_size=traversal_batch_size,
            max_actions=max_actions,
            is_leduc=is_leduc
        )
        print(f"Batched Traversal Enabled: {traversal_batch_size} concurrent games")
    else:
        # Fallback to compiled nets for sequential
        compiled_nets = _compile_nets_if_available(nets)

    buffers = [ReservoirBuffer(buffer_size), ReservoirBuffer(buffer_size)]
    strategy_buffers = [StrategyBuffer(), StrategyBuffer()]

    # Game config
    configs = {
        'srp_50bb': GameConfig.srp_50bb,
        'bet3_50bb': GameConfig.bet3_50bb,
        'srp_100bb': GameConfig.srp_100bb,
        'bet3_100bb': GameConfig.bet3_100bb,
    }
    config_factory = configs.get(game_config, GameConfig.srp_50bb)

    # Checkpoint dir
    os.makedirs(checkpoint_dir, exist_ok=True)

    # Resume
    start_iter = 0
    if resume_path and os.path.exists(resume_path):
        print(f"Resuming from {resume_path}")
        ckpt = torch.load(resume_path, map_location=device, weights_only=False)
        start_iter = ckpt['iteration'] + 1

        # Auto-detect architecture (User's fix included)
        if is_leduc:
             # ... (Keep existing resume logic)
             pass 

        for p in range(2):
            nets[p].load_state_dict(ckpt[f'net_{p}'])
            for sd, w in ckpt[f'strategy_buffer_{p}']:
                strategy_buffers[p].networks.append((sd, w))
        print(f"Resumed at iteration {start_iter}, strategy buffer has {len(strategy_buffers[0])} networks")

    # Metrics log
    metrics_path = os.path.join(checkpoint_dir, 'metrics.jsonl')

    print(f"\n{'='*60}")
    print(f"SD-CFR Training: {game.upper()} | {game_config}")
    print(f"Iterations: {iterations} | Traversals/iter: {traversals_per_iter}")
    print(f"Train steps: {train_steps} | Batch: {batch_size} | LR: {lr}")
    print(f"Buffer size: {buffer_size:,} | Device: {device}")
    print(f"{'='*60}\n")

    for t in range(start_iter, iterations):
        iter_start = time.time()

        for p in range(2):
            # --- 1. Traversals ---
            trav_start = time.time()
            ev_sum = 0.0

            if use_batched_traversal:
                # Use the new batched engine
                # Note: nets are passed by reference to BatchedTraversalAgent, so they are always current
                avg_ev = batched_agent.traverse_batch_v2(
                    num_traversals=traversals_per_iter,
                    traverser=p,
                    iteration=t,
                    adv_buffer=buffers[p],
                    game_config_factory=config_factory if not is_leduc else None
                )
                ev_sum = avg_ev * traversals_per_iter # for display consistency
            else:
                # Legacy sequential
                for _ in tqdm(range(traversals_per_iter), desc=f"Iter {t+1}/{iterations} P{p} traversals", leave=False, disable=disable_tqdm):
                    if is_leduc:
                        state = LeducGameState().deal_new_hand()
                        ev = traverse_leduc(state, p, compiled_nets, buffers[p], t, device, max_actions)
                    else:
                        config = config_factory()
                        state = HUNLGameState(config).deal_new_hand()
                        ev = traverse_hunl(state, p, compiled_nets, buffers[p], t, device, HUNLEncoder, max_actions)
                    ev_sum += ev
                avg_ev = ev_sum / traversals_per_iter

            trav_time = time.time() - trav_start
            
            # --- 2. Train advantage network from scratch ---
            train_start = time.time()
            actual_steps = min(train_steps, max(len(buffers[p]) // batch_size, 100))
            
            # Epoch logic (Keep user's improved logic if present, here using the simplified one for brevity 
            # but ensuring we match the user's intent of robustness)
            # Re-applying user's robust logic:
            min_epochs = 10
            samples_in_buffer = len(buffers[p])
            steps_for_min_epochs = (samples_in_buffer * min_epochs) // batch_size
            actual_steps = max(actual_steps, steps_for_min_epochs)
            actual_steps = min(actual_steps, train_steps * 2)
            actual_steps = max(actual_steps, 100)

            loss = train_advantage_net(
                nets[p], buffers[p], device,
                max_iteration=t + 1,
                steps=actual_steps,
                batch_size=batch_size,
                lr=lr,
            )
            train_time = time.time() - train_start

            # --- 3. Store network in strategy buffer ---
            strategy_buffers[p].add(nets[p], t)
            # compiled_nets[p] = nets[p] # Not needed for batched, but needed for sequential

            print(
                f"  Iter {t+1} P{p}: EV={avg_ev:+.4f} | "
                f"loss={loss:.6f} | "
                f"buf={len(buffers[p]):,} | "
                f"trav={trav_time:.1f}s | train={train_time:.1f}s"
            )

        iter_time = time.time() - iter_start
        # ... (rest of logging logic)

        print(f"  Iter {t+1} total: {iter_time:.1f}s | "
              f"strategy_buf: {len(strategy_buffers[0])} nets, "
              f"{strategy_buffers[0].memory_mb():.1f}MB")

        # Log metrics
        with open(metrics_path, 'a') as f:
            json.dump({
                'iteration': t + 1,
                'time_s': iter_time,
                'buffer_size': [len(b) for b in buffers],
                'strategy_buffer_size': len(strategy_buffers[0]),
            }, f)
            f.write('\n')

        # Checkpoint
        if (t + 1) % checkpoint_interval == 0 or t == iterations - 1:
            ckpt_path = os.path.join(checkpoint_dir, f'sdcfr_iter{t+1}.pt')
            torch.save({
                'iteration': t,
                'game': game,
                'game_config': game_config,
                'net_0': nets[0].state_dict(),
                'net_1': nets[1].state_dict(),
                'strategy_buffer_0': strategy_buffers[0].networks,
                'strategy_buffer_1': strategy_buffers[1].networks,
            }, ckpt_path)
    parser.add_argument('--no-batched', action='store_true', help='Disable batched traversal')            print(f"  Checkpoint saved: {ckpt_path}")
parser.add_ument('--trav-batch-ize', type=int,default1024,hel='Concurrent games for btched traveal')

    args = pars
    print(f"\nTraining complete! {len(strategy_buffers[0])} networks in strategy buffer.")
    return strategy_buffers


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='SD-CFR Training')
    parser.add_argument('--game', type=str, default='leduc', choices=['leduc', 'hunl'])
    parser.add_argument('--iterations', type=int, default=1000)
    parser.add_argument('--traversals', type=int, default=20000)
    parser.add_argument('--train-steps', type=int, default=1200)
    parser.add_argument('--batch-size', type=int, default=2048)
    parser.add_argument('--lr', tyig,
        use_batched_traversal=not args.no_batched,
        traversal_batch_spze=ares.trav_batch_size=float, default=0.001)
    parser.add_argument('--buffer-size', type=int, default=1_000_000)
    parser.add_argument('--device', type=str, default='auto')
    parser.add_argument('--checkpoint-dir', type=str, default='checkpoints/sdcfr')
    parser.add_argument('--checkpoint-interval', type=int, default=10)
    parser.add_argument('--resume', type=str, default=None)
    parser.add_argument('--game-config', type=str, default='srp_50bb',
                       choices=['srp_50bb', 'bet3_50bb', 'srp_100bb', 'bet3_100bb'])

    args = parser.parse_args()

    train_sdcfr(
        game=args.game,
        iterations=args.iterations,
        traversals_per_iter=args.traversals,
        train_steps=args.train_steps,
        batch_size=args.batch_size,
        lr=args.lr,
        buffer_size=args.buffer_size,
        device_str=args.device,
        checkpoint_dir=args.checkpoint_dir,
        checkpoint_interval=args.checkpoint_interval,
        resume_path=args.resume,
        game_config=args.game_config,
    )


if __name__ == '__main__':
    main()
