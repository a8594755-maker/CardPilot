#!/usr/bin/env python3
"""
AlphaHoldem fast trainer — batched GPU inference + parallel game workers.

Architecture:
  - Main thread: GPU inference server (batches observations → actions)
  - Worker threads: pure game logic (no torch), communicate via queues
  - ~60x faster than per-hand torch inference

Target: 4000+ hands/sec → 1B hands in ~3 days.

Usage:
  python scripts/alpha_holdem/train_fast.py --device cuda --workers 28
"""

import argparse
import os
import sys
import time
import random
import threading
from queue import Queue, Empty
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment import (
    HUNLEnvironment, NUM_ACTIONS,
    encode_cards, encode_action_history, encode_extra, get_legal_mask,
    action_index_to_game_action,
)
from deep_cfr.game_state import GameConfig


# ═══════════════════════════════════════════════════════════
# Shared State
# ═══════════════════════════════════════════════════════════

class InferenceRequest:
    __slots__ = ('card_info', 'action_info', 'extra_info', 'legal_mask', 'result_event', 'action_idx', 'log_prob', 'value')
    def __init__(self, card_info, action_info, extra_info, legal_mask):
        self.card_info = card_info
        self.action_info = action_info
        self.extra_info = extra_info
        self.legal_mask = legal_mask
        self.result_event = threading.Event()
        self.action_idx = 0
        self.log_prob = 0.0
        self.value = 0.0


class Transition:
    __slots__ = ('card_info', 'action_info', 'extra_info', 'legal_mask', 'action', 'log_prob', 'reward', 'value', 'done')
    def __init__(self, card_info, action_info, extra_info, legal_mask, action, log_prob, reward, value, done):
        self.card_info = card_info
        self.action_info = action_info
        self.extra_info = extra_info
        self.legal_mask = legal_mask
        self.action = action
        self.log_prob = log_prob
        self.reward = reward
        self.value = value
        self.done = done


# ═══════════════════════════════════════════════════════════
# Game Worker (pure game logic, no torch)
# ═══════════════════════════════════════════════════════════

def game_worker(
    worker_id: int,
    inference_queue: Queue,
    transition_queue: Queue,
    stop_event: threading.Event,
    epsilon: float,
    hands_target: int,
):
    """
    Play hands continuously. For each action needed:
    1. Encode observation
    2. Submit InferenceRequest to queue
    3. Wait for GPU inference result
    4. Apply action
    """
    env = HUNLEnvironment(starting_stack=50.0)
    hands_played = 0

    while not stop_event.is_set() and hands_played < hands_target:
        obs = env.reset()
        done = False
        hero_player = hands_played % 2
        hand_buffer = []
        hand_reward = 0.0

        while not done and not stop_event.is_set():
            player = obs['player']
            is_hero = (player == hero_player)

            # Submit inference request
            req = InferenceRequest(
                obs['card_info'], obs['action_info'],
                obs['extra_info'], obs['legal_mask'],
            )
            inference_queue.put(req)
            req.result_event.wait()  # block until GPU responds

            # Epsilon-greedy
            if random.random() < epsilon:
                legal = np.where(obs['legal_mask'] > 0)[0]
                action_idx = random.choice(legal)
                # Recompute log_prob for the random action (approximate)
                log_prob = req.log_prob  # use model's log_prob as estimate
            else:
                action_idx = req.action_idx
                log_prob = req.log_prob

            if is_hero:
                hand_buffer.append((
                    obs['card_info'], obs['action_info'], obs['extra_info'],
                    obs['legal_mask'], action_idx, log_prob, req.value,
                ))

            obs, reward, done = env.step(action_idx)

            if done:
                hand_reward = reward if is_hero else -reward

        # Submit transitions
        for i, (ci, ai, ei, lm, act, lp, val) in enumerate(hand_buffer):
            is_last = (i == len(hand_buffer) - 1)
            transition_queue.put(Transition(
                ci, ai, ei, lm, act, lp,
                hand_reward if is_last else 0.0,
                val,
                1.0 if is_last else 0.0,
            ))

        hands_played += 1


# ═══════════════════════════════════════════════════════════
# GPU Inference Server
# ═══════════════════════════════════════════════════════════

