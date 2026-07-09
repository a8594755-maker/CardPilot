#!/usr/bin/env python3
"""
AlphaHoldem self-play PPO trainer.

Architecture:
  - Two copies of AlphaHoldemNet play against each other
  - Current model plays both sides (self-play)
  - PPO updates on batches of completed hands
  - Periodic opponent snapshots (league training)

Usage:
  python scripts/alpha_holdem/train.py --device cuda --hands-per-batch 4096
"""

import argparse
import os
import sys
import time
import json
import random
from pathlib import Path
from collections import deque

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.distributions import Categorical

# Add parent to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.network import AlphaHoldemNet, count_parameters
from alpha_holdem.environment import HUNLEnvironment, NUM_ACTIONS


# ═══════════════════════════════════════════════════════════
# Rollout Buffer
# ═══════════════════════════════════════════════════════════

class RolloutBuffer:
    """Stores transitions from self-play for PPO training."""

    def __init__(self):
        self.card_infos = []
        self.action_infos = []
        self.extra_infos = []
        self.legal_masks = []
        self.actions = []
        self.log_probs = []
        self.rewards = []
        self.values = []
        self.dones = []

    def add(self, card_info, action_info, extra_info, legal_mask,
            action, log_prob, reward, value, done):
        self.card_infos.append(card_info)
        self.action_infos.append(action_info)
        self.extra_infos.append(extra_info)
        self.legal_masks.append(legal_mask)
        self.actions.append(action)
        self.log_probs.append(log_prob)
        self.rewards.append(reward)
        self.values.append(value)
        self.dones.append(done)

    def __len__(self):
        return len(self.actions)

    def get_tensors(self, device: str) -> dict:
        return {
            'card_infos': torch.tensor(np.array(self.card_infos), dtype=torch.float32, device=device),
            'action_infos': torch.tensor(np.array(self.action_infos), dtype=torch.float32, device=device),
            'extra_infos': torch.tensor(np.array(self.extra_infos), dtype=torch.float32, device=device),
            'legal_masks': torch.tensor(np.array(self.legal_masks), dtype=torch.float32, device=device),
            'actions': torch.tensor(np.array(self.actions), dtype=torch.long, device=device),
            'log_probs': torch.tensor(np.array(self.log_probs), dtype=torch.float32, device=device),
            'rewards': torch.tensor(np.array(self.rewards), dtype=torch.float32, device=device),
            'values': torch.tensor(np.array(self.values), dtype=torch.float32, device=device),
            'dones': torch.tensor(np.array(self.dones), dtype=torch.float32, device=device),
        }

    def clear(self):
        for attr in ['card_infos', 'action_infos', 'extra_infos', 'legal_masks',
                      'actions', 'log_probs', 'rewards', 'values', 'dones']:
            getattr(self, attr).clear()


# ═══════════════════════════════════════════════════════════
# GAE Computation
# ═══════════════════════════════════════════════════════════

def compute_gae(rewards, values, dones, gamma=1.0, lam=0.95):
    """Compute Generalized Advantage Estimation."""
    advantages = np.zeros_like(rewards)
    last_gae = 0.0
    n = len(rewards)

    for t in reversed(range(n)):
        if t == n - 1:
            next_value = 0.0
        else:
            next_value = values[t + 1]

        delta = rewards[t] + gamma * next_value * (1 - dones[t]) - values[t]
        advantages[t] = last_gae = delta + gamma * lam * (1 - dones[t]) * last_gae

    returns = advantages + values
    return advantages, returns


# ═══════════════════════════════════════════════════════════
# Self-Play Data Collection
# ═══════════════════════════════════════════════════════════

