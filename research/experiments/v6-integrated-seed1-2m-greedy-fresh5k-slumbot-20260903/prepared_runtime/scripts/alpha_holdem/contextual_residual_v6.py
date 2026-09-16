"""Standard10-preserving native-v6 residual with public cross-hand context."""
from __future__ import annotations

import torch
from torch import nn

from .dual_contract_residual_v6 import NATIVE_FEATURES


CONTEXT_FEATURES = 20


class ContextualResidualPolicy(nn.Module):
    """Learn a state-by-context interaction while remaining exact at zero context."""

    def __init__(self, base: nn.Module, hidden: int = 128, policy_delta_cap: float = 0.25):
        super().__init__()
        if hidden <= 0 or hidden % 2:
            raise ValueError("hidden must be a positive even integer")
        if policy_delta_cap < 0:
            raise ValueError("policy_delta_cap must be nonnegative")
        self.policy_delta_cap = float(policy_delta_cap)
        self.base = base.eval()
        for parameter in self.base.parameters():
            parameter.requires_grad_(False)
        interaction = hidden // 2
        self.state_encoder = nn.Sequential(
            nn.Linear(NATIVE_FEATURES, hidden),
            nn.LayerNorm(hidden),
            nn.SiLU(),
            nn.Linear(hidden, interaction),
            nn.SiLU(),
        )
        self.context_encoder = nn.Sequential(
            nn.Linear(CONTEXT_FEATURES, interaction, bias=False),
            nn.Tanh(),
        )
        self.policy_delta = nn.Linear(interaction, 9)
        self.value_delta = nn.Linear(interaction, 1)
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
        context: torch.Tensor,
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
            raise ValueError(f"native feature width must be {NATIVE_FEATURES}, got {features.shape[1]}")
        if context.ndim != 2 or context.shape[1] != CONTEXT_FEATURES:
            raise ValueError(f"context must have shape [batch,{CONTEXT_FEATURES}]")
        interaction = self.state_encoder(features) * self.context_encoder(context)
        policy_delta = self.policy_delta(interaction)
        value_delta = self.value_delta(interaction)
        # This gate gives an architectural, testable cold-start contract after training.
        present = (context.abs().sum(dim=1, keepdim=True) > 0).to(policy_delta.dtype)
        policy_delta = policy_delta * present
        value_delta = value_delta * present
        if self.policy_delta_cap > 0:
            policy_delta = self.policy_delta_cap * torch.tanh(policy_delta / self.policy_delta_cap)
        return base_logits + policy_delta, base_value + value_delta

    def trainable_parameters(self):
        return (parameter for name, parameter in self.named_parameters() if not name.startswith("base."))


class PosteriorCenteredResidualPolicy(nn.Module):
    """A zero-mean mixture of learned style heads under a frozen classifier."""

    def __init__(
        self,
        base: nn.Module,
        classifier: dict,
        hidden: int = 128,
        policy_delta_cap: float = 0.25,
        reliability_power: float = 0.0,
    ):
        super().__init__()
        if hidden <= 0 or hidden % 2:
            raise ValueError("hidden must be a positive even integer")
        weight = torch.as_tensor(classifier["weight"], dtype=torch.float32)
        bias = torch.as_tensor(classifier["bias"], dtype=torch.float32)
        mean = torch.as_tensor(classifier["mean"], dtype=torch.float32)
        std = torch.as_tensor(classifier["std"], dtype=torch.float32)
        if weight.ndim != 2 or weight.shape[1] != CONTEXT_FEATURES or bias.shape != (weight.shape[0],):
            raise ValueError("invalid frozen context classifier")
        if mean.shape != (CONTEXT_FEATURES,) or std.shape != (CONTEXT_FEATURES,) or torch.any(std <= 0):
            raise ValueError("invalid frozen classifier normalization")
        temperature = float(classifier["temperature"])
        if temperature <= 0:
            raise ValueError("classifier temperature must be positive")
        if reliability_power < 0:
            raise ValueError("reliability_power must be nonnegative")
        self.classes = int(weight.shape[0])
        self.policy_delta_cap = float(policy_delta_cap)
        self.reliability_power = float(reliability_power)
        self.base = base.eval()
        for parameter in self.base.parameters():
            parameter.requires_grad_(False)
        self.register_buffer("classifier_weight", weight)
        self.register_buffer("classifier_bias", bias)
        self.register_buffer("classifier_mean", mean)
        self.register_buffer("classifier_std", std)
        self.register_buffer("classifier_temperature", torch.tensor(temperature, dtype=torch.float32))
        interaction = hidden // 2
        self.state_encoder = nn.Sequential(
            nn.Linear(NATIVE_FEATURES, hidden), nn.LayerNorm(hidden), nn.SiLU(),
            nn.Linear(hidden, interaction), nn.SiLU(),
        )
        self.policy_heads = nn.Linear(interaction, self.classes * 9)
        self.value_heads = nn.Linear(interaction, self.classes)
        nn.init.zeros_(self.policy_heads.weight)
        nn.init.zeros_(self.policy_heads.bias)
        nn.init.zeros_(self.value_heads.weight)
        nn.init.zeros_(self.value_heads.bias)

    def train(self, mode: bool = True):
        super().train(mode)
        self.base.eval()
        return self

    def context_posterior(self, context: torch.Tensor) -> torch.Tensor:
        normalized = (context - self.classifier_mean) / self.classifier_std
        logits = normalized @ self.classifier_weight.T + self.classifier_bias
        return torch.softmax(logits / self.classifier_temperature, dim=1)

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
        context: torch.Tensor,
    ) -> tuple[torch.Tensor, torch.Tensor]:
        with torch.no_grad():
            base_logits, base_value = self.base(legacy_cards, legacy_actions, legacy_extras, legal_mask)[:2]
        features = torch.cat(
            (native_cards.flatten(start_dim=1), native_actions.flatten(start_dim=1), native_extras[:, :2], native_legal_mask),
            dim=1,
        )
        if features.shape[1] != NATIVE_FEATURES or context.ndim != 2 or context.shape[1] != CONTEXT_FEATURES:
            raise ValueError("invalid state or context feature width")
        hidden = self.state_encoder(features)
        centered_posterior = self.context_posterior(context) - (1.0 / self.classes)
        if self.reliability_power > 0:
            posterior = centered_posterior + (1.0 / self.classes)
            entropy = -(posterior * posterior.clamp_min(1e-15).log()).sum(dim=1, keepdim=True)
            reliability = (1.0 - entropy / torch.log(torch.as_tensor(float(self.classes), device=context.device))).clamp(0.0, 1.0)
            centered_posterior = centered_posterior * reliability.pow(self.reliability_power)
        policy_heads = self.policy_heads(hidden).view(-1, self.classes, 9)
        value_heads = self.value_heads(hidden)
        policy_delta = torch.einsum("bc,bca->ba", centered_posterior, policy_heads)
        value_delta = (centered_posterior * value_heads).sum(dim=1, keepdim=True)
        present = (context.abs().sum(dim=1, keepdim=True) > 0).to(policy_delta.dtype)
        policy_delta = policy_delta * present
        value_delta = value_delta * present
        if self.policy_delta_cap > 0:
            policy_delta = self.policy_delta_cap * torch.tanh(policy_delta / self.policy_delta_cap)
        return base_logits + policy_delta, base_value + value_delta

    def trainable_parameters(self):
        return (parameter for name, parameter in self.named_parameters() if not name.startswith("base."))