@torch.no_grad()
def inference_server(
    model: AlphaHoldemNet,
    inference_queue: Queue,
    stop_event: threading.Event,
    device: str,
    max_batch: int = 256,
    timeout: float = 0.005,  # 5ms — collect requests then batch
):
    """
    Continuously batch inference requests from workers.
    Collects up to max_batch requests within timeout, runs one GPU forward pass.
    """
    model.eval()

    while not stop_event.is_set():
        batch = []

        # Collect requests (wait up to timeout for a batch)
        try:
            req = inference_queue.get(timeout=0.1)
            batch.append(req)
        except Empty:
            continue

        # Drain queue for more requests (up to max_batch)
        deadline = time.monotonic() + timeout
        while len(batch) < max_batch and time.monotonic() < deadline:
            try:
                req = inference_queue.get_nowait()
                batch.append(req)
            except Empty:
                break

        if not batch:
            continue

        B = len(batch)

        # Stack into tensors
        cards = torch.tensor(np.array([r.card_info for r in batch]), dtype=torch.float32, device=device)
        actions = torch.tensor(np.array([r.action_info for r in batch]), dtype=torch.float32, device=device)
        extras = torch.tensor(np.array([r.extra_info for r in batch]), dtype=torch.float32, device=device)
        masks = torch.tensor(np.array([r.legal_mask for r in batch]), dtype=torch.float32, device=device)

        # Batch forward pass
        logits, values = model(cards, actions, extras, masks)
        probs = F.softmax(logits, dim=-1)
        dist = Categorical(probs)
        sampled = dist.sample()
        log_probs = dist.log_prob(sampled)

        # Distribute results
        sampled_np = sampled.cpu().numpy()
        log_probs_np = log_probs.cpu().numpy()
        values_np = values.squeeze(-1).cpu().numpy()

        for i, req in enumerate(batch):
            req.action_idx = int(sampled_np[i])
            req.log_prob = float(log_probs_np[i])
            req.value = float(values_np[i])
            req.result_event.set()


# ═══════════════════════════════════════════════════════════
# GAE + PPO (same as train.py)
# ═══════════════════════════════════════════════════════════

def compute_gae(rewards, values, dones, gamma=1.0, lam=0.95):
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)
    for t in reversed(range(n)):
        next_value = 0.0 if t == n - 1 else values[t + 1]
        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae
    returns = advantages + values
    return advantages, returns


def ppo_update(
    model: AlphaHoldemNet,
    optimizer: torch.optim.Optimizer,
    transitions: list[Transition],
    device: str,
    epochs: int = 4,
    mini_batch_size: int = 1024,
    clip_eps: float = 0.2,
    value_coef: float = 0.5,
    entropy_coef: float = 0.1,
    max_grad_norm: float = 0.5,
    min_entropy: float = 0.3,
) -> dict:
    model.train()
    n = len(transitions)

    # Build arrays
    card_arr = np.array([t.card_info for t in transitions])
    action_arr = np.array([t.action_info for t in transitions])
    extra_arr = np.array([t.extra_info for t in transitions])
    mask_arr = np.array([t.legal_mask for t in transitions])
    act_arr = np.array([t.action for t in transitions])
    lp_arr = np.array([t.log_prob for t in transitions])
    rew_arr = np.array([t.reward for t in transitions])
    val_arr = np.array([t.value for t in transitions])
    done_arr = np.array([t.done for t in transitions])

    advantages, returns = compute_gae(rew_arr, val_arr, done_arr)

    # To tensors
    cards_t = torch.tensor(card_arr, dtype=torch.float32, device=device)
    actions_info_t = torch.tensor(action_arr, dtype=torch.float32, device=device)
    extras_t = torch.tensor(extra_arr, dtype=torch.float32, device=device)
    masks_t = torch.tensor(mask_arr, dtype=torch.float32, device=device)
    acts_t = torch.tensor(act_arr, dtype=torch.long, device=device)
    old_lp_t = torch.tensor(lp_arr, dtype=torch.float32, device=device)
    adv_t = torch.tensor(advantages, dtype=torch.float32, device=device)
    ret_t = torch.tensor(returns, dtype=torch.float32, device=device)

    if n > 1:
        adv_t = (adv_t - adv_t.mean()) / (adv_t.std() + 1e-8)

    total_ploss = 0.0
    total_vloss = 0.0
    total_ent = 0.0
    num_updates = 0

    for _ in range(epochs):
        indices = torch.randperm(n, device=device)
        for start in range(0, n, mini_batch_size):
            end = min(start + mini_batch_size, n)
            idx = indices[start:end]

            logits, values = model(cards_t[idx], actions_info_t[idx], extras_t[idx], masks_t[idx])
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)
            new_lp = dist.log_prob(acts_t[idx])
            entropy = dist.entropy().mean()

            ratio = torch.exp(new_lp - old_lp_t[idx])
            surr1 = ratio * adv_t[idx]
            surr2 = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * adv_t[idx]
            ploss = -torch.min(surr1, surr2).mean()
            vloss = F.mse_loss(values.squeeze(-1), ret_t[idx])

            ent_coef = entropy_coef * 5.0 if entropy.item() < min_entropy else entropy_coef
            loss = ploss + value_coef * vloss - ent_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            total_ploss += ploss.item()
            total_vloss += vloss.item()
            total_ent += entropy.item()
            num_updates += 1

    return {
        'policy_loss': total_ploss / max(num_updates, 1),
        'value_loss': total_vloss / max(num_updates, 1),
        'entropy': total_ent / max(num_updates, 1),
    }