def _play_batch(args):
    """Worker: play a batch of hands, return all transitions."""
    model_state, opponent_state, hand_start, num_hands, epsilon = args

    model = AlphaHoldemNet(num_actions=NUM_ACTIONS)
    dummy_c = torch.zeros(1, 6, 4, 13)
    dummy_a = torch.zeros(1, 25, 4, 5)
    dummy_e = torch.zeros(1, 2)
    model(dummy_c, dummy_a, dummy_e)
    model.load_state_dict(model_state)
    model.eval()

    opponent = AlphaHoldemNet(num_actions=NUM_ACTIONS)
    opponent(dummy_c, dummy_a, dummy_e)
    opponent.load_state_dict(opponent_state)
    opponent.eval()

    all_transitions = []
    total_reward = 0.0
    total_steps = 0

    env = HUNLEnvironment(starting_stack=50.0)

    with torch.no_grad():
        for hand_idx in range(hand_start, hand_start + num_hands):
            obs = env.reset()
            done = False
            steps = 0
            hero_player = hand_idx % 2
            hand_reward = 0.0
            hand_buffer = []

            while not done:
                player = obs['player']
                is_hero = (player == hero_player)
                net = model if is_hero else opponent

                card_t = torch.tensor(obs['card_info'], dtype=torch.float32).unsqueeze(0)
                action_t = torch.tensor(obs['action_info'], dtype=torch.float32).unsqueeze(0)
                extra_t = torch.tensor(obs['extra_info'], dtype=torch.float32).unsqueeze(0)
                mask_t = torch.tensor(obs['legal_mask'], dtype=torch.float32).unsqueeze(0)

                logits, value = net(card_t, action_t, extra_t, mask_t)
                probs = F.softmax(logits, dim=-1)
                dist = Categorical(probs)

                if random.random() < epsilon:
                    legal_actions = np.where(obs['legal_mask'] > 0)[0]
                    action_idx = random.choice(legal_actions)
                    action_tensor = torch.tensor([action_idx])
                else:
                    action_tensor = dist.sample()
                    action_idx = action_tensor.item()

                log_prob = dist.log_prob(action_tensor).item()
                val = value.item()

                if is_hero:
                    hand_buffer.append({
                        'card_info': obs['card_info'],
                        'action_info': obs['action_info'],
                        'extra_info': obs['extra_info'],
                        'legal_mask': obs['legal_mask'],
                        'action': action_idx,
                        'log_prob': log_prob,
                        'value': val,
                    })

                obs, reward, done = env.step(action_idx)
                steps += 1

                if done and is_hero:
                    hand_reward = reward
                elif done and not is_hero:
                    hand_reward = -reward

            for i, t in enumerate(hand_buffer):
                is_last = (i == len(hand_buffer) - 1)
                all_transitions.append((
                    t['card_info'], t['action_info'], t['extra_info'], t['legal_mask'],
                    t['action'], t['log_prob'],
                    hand_reward if is_last else 0.0,
                    t['value'],
                    1.0 if is_last else 0.0,
                ))

            total_reward += hand_reward
            total_steps += steps

    return all_transitions, total_reward, total_steps, num_hands


_worker_pool = None  # Persistent pool

def _get_pool(num_workers: int):
    global _worker_pool
    if _worker_pool is None:
        from concurrent.futures import ProcessPoolExecutor
        _worker_pool = ProcessPoolExecutor(max_workers=num_workers)
    return _worker_pool


