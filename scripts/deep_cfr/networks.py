"""
Neural network architecture for SD-CFR.

AdvantageNetwork: Predicts counterfactual advantages (regrets) per action.
StrategyBuffer: Stores network snapshots for SD-CFR's average strategy computation.
"""

from __future__ import annotations

import copy
from collections import OrderedDict
from typing import Optional

import numpy as np
import torch
import torch.nn as nn

from .encoding import HUNLEncoder, LeducEncoder


# ---------- Advantage Network (HUNL) ----------

class AdvantageNetwork(nn.Module):
    """
    Predicts counterfactual advantages for each action.
    Uses embedding layers for combo and board cards, plus MLP trunk with dueling heads.

    Input: raw feature vector from HUNLEncoder (56D):
      [combo_idx(1), board_cards(5), float_features(50)]
    Output: advantage values for each action slot (max_actions=6)
    """

    def __init__(self, max_actions: int = 9, combo_embed_dim: int = 64,
                 card_embed_dim: int = 16, hidden_dims: tuple[int, ...] = (256, 256)):
        super().__init__()
        self.max_actions = max_actions

        # Embeddings
        self.combo_embed = nn.Embedding(1326 + 1, combo_embed_dim, padding_idx=1326)  # +1 for padding
        self.card_embed = nn.Embedding(52 + 1, card_embed_dim, padding_idx=52)  # +1 for padding

        # Float feature dim (after combo_idx and board_cards)
        float_dim = HUNLEncoder.RAW_DIM - 6  # 50

        # Total input to trunk
        trunk_input = combo_embed_dim + card_embed_dim + float_dim  # 64 + 16 + 50 = 130

        # Trunk MLP
        layers = []
        in_dim = trunk_input
        for h_dim in hidden_dims:
            layers.append(nn.Linear(in_dim, h_dim))
            layers.append(nn.ReLU())
            in_dim = h_dim
        layers.append(nn.LayerNorm(in_dim))
        self.trunk = nn.Sequential(*layers)
        self._trunk_dim = in_dim

        # Dueling heads
        self.adv_head = nn.Sequential(
            nn.Linear(in_dim, 128),
            nn.ReLU(),
            nn.Linear(128, max_actions),
        )
        self.val_head = nn.Sequential(
            nn.Linear(in_dim, 128),
            nn.ReLU(),
            nn.Linear(128, 1),
        )

        # Sizing regression head: outputs [0, 1] representing pot fraction
        self.sizing_head = nn.Sequential(
            nn.Linear(in_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 1),
            nn.Sigmoid(),
        )

    def forward(self, raw_features: torch.Tensor, legal_mask: torch.Tensor,
                return_sizing: bool = False) -> torch.Tensor | tuple[torch.Tensor, torch.Tensor]:
        """
        Args:
            raw_features: (batch, 56) — raw encoded state
            legal_mask: (batch, max_actions) — 1.0 for legal actions
            return_sizing: if True, also return sizing prediction
        Returns:
            advantages: (batch, max_actions) — masked advantages
            OR (advantages, sizing): sizing is (batch, 1) in [0, 1]
        """
        # Extract indices
        combo_idx = raw_features[:, 0].long().clamp(0, 1326)  # -1 → 1326 (padding)
        board_cards = raw_features[:, 1:6].long().clamp(-1, 52)
        board_cards = board_cards.where(board_cards >= 0, torch.tensor(52, device=board_cards.device))
        float_feats = raw_features[:, 6:]

        # Embeddings
        combo_emb = self.combo_embed(combo_idx)  # (batch, 64)
        board_emb = self.card_embed(board_cards)  # (batch, 5, 16)
        board_emb = board_emb.sum(dim=1)  # (batch, 16) — sum pooling

        # Concatenate
        x = torch.cat([combo_emb, board_emb, float_feats], dim=-1)  # (batch, 130)

        # Trunk
        h = self.trunk(x)

        # Advantage prediction — no mean-centering (CFR advantages are NOT zero-mean;
        # they satisfy Σ σ(a)*adv(a)=0, not Σ adv(a)/|A|=0)
        adv = self.adv_head(h)  # (batch, max_actions)
        val = self.val_head(h)  # (batch, 1)

        # Q = V + A, masked to legal actions only
        q = (val + adv) * legal_mask

        if return_sizing:
            sizing = self.sizing_head(h)  # (batch, 1)
            return q, sizing
        return q


# ---------- Advantage Network (Leduc — for smoke testing) ----------