# ═══════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='AlphaHoldem Fast Trainer')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--workers', type=int, default=28)
    parser.add_argument('--hands-per-iter', type=int, default=16384)
    parser.add_argument('--total-hands', type=int, default=1_000_000_000)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=1024)
    parser.add_argument('--epsilon', type=float, default=0.15)
    parser.add_argument('--save-interval', type=int, default=100)
    parser.add_argument('--out', default='models/alpha_holdem_v2.pt')
    parser.add_argument('--resume', default=None)
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)
    # Force lazy init
    dummy_c = torch.zeros(1, 6, 4, 13, device=device)
    dummy_a = torch.zeros(1, 25, 4, 5, device=device)
    dummy_e = torch.zeros(1, 2, device=device)
    model(dummy_c, dummy_a, dummy_e)
    print(f'Parameters: {count_parameters(model):,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)

    start_hands = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        start_hands = ckpt.get('total_hands', 0)
        print(f'Resumed from {args.resume}, {start_hands:,} hands played')

    log_path = args.out.replace('.pt', '.log')
    total_hands = start_hands
    iteration = 0
    reward_window = deque(maxlen=100)

    num_iters = (args.total_hands - start_hands) // args.hands_per_iter
    print(f'\nTarget: {args.total_hands:,} hands ({num_iters:,} iterations of {args.hands_per_iter:,})')
    print(f'Workers: {args.workers}, PPO epochs: {args.ppo_epochs}')
    print('-' * 80)

    while total_hands < args.total_hands:
        t0 = time.time()
        iteration += 1

        # Decay epsilon after 80%
        progress = total_hands / args.total_hands
        eps = max(0.05, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))

        # ── Collect data via batched inference ──
        inference_queue = Queue()
        transition_queue = Queue()
        stop_event = threading.Event()

        hands_per_worker = args.hands_per_iter // args.workers + 1

        # Start inference server
        server_thread = threading.Thread(
            target=inference_server,
            args=(model, inference_queue, stop_event, device, 256, 0.005),
            daemon=True,
        )
        server_thread.start()

        # Start game workers
        worker_threads = []
        for w in range(args.workers):
            t = threading.Thread(
                target=game_worker,
                args=(w, inference_queue, transition_queue, stop_event, eps, hands_per_worker),
                daemon=True,
            )
            t.start()
            worker_threads.append(t)

        # Wait for workers to finish
        for t in worker_threads:
            t.join()

        # Stop inference server
        stop_event.set()
        server_thread.join(timeout=5)

        # Collect transitions
        transitions = []
        batch_reward = 0.0
        batch_hands = 0
        while not transition_queue.empty():
            t = transition_queue.get_nowait()
            transitions.append(t)
            if t.done > 0.5:
                batch_reward += t.reward
                batch_hands += 1

        if not transitions:
            print(f'[{iteration}] WARNING: no transitions collected')
            continue

        avg_reward = batch_reward / max(batch_hands, 1)
        reward_window.append(avg_reward)

        # ── PPO update ──
        update_stats = ppo_update(
            model, optimizer, transitions, device,
            epochs=args.ppo_epochs,
            mini_batch_size=args.mini_batch_size,
        )

        total_hands += batch_hands
        elapsed = time.time() - t0
        hands_per_sec = batch_hands / elapsed if elapsed > 0 else 0
        rew100 = np.mean(reward_window) if reward_window else 0

        log_line = (
            f"[{iteration:5d}] "
            f"hands={total_hands:,} "
            f"rew={avg_reward:+.3f} "
            f"rew100={rew100:+.3f} "
            f"ploss={update_stats['policy_loss']:.4f} "
            f"vloss={update_stats['value_loss']:.4f} "
            f"ent={update_stats['entropy']:.4f} "
            f"eps={eps:.3f} "
            f"trans={len(transitions)} "
            f"h/s={hands_per_sec:.0f} "
            f"t={elapsed:.1f}s"
        )
        print(log_line)
        with open(log_path, 'a') as f:
            f.write(log_line + '\n')

        # Save
        if iteration % args.save_interval == 0:
            torch.save({
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'total_hands': total_hands,
                'iteration': iteration,
            }, args.out)
            print(f'  [Save] {args.out} ({total_hands:,} hands)')

    # Final save
    torch.save({
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'total_hands': total_hands,
        'iteration': iteration,
    }, args.out)
    print(f'\nDone! {total_hands:,} hands. Model: {args.out}')


if __name__ == '__main__':
    main()