def collect_self_play_data(
    model: AlphaHoldemNet,
    opponent: AlphaHoldemNet,
    num_hands: int,
    device: str,
    epsilon: float = 0.05,
    num_workers: int = 24,
) -> tuple[RolloutBuffer, dict]:
    """Play num_hands using persistent worker pool (batched per worker)."""
    model.eval()
    opponent.eval()

    model_state = {k: v.cpu() for k, v in model.state_dict().items()}
    opponent_state = {k: v.cpu() for k, v in opponent.state_dict().items()}

    hands_per_worker = max(1, num_hands // num_workers)
    args_list = []
    offset = 0
    for i in range(num_workers):
        n = hands_per_worker if i < num_workers - 1 else (num_hands - offset)
        if n <= 0:
            break
        args_list.append((model_state, opponent_state, offset, n, epsilon))
        offset += n

    buffer = RolloutBuffer()
    total_reward = 0.0
    total_hands = 0
    hand_lengths_sum = 0

    pool = _get_pool(len(args_list))
    futures = [pool.submit(_play_batch, a) for a in args_list]
    for future in futures:
        transitions, batch_reward, batch_steps, batch_hands = future.result()
        for t in transitions:
            buffer.add(
                card_info=t[0], action_info=t[1], extra_info=t[2], legal_mask=t[3],
                action=t[4], log_prob=t[5], reward=t[6], value=t[7], done=t[8],
            )
        total_reward += batch_reward
        total_hands += batch_hands
        hand_lengths_sum += batch_steps

    stats = {
        'avg_reward': total_reward / max(total_hands, 1),
        'avg_hand_length': hand_lengths_sum / max(total_hands, 1),
        'num_transitions': len(buffer),
        'num_hands': total_hands,
    }

    return buffer, stats


# ═══════════════════════════════════════════════════════════
# PPO Update
# ═══════════════════════════════════════════════════════════

def ppo_update(
    model: AlphaHoldemNet,
    optimizer: torch.optim.Optimizer,
    buffer: RolloutBuffer,
    device: str,
    epochs: int = 4,
    mini_batch_size: int = 512,
    clip_eps: float = 0.2,
    value_coef: float = 0.5,
    entropy_coef: float = 0.1,
    max_grad_norm: float = 0.5,
    min_entropy: float = 0.3,
) -> dict:
    """Run PPO update on collected data."""
    model.train()

    data = buffer.get_tensors(device)
    rewards_np = data['rewards'].cpu().numpy()
    values_np = data['values'].cpu().numpy()
    dones_np = data['dones'].cpu().numpy()

    advantages, returns = compute_gae(rewards_np, values_np, dones_np)
    advantages = torch.tensor(advantages, dtype=torch.float32, device=device)
    returns = torch.tensor(returns, dtype=torch.float32, device=device)

    # Normalize advantages
    if len(advantages) > 1:
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)

    n = len(buffer)
    total_policy_loss = 0.0
    total_value_loss = 0.0
    total_entropy = 0.0
    num_updates = 0

    for _ in range(epochs):
        indices = torch.randperm(n, device=device)

        for start in range(0, n, mini_batch_size):
            end = min(start + mini_batch_size, n)
            idx = indices[start:end]

            # Get mini-batch
            mb_cards = data['card_infos'][idx]
            mb_actions_info = data['action_infos'][idx]
            mb_extra = data['extra_infos'][idx]
            mb_masks = data['legal_masks'][idx]
            mb_actions = data['actions'][idx]
            mb_old_log_probs = data['log_probs'][idx]
            mb_advantages = advantages[idx]
            mb_returns = returns[idx]

            # Forward pass
            logits, values = model(mb_cards, mb_actions_info, mb_extra, mb_masks)
            probs = F.softmax(logits, dim=-1)
            dist = Categorical(probs)

            new_log_probs = dist.log_prob(mb_actions)
            entropy = dist.entropy().mean()

            # PPO clipped objective
            ratio = torch.exp(new_log_probs - mb_old_log_probs)
            surr1 = ratio * mb_advantages
            surr2 = torch.clamp(ratio, 1 - clip_eps, 1 + clip_eps) * mb_advantages
            policy_loss = -torch.min(surr1, surr2).mean()

            # Value loss
            value_loss = F.mse_loss(values.squeeze(-1), mb_returns)

            # Adaptive entropy: boost coefficient if entropy too low
            ent_coef = entropy_coef
            if entropy.item() < min_entropy:
                ent_coef = entropy_coef * 5.0  # 5x penalty when entropy collapses

            # Total loss
            loss = policy_loss + value_coef * value_loss - ent_coef * entropy

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), max_grad_norm)
            optimizer.step()

            total_policy_loss += policy_loss.item()
            total_value_loss += value_loss.item()
            total_entropy += entropy.item()
            num_updates += 1

    return {
        'policy_loss': total_policy_loss / max(num_updates, 1),
        'value_loss': total_value_loss / max(num_updates, 1),
        'entropy': total_entropy / max(num_updates, 1),
        'num_updates': num_updates,
    }


# ═══════════════════════════════════════════════════════════
# League Training (Opponent Pool)
# ═══════════════════════════════════════════════════════════

class OpponentPool:
    """Maintains a pool of past model snapshots for diverse self-play."""

    def __init__(self, max_size: int = 20):
        self.max_size = max_size
        self.pool: list[dict] = []  # list of state_dicts

    def add_snapshot(self, model: AlphaHoldemNet):
        """Save current model as an opponent."""
        state = {k: v.cpu().clone() for k, v in model.state_dict().items()}
        self.pool.append(state)
        if len(self.pool) > self.max_size:
            self.pool.pop(0)

    def get_opponent(self, model: AlphaHoldemNet, device: str) -> AlphaHoldemNet:
        """
        Get an opponent model. 80% chance = latest snapshot, 20% = random from pool.
        Returns a new model instance loaded with opponent weights.
        """
        opponent = AlphaHoldemNet(num_actions=model.num_actions).to(device)
        # Force lazy init
        dummy_c = torch.zeros(1, 6, 4, 13, device=device)
        dummy_a = torch.zeros(1, 25, 4, 5, device=device)
        dummy_e = torch.zeros(1, 2, device=device)
        opponent(dummy_c, dummy_a, dummy_e)

        if len(self.pool) == 0 or random.random() < 0.2:
            # Play against self (current weights)
            opponent.load_state_dict(model.state_dict())
        else:
            # Play against a past version
            if random.random() < 0.8 and len(self.pool) > 0:
                state = self.pool[-1]  # latest
            else:
                state = random.choice(self.pool)
            opponent.load_state_dict(state)
            opponent = opponent.to(device)

        opponent.eval()
        return opponent