class LeducAdvantageNetwork(nn.Module):
    """Simple MLP for Leduc Hold'em (no embeddings needed)."""

    def __init__(self, max_actions: int = 4, hidden_dims: tuple[int, ...] = (64, 64, 64)):
        super().__init__()
        self.max_actions = max_actions

        layers = []
        in_dim = LeducEncoder.RAW_DIM  # 25
        for h_dim in hidden_dims:
            layers.append(nn.Linear(in_dim, h_dim))
            layers.append(nn.ReLU())
            in_dim = h_dim

        self.trunk = nn.Sequential(*layers)
        self.head = nn.Linear(in_dim, max_actions)

    def forward(self, raw_features: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
        h = self.trunk(raw_features)
        # No mean-centering: CFR advantages satisfy Σ σ(a)*adv(a)=0 (strategy-weighted),
        # NOT Σ adv(a)/|A|=0 (arithmetic mean). Mean-centering distorts regret matching.
        return self.head(h) * legal_mask


# ---------- Strategy Buffer (SD-CFR) ----------

class StrategyBuffer:
    """
    Stores network snapshots from each CFR iteration.
    At inference time, sample a network proportional to its iteration weight (Linear CFR).
    """

    def __init__(self):
        self.networks: list[tuple[OrderedDict, int]] = []  # (state_dict, weight)

    def add(self, network: nn.Module, iteration: int) -> None:
        """Save a copy of the network's state dict with Linear CFR weight."""
        state_dict = OrderedDict(
            (k, v.cpu().clone()) for k, v in network.state_dict().items()
        )
        self.networks.append((state_dict, iteration + 1))

    def sample_strategy(self) -> OrderedDict:
        """Sample a network state_dict proportional to iteration weight."""
        weights = np.array([w for _, w in self.networks], dtype=np.float64)
        probs = weights / weights.sum()
        idx = np.random.choice(len(self.networks), p=probs)
        return self.networks[idx][0]

    def average_strategy(self, network_template: nn.Module) -> OrderedDict:
        """
        Compute the weighted average of all stored networks.
        This is a deterministic alternative to sampling.
        """
        total_weight = sum(w for _, w in self.networks)
        avg_dict = OrderedDict()

        for key in self.networks[0][0]:
            avg_dict[key] = sum(
                sd[key].cpu().float() * (w / total_weight)
                for sd, w in self.networks
            )

        return avg_dict

    def __len__(self) -> int:
        return len(self.networks)

    def memory_mb(self) -> float:
        """Estimate memory usage in MB."""
        if not self.networks:
            return 0.0
        # Rough estimate from first network
        sd = self.networks[0][0]
        params_bytes = sum(v.nelement() * v.element_size() for v in sd.values())
        return (params_bytes * len(self.networks)) / (1024 * 1024)


# ---------- Policy Network (Distillation target) ----------

class LeducPolicyNetwork(nn.Module):
    """
    Distilled policy network for Leduc Hold'em.
    Directly outputs action probabilities (no regret matching needed at inference).
    """

    def __init__(self, max_actions: int = 4, hidden_dims: tuple[int, ...] = (128, 128)):
        super().__init__()
        self.max_actions = max_actions
        layers = []
        in_dim = LeducEncoder.RAW_DIM  # 25
        for h_dim in hidden_dims:
            layers.append(nn.Linear(in_dim, h_dim))
            layers.append(nn.ReLU())
            in_dim = h_dim
        self.trunk = nn.Sequential(*layers)
        self.head = nn.Linear(in_dim, max_actions)

    def forward(self, raw_features: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
        """Returns action probabilities (softmax over legal actions)."""
        h = self.trunk(raw_features)
        logits = self.head(h)
        # Mask illegal actions with large negative value
        logits = logits + (1.0 - legal_mask) * (-1e9)
        return torch.softmax(logits, dim=-1) * legal_mask


class PolicyNetwork(nn.Module):
    """
    Distilled policy network for HU NL Hold'em.
    Same embedding architecture as AdvantageNetwork but outputs action probs directly.
    """

    def __init__(self, max_actions: int = 9, combo_embed_dim: int = 64,
                 card_embed_dim: int = 16, hidden_dims: tuple[int, ...] = (256, 256)):
        super().__init__()
        self.max_actions = max_actions
        self.combo_embed = nn.Embedding(1326 + 1, combo_embed_dim, padding_idx=1326)
        self.card_embed = nn.Embedding(52 + 1, card_embed_dim, padding_idx=52)
        float_dim = HUNLEncoder.RAW_DIM - 6
        trunk_input = combo_embed_dim + card_embed_dim + float_dim

        layers = []
        in_dim = trunk_input
        for h_dim in hidden_dims:
            layers.append(nn.Linear(in_dim, h_dim))
            layers.append(nn.ReLU())
            in_dim = h_dim
        layers.append(nn.LayerNorm(in_dim))
        self.trunk = nn.Sequential(*layers)
        self.head = nn.Linear(in_dim, max_actions)

    def forward(self, raw_features: torch.Tensor, legal_mask: torch.Tensor) -> torch.Tensor:
        combo_idx = raw_features[:, 0].long().clamp(0, 1326)
        board_cards = raw_features[:, 1:6].long().clamp(-1, 52)
        board_cards = board_cards.where(board_cards >= 0, torch.tensor(52, device=board_cards.device))
        float_feats = raw_features[:, 6:]

        combo_emb = self.combo_embed(combo_idx)
        board_emb = self.card_embed(board_cards).sum(dim=1)
        x = torch.cat([combo_emb, board_emb, float_feats], dim=-1)

        h = self.trunk(x)
        logits = self.head(h)
        logits = logits + (1.0 - legal_mask) * (-1e9)
        return torch.softmax(logits, dim=-1) * legal_mask
