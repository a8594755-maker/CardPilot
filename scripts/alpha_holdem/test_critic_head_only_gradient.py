from __future__ import annotations

import copy

import numpy as np
import torch
from torch import nn

from scripts.alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


class TinyPolicy(nn.Module):
    def __init__(self) -> None:
        super().__init__()
        self.trunk = nn.Linear(2, 8)
        self.policy_head = nn.Linear(8, 9)
        self.value_head = nn.Linear(8, 1)

    def forward(self, cards, actions, extras, masks):
        hidden = torch.tanh(self.trunk(extras))
        logits = self.policy_head(hidden).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(hidden)


def constant_advantage_transitions(model: TinyPolicy, count: int = 8) -> list[tuple]:
    card = np.zeros((6, 4, 13), np.float32)
    action = np.zeros((25, 4, 5), np.float32)
    extra = np.array([1.0, 0.5], np.float32)
    mask = np.ones(9, np.float32)
    with torch.no_grad():
        logits, value = model(
            torch.tensor(card).unsqueeze(0),
            torch.tensor(action).unsqueeze(0),
            torch.tensor(extra).unsqueeze(0),
            torch.tensor(mask).unsqueeze(0),
        )
        old_lp = torch.log_softmax(logits, dim=-1)[0, 1].item()
        old_value = float(value.item())
    return [
        (
            card.copy(),
            action.copy(),
            extra.copy(),
            mask.copy(),
            1,
            old_lp,
            10.0,
            old_value,
            1.0,
            200.0,
            200.0,
            1.0,
        )
        for _ in range(count)
    ]


def changed(before: dict[str, torch.Tensor], after: dict[str, torch.Tensor], prefix: str) -> bool:
    return any(
        not torch.equal(before[name], tensor)
        for name, tensor in after.items()
        if name.startswith(prefix)
    )


def run_update(
    initial: TinyPolicy,
    *,
    isolate_critic: bool,
    value_coef: float,
) -> TinyPolicy:
    model = copy.deepcopy(initial)
    optimizer = torch.optim.SGD(model.parameters(), lr=0.01)
    torch.manual_seed(2026072604)
    trinal_clip_ppo_update(
        model,
        optimizer,
        constant_advantage_transitions(model),
        "cpu",
        epochs=1,
        mini_batch_size=8,
        value_coef=value_coef,
        entropy_coef=0.0,
        entropy_floor=0.0,
        action_prior_coef=0.0,
        preflop_action_prior_coef=0.0,
        critic_head_only_gradient=isolate_critic,
    )
    return model


def test_critic_head_only_gradient_blocks_shared_trunk_updates() -> None:
    torch.manual_seed(2026072603)
    initial = TinyPolicy()
    before = copy.deepcopy(initial.state_dict())

    actor_only = run_update(initial, isolate_critic=False, value_coef=0.0)
    actor_only_after = actor_only.state_dict()
    isolated = run_update(initial, isolate_critic=True, value_coef=1.0)
    isolated_after = isolated.state_dict()
    for name in isolated_after:
        if not name.startswith("value_head."):
            assert torch.equal(isolated_after[name], actor_only_after[name]), name
    assert changed(before, isolated_after, "value_head.")

    coupled = run_update(initial, isolate_critic=False, value_coef=1.0)
    coupled_after = coupled.state_dict()
    assert any(
        not torch.equal(coupled_after[name], actor_only_after[name])
        for name in coupled_after
        if name.startswith("trunk.")
    )
    assert changed(before, coupled_after, "value_head.")
