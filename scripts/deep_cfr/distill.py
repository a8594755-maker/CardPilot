"""
Distillation: Train a single Policy Network from the SD-CFR StrategyBuffer.

The StrategyBuffer stores advantage networks from each CFR iteration.
The *correct* average strategy at each info set is:
    σ_avg(I, a) = Σ_t w_t * regret_match(adv_net_t(I)) / Σ_t w_t

This script:
1. Generates training data by traversing game states and computing the
   exact weighted-average strategy from all buffer networks.
2. Trains a Policy Network to directly output these probabilities.
3. The deployed Policy Network needs NO regret matching — just a forward pass.

Usage:
  python -m scripts.deep_cfr.distill --checkpoint checkpoints/sdcfr/sdcfr_iter200.pt --game leduc
  python -m scripts.deep_cfr.distill --checkpoint checkpoints/sdcfr/sdcfr_iter200.pt --game hunl
"""

from __future__ import annotations

import argparse
import json
import os
import random
import time

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from tqdm import tqdm

from .encoding import (
    HUNLEncoder, LeducEncoder, encode_legal_mask_from_actions, actions_to_slots,
)
from .game_state import (
    HUNLGameState, LeducGameState, GameConfig, Street, Action,
)
from .networks import (
    AdvantageNetwork, LeducAdvantageNetwork, StrategyBuffer,
    PolicyNetwork, LeducPolicyNetwork,
)


def _regret_match(advantages: np.ndarray, legal_mask: np.ndarray) -> np.ndarray:
    """When all advantages <= 0, select highest (least negative) action per Brown et al. (2019)."""
    positive = np.maximum(advantages, 0) * legal_mask
    total = positive.sum()
    if total > 0:
        return positive / total
    masked = np.where(legal_mask > 0, advantages, -np.inf)
    best = np.argmax(masked)
    result = np.zeros_like(advantages)
    result[best] = 1.0
    return result


# ---------- Data generation ----------

def generate_distillation_data_leduc(
    strategy_buffer: StrategyBuffer,
    net_template: LeducAdvantageNetwork,
    player: int,
    n_traversals: int,
    device: torch.device,
    max_actions: int = 4,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """
    Generate (state, target_strategy, legal_mask) tuples by traversing random Leduc games
    and computing the exact weighted-average strategy from all buffer networks.

    Returns list of (raw_features, target_probs, legal_mask).
    """
    data: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    total_weight = sum(w for _, w in strategy_buffer.networks)

    for _ in tqdm(range(n_traversals), desc=f"Generating distillation data P{player}"):
        state = LeducGameState().deal_new_hand()
        _collect_states_leduc(
            state, player, strategy_buffer, net_template,
            device, max_actions, total_weight, data,
        )
    return data


def _collect_states_leduc(
    state: LeducGameState,
    player: int,
    strategy_buffer: StrategyBuffer,
    net_template: LeducAdvantageNetwork,
    device: torch.device,
    max_actions: int,
    total_weight: float,
    data: list,
) -> None:
    """Recursively collect states where it's `player`'s turn and compute average strategy."""
    if state.is_terminal():
        return

    actions = state.legal_actions()
    if not actions:
        return

    if state.current_player == player:
        # Compute exact average strategy from all buffer networks
        raw = LeducEncoder.encode(state)
        legal_mask = LeducEncoder.encode_legal_mask(state, max_actions)
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)

        avg_strategy = np.zeros(max_actions, dtype=np.float64)
        with torch.no_grad():
            for sd, weight in strategy_buffer.networks:
                net_template.load_state_dict(sd)
                net_template.eval()
                adv = net_template(raw_t, mask_t).squeeze(0).cpu().numpy()
                strategy = _regret_match(adv, legal_mask)
                avg_strategy += strategy * weight

        avg_strategy /= total_weight
        # Normalize over legal actions
        total = avg_strategy.sum()
        if total > 0:
            avg_strategy /= total
        else:
            n_legal = legal_mask.sum()
            avg_strategy = legal_mask / max(n_legal, 1)

        data.append((raw, avg_strategy.astype(np.float32), legal_mask))

    # Continue traversal with uniform sampling (for data diversity)
    action = random.choice(actions)
    child = state.apply(action)
    _collect_states_leduc(child, player, strategy_buffer, net_template,
                          device, max_actions, total_weight, data)


