"""Frozen legacy-policy plus trainable native-v6 residual wrapper."""
from __future__ import annotations

import torch
from torch import nn


NATIVE_FEATURES = 6 * 4 * 13 + 25 * 4 * 5 + 2 + 9


class DualContractResidualPolicy(nn.Module):
    """Preserve a legacy base exactly while learning only a native-v6 delta."""

    def __init__(
        self, base: nn.Module, hidden: int = 128, policy_delta_cap: float = 0.0
    ):
        super().__init__()
        if hidden <= 0:
            raise ValueError("hidden must be positive")
        if policy_delta_cap < 0:
            raise ValueError("policy_delta_cap must be nonnegative")
        self.policy_delta_cap = float(policy_delta_cap)
        self.base = base.eval()
        for parameter in self.base.parameters():
            parameter.requires_grad_(False)
        self.residual = nn.Sequential(
            nn.Linear(NATIVE_FEATURES, hidden),
            nn.LayerNorm(hidden),
            nn.SiLU(),
            nn.Linear(hidden, hidden // 2),
            nn.SiLU(),
        )
        self.policy_delta = nn.Linear(hidden // 2, 9)
        self.value_delta = nn.Linear(hidden // 2, 1)
        nn.init.zeros_(self.policy_delta.weight)
        nn.init.zeros_(self.policy_delta.bias)
        nn.init.zeros_(self.value_delta.weight)
        nn.init.zeros_(self.value_delta.bias)

    def train(self, mode: bool = True):
        super().train(mode)
        self.base.eval()
        return self

    def forward(
        self,
        legacy_cards: torch.Tensor,
        legacy_actions: torch.Tensor,
        legacy_extras: torch.Tensor,
        native_cards: torch.Tensor,
        native_actions: torch.Tensor,
        native_extras: torch.Tensor,
        legal_mask: torch.Tensor,
        native_legal_mask: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        with torch.no_grad():
            base_logits, base_value = self.base(
                legacy_cards, legacy_actions, legacy_extras, legal_mask
            )[:2]
        features = torch.cat(
            (
                native_cards.flatten(start_dim=1),
                native_actions.flatten(start_dim=1),
                native_extras[:, :2],
                native_legal_mask,
            ),
            dim=1,
        )
        if features.shape[1] != NATIVE_FEATURES:
            raise ValueError(
                f"native feature width must be {NATIVE_FEATURES}, got {features.shape[1]}"
            )
        hidden = self.residual(features)
        policy_delta = self.policy_delta(hidden)
        if self.policy_delta_cap > 0:
            policy_delta = self.policy_delta_cap * torch.tanh(
                policy_delta / self.policy_delta_cap
            )
        return base_logits + policy_delta, base_value + self.value_delta(hidden)

    def trainable_parameters(self):
        return (parameter for name, parameter in self.named_parameters() if not name.startswith("base."))