# ═══════════════════════════════════════════════════════════
# Main Training Loop
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description='AlphaHoldem Self-Play PPO Trainer')
    parser.add_argument('--device', default='cuda' if torch.cuda.is_available() else 'cpu')
    parser.add_argument('--hands-per-batch', type=int, default=4096)
    parser.add_argument('--iterations', type=int, default=5000)
    parser.add_argument('--lr', type=float, default=3e-4)
    parser.add_argument('--ppo-epochs', type=int, default=4)
    parser.add_argument('--mini-batch-size', type=int, default=512)
    parser.add_argument('--epsilon', type=float, default=0.15, help='Exploration rate')
    parser.add_argument('--snapshot-interval', type=int, default=50)
    parser.add_argument('--eval-interval', type=int, default=100)
    parser.add_argument('--save-interval', type=int, default=200)
    parser.add_argument('--out', default='models/alpha_holdem.pt')
    parser.add_argument('--num-workers', type=int, default=24, help='Parallel self-play workers')
    parser.add_argument('--resume', default=None, help='Path to checkpoint to resume from')
    args = parser.parse_args()

    device = args.device
    print(f'Device: {device}')
    if device == 'cuda':
        print(f'GPU: {torch.cuda.get_device_name(0)}')

    # Create model
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS).to(device)

    # Force lazy init
    dummy_card = torch.zeros(1, 6, 4, 13, device=device)
    dummy_action = torch.zeros(1, 25, 4, 5, device=device)
    dummy_extra = torch.zeros(1, 2, device=device)
    model(dummy_card, dummy_action, dummy_extra)

    print(f'Parameters: {count_parameters(model):,}')

    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    pool = OpponentPool(max_size=20)

    # Resume from checkpoint
    start_iter = 0
    if args.resume and os.path.exists(args.resume):
        ckpt = torch.load(args.resume, map_location=device, weights_only=False)
        model.load_state_dict(ckpt['model'])
        optimizer.load_state_dict(ckpt['optimizer'])
        start_iter = ckpt.get('iteration', 0)
        print(f'Resumed from {args.resume}, iteration {start_iter}')

    # Logging
    log_path = args.out.replace('.pt', '.log')
    reward_window = deque(maxlen=100)

    print(f'\nTraining: {args.iterations} iterations, {args.hands_per_batch} hands/batch')
    print(f'PPO: {args.ppo_epochs} epochs, mini-batch {args.mini_batch_size}')
    print(f'Exploration: epsilon={args.epsilon}')
    print('-' * 80)

    for iteration in range(start_iter, args.iterations):
        t0 = time.time()

        # Decay epsilon
        # Keep exploration high for first 80% of training
        progress = iteration / args.iterations
        eps = max(0.05, args.epsilon * (1 - max(0, progress - 0.8) / 0.2))

        # Get opponent
        opponent = pool.get_opponent(model, device)

        # Collect self-play data
        buffer, play_stats = collect_self_play_data(
            model, opponent, args.hands_per_batch, device,
            epsilon=eps, num_workers=args.num_workers,
        )

        # PPO update
        update_stats = ppo_update(
            model, optimizer, buffer, device,
            epochs=args.ppo_epochs,
            mini_batch_size=args.mini_batch_size,
        )

        buffer.clear()
        elapsed = time.time() - t0
        reward_window.append(play_stats['avg_reward'])

        # Log
        avg_rew_100 = np.mean(reward_window) if reward_window else 0
        log_line = (
            f"[{iteration+1:5d}] "
            f"rew={play_stats['avg_reward']:+.3f} "
            f"rew100={avg_rew_100:+.3f} "
            f"ploss={update_stats['policy_loss']:.4f} "
            f"vloss={update_stats['value_loss']:.4f} "
            f"ent={update_stats['entropy']:.4f} "
            f"eps={eps:.3f} "
            f"trans={play_stats['num_transitions']} "
            f"t={elapsed:.1f}s"
        )
        print(log_line)

        with open(log_path, 'a') as f:
            f.write(log_line + '\n')

        # Snapshot opponent
        if (iteration + 1) % args.snapshot_interval == 0:
            pool.add_snapshot(model)
            print(f'  [Snapshot] Pool size: {len(pool.pool)}')

        # Save checkpoint
        if (iteration + 1) % args.save_interval == 0:
            ckpt = {
                'model': model.state_dict(),
                'optimizer': optimizer.state_dict(),
                'iteration': iteration + 1,
                'avg_reward_100': avg_rew_100,
            }
            os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
            torch.save(ckpt, args.out)
            print(f'  [Save] {args.out}')

    # Final save
    torch.save({
        'model': model.state_dict(),
        'optimizer': optimizer.state_dict(),
        'iteration': args.iterations,
    }, args.out)
    print(f'\nTraining complete. Model saved to {args.out}')


if __name__ == '__main__':
    main()