def generate_distillation_data_hunl(
    strategy_buffer: StrategyBuffer,
    net_template: AdvantageNetwork,
    player: int,
    n_traversals: int,
    device: torch.device,
    config_factory,
    max_actions: int = 6,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Generate distillation data for HUNL."""
    data: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    total_weight = sum(w for _, w in strategy_buffer.networks)

    for _ in tqdm(range(n_traversals), desc=f"Generating distillation data P{player}"):
        config = config_factory()
        state = HUNLGameState(config).deal_new_hand()
        _collect_states_hunl(
            state, player, strategy_buffer, net_template,
            device, max_actions, total_weight, data, config_factory,
        )
    return data


def _collect_states_hunl(
    state: HUNLGameState,
    player: int,
    strategy_buffer: StrategyBuffer,
    net_template: AdvantageNetwork,
    device: torch.device,
    max_actions: int,
    total_weight: float,
    data: list,
    config_factory,
) -> None:
    if state.is_terminal():
        return

    actions = state.legal_actions()
    if not actions:
        return

    if state.current_player == player:
        raw = HUNLEncoder.encode(state)
        legal_mask = encode_legal_mask_from_actions(actions, max_actions)
        raw_t = torch.from_numpy(raw).unsqueeze(0).to(device)
        mask_t = torch.from_numpy(legal_mask).unsqueeze(0).to(device)

        avg_strategy = np.zeros(max_actions, dtype=np.float64)
        with torch.no_grad():
            for sd, weight in strategy_buffer.networks:
                net_template.load_state_dict(sd)
                net_template.eval()
                adv = net_template(raw_t, mask_t).squeeze(0).cpu().numpy()
                strategy = _regret_match(adv, legal_mask)
                avg_strategy += strategy * weight

        avg_strategy /= total_weight
        total = avg_strategy.sum()
        if total > 0:
            avg_strategy /= total
        else:
            n_legal = legal_mask.sum()
            avg_strategy = legal_mask / max(n_legal, 1)

        data.append((raw, avg_strategy.astype(np.float32), legal_mask))

    action = random.choice(actions)
    child = state.apply(action)
    _collect_states_hunl(child, player, strategy_buffer, net_template,
                         device, max_actions, total_weight, data, config_factory)


# ---------- Training ----------

def train_policy_network(
    policy_net: nn.Module,
    data: list[tuple[np.ndarray, np.ndarray, np.ndarray]],
    device: torch.device,
    epochs: int = 50,
    batch_size: int = 2048,
    lr: float = 0.001,
) -> float:
    """
    Train the policy network using cross-entropy loss against the target strategy.
    Returns final validation loss.
    """
    # Prepare tensors
    states = torch.from_numpy(np.stack([d[0] for d in data])).to(device)
    targets = torch.from_numpy(np.stack([d[1] for d in data])).to(device)
    masks = torch.from_numpy(np.stack([d[2] for d in data])).to(device)

    n = len(data)
    n_val = max(1, n // 10)
    n_train = n - n_val

    # Shuffle and split
    perm = torch.randperm(n)
    train_idx = perm[:n_train]
    val_idx = perm[n_train:]

    policy_net.to(device)
    policy_net.train()
    optimizer = optim.Adam(policy_net.parameters(), lr=lr)

    best_val_loss = float('inf')

    for epoch in range(epochs):
        # Train
        shuffle = torch.randperm(n_train)
        total_loss = 0.0
        n_batches = 0

        for i in range(0, n_train, batch_size):
            idx = train_idx[shuffle[i:i+batch_size]]
            s, t, m = states[idx], targets[idx], masks[idx]

            probs = policy_net(s, m)
            # Cross-entropy: -Σ target * log(pred)
            loss = -(t * torch.log(probs + 1e-8) * m).sum(dim=-1).mean()

            optimizer.zero_grad()
            loss.backward()
            nn.utils.clip_grad_norm_(policy_net.parameters(), 1.0)
            optimizer.step()

            total_loss += loss.item()
            n_batches += 1

        # Validate
        policy_net.eval()
        with torch.no_grad():
            s_val = states[val_idx]
            t_val = targets[val_idx]
            m_val = masks[val_idx]
            probs_val = policy_net(s_val, m_val)
            val_loss = -(t_val * torch.log(probs_val + 1e-8) * m_val).sum(dim=-1).mean().item()
        policy_net.train()

        if val_loss < best_val_loss:
            best_val_loss = val_loss

        if (epoch + 1) % 10 == 0 or epoch == 0:
            print(f"  Epoch {epoch+1}/{epochs}: train_loss={total_loss/max(n_batches,1):.4f} "
                  f"val_loss={val_loss:.4f}")

    return best_val_loss


# ---------- Main ----------

def distill(
    checkpoint_path: str,
    game: str = 'leduc',
    game_config: str = 'srp_50bb',
    n_traversals: int = 50000,
    epochs: int = 50,
    batch_size: int = 2048,
    lr: float = 0.001,
    device_str: str = 'auto',
    output_dir: str = 'models',
) -> None:
    if device_str == 'auto':
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    else:
        device = torch.device(device_str)
    print(f"Using device: {device}")

    ckpt = torch.load(checkpoint_path, map_location=device, weights_only=False)
    is_leduc = game == 'leduc'

    configs = {
        'srp_50bb': GameConfig.srp_50bb,
        'bet3_50bb': GameConfig.bet3_50bb,
        'srp_100bb': GameConfig.srp_100bb,
        'bet3_100bb': GameConfig.bet3_100bb,
    }
    config_factory = configs.get(game_config, GameConfig.srp_50bb)

    print(f"\n{'='*60}")
    print(f"SD-CFR Distillation: {game.upper()} | {game_config}")
    print(f"Checkpoint: {checkpoint_path}")
    print(f"Traversals: {n_traversals} | Epochs: {epochs}")
    print(f"{'='*60}\n")

    for player in range(2):
        print(f"\n--- Player {player} ---")

        # Load strategy buffer
        sb = StrategyBuffer()
        sb.networks = list(ckpt[f'strategy_buffer_{player}'])
        print(f"Strategy buffer: {len(sb)} networks")

        if is_leduc:
            max_actions = 4
            adv_net = LeducAdvantageNetwork(max_actions=max_actions).to(device)
            policy_net = LeducPolicyNetwork(max_actions=max_actions)
        else:
            max_actions = 6
            adv_net = AdvantageNetwork(max_actions=max_actions).to(device)
            policy_net = PolicyNetwork(max_actions=max_actions)

        # Generate data
        t0 = time.time()
        if is_leduc:
            data = generate_distillation_data_leduc(
                sb, adv_net, player, n_traversals, device, max_actions,
            )
        else:
            data = generate_distillation_data_hunl(
                sb, adv_net, player, n_traversals, device, config_factory, max_actions,
            )
        print(f"Generated {len(data)} training samples in {time.time()-t0:.1f}s")

        # Train
        t0 = time.time()
        val_loss = train_policy_network(
            policy_net, data, device, epochs=epochs, batch_size=batch_size, lr=lr,
        )
        print(f"Training done in {time.time()-t0:.1f}s | best_val_loss={val_loss:.4f}")

        # Save
        os.makedirs(output_dir, exist_ok=True)
        base = os.path.splitext(os.path.basename(checkpoint_path))[0]
        out_path = os.path.join(output_dir, f'{base}_policy_p{player}.pt')
        torch.save({
            'game': game,
            'game_config': game_config,
            'player': player,
            'state_dict': policy_net.state_dict(),
            'max_actions': max_actions,
            'val_loss': val_loss,
        }, out_path)
        print(f"Saved: {out_path}")

    print("\nDistillation complete!")


# ---------- CLI ----------

def main():
    parser = argparse.ArgumentParser(description='SD-CFR Distillation')
    parser.add_argument('--checkpoint', type=str, required=True)
    parser.add_argument('--game', type=str, default='leduc', choices=['leduc', 'hunl'])
    parser.add_argument('--game-config', type=str, default='srp_50bb')
    parser.add_argument('--traversals', type=int, default=50000)
    parser.add_argument('--epochs', type=int, default=50)
    parser.add_argument('--batch-size', type=int, default=2048)
    parser.add_argument('--lr', type=float, default=0.001)
    parser.add_argument('--device', type=str, default='auto')
    parser.add_argument('--output-dir', type=str, default='models')

    args = parser.parse_args()
    distill(
        checkpoint_path=args.checkpoint,
        game=args.game,
        game_config=args.game_config,
        n_traversals=args.traversals,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        device_str=args.device,
        output_dir=args.output_dir,
    )


class DistilledAgent:
    """O(1) inference agent using a distilled policy network."""

    def __init__(self, policy_net: nn.Module, device: torch.device, is_leduc: bool = True):
        self.policy_net = policy_net.to(device)
        self.policy_net.eval()
        self.device = device
        self.is_leduc = is_leduc
        self.max_actions = policy_net.max_actions

    def get_strategy(self, state) -> tuple[list, np.ndarray]:
        if self.is_leduc:
            return self._get_strategy_leduc(state)
        return self._get_strategy_hunl(state)

    def _get_strategy_leduc(self, state: LeducGameState) -> tuple[list[str], np.ndarray]:
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])
        raw = LeducEncoder.encode(state)
        mask = LeducEncoder.encode_legal_mask(state, self.max_actions)
        with torch.inference_mode():
            raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
            mask_t = torch.from_numpy(mask).unsqueeze(0).to(self.device)
            probs = self.policy_net(raw_t, mask_t).squeeze(0).cpu().numpy()
        action_slot_map = {'fold': 0, 'check': 1, 'call': 1, 'bet': 2, 'raise': 3}
        action_probs = np.array([probs[action_slot_map[a]] for a in actions], dtype=np.float64)
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)
        return actions, action_probs.astype(np.float32)

    def _get_strategy_hunl(self, state: HUNLGameState) -> tuple[list[Action], np.ndarray]:
        actions = state.legal_actions()
        if not actions:
            return [], np.array([])
        raw = HUNLEncoder.encode(state)
        mask = encode_legal_mask_from_actions(actions, self.max_actions)
        slots = actions_to_slots(actions)
        with torch.inference_mode():
            raw_t = torch.from_numpy(raw).unsqueeze(0).to(self.device)
            mask_t = torch.from_numpy(mask).unsqueeze(0).to(self.device)
            probs = self.policy_net(raw_t, mask_t).squeeze(0).cpu().numpy()
        action_probs = np.array([probs[slots[i]] for i in range(len(actions))], dtype=np.float64)
        total = action_probs.sum()
        if total > 0:
            action_probs /= total
        else:
            action_probs = np.ones(len(actions)) / len(actions)
        return actions, action_probs.astype(np.float32)

    def choose_action(self, state) -> object:
        actions, probs = self.get_strategy(state)
        if not actions:
            return None
        return actions[np.random.choice(len(actions), p=probs)]


def load_distilled(path: str, player: int = 0, device: str = 'cpu') -> DistilledAgent:
    """Load a distilled policy agent from a .pt file."""
    ckpt = torch.load(path, map_location=device, weights_only=False)
    is_leduc = ckpt['game'] == 'leduc'
    if is_leduc:
        net = LeducPolicyNetwork(max_actions=ckpt['max_actions'])
    else:
        net = PolicyNetwork(max_actions=ckpt['max_actions'])
    net.load_state_dict(ckpt['state_dict'])
    return DistilledAgent(net, torch.device(device), is_leduc=is_leduc)


if __name__ == '__main__':
    main()
