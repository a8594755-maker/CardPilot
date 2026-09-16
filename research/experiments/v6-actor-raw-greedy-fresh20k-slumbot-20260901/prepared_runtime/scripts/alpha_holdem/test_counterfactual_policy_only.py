#!/usr/bin/env python3
"""Regression checks for policy-only counterfactual replay."""

from __future__ import annotations

import torch

try:
    from alpha_holdem.train_mp3_hybrid_h1 import (
        counterfactual_soft_policy_replay_loss,
    )
except ModuleNotFoundError:
    from scripts.alpha_holdem.train_mp3_hybrid_h1 import (
        counterfactual_soft_policy_replay_loss,
    )


class PolicyOnlyModel(torch.nn.Module):
    """Small model that deliberately has no Action-Q interface or head."""

    def __init__(self) -> None:
        super().__init__()
        self.logits = torch.nn.Parameter(torch.zeros(9))
        self.value = torch.nn.Parameter(torch.zeros(1))

    def forward(self, cards, actions, extras, masks):
        rows = cards.shape[0]
        logits = self.logits.unsqueeze(0).expand(rows, -1)
        logits = logits.masked_fill(masks <= 0.0, -1e9)
        values = self.value.expand(rows, 1)
        return logits, values


def _replay(rows: int = 8):
    legal = torch.ones(rows, 9)
    q_target = torch.linspace(-1.0, 1.0, 9).repeat(rows, 1)
    return {
        "cards": torch.zeros(rows, 6, 4, 13),
        "actions": torch.zeros(rows, 25, 4, 5),
        "extras": torch.zeros(rows, 3),
        "masks": legal,
        "q_target": q_target,
        "weights": legal,
        "cursor": 0,
    }


def test_policy_only_replay_backpropagates_without_action_q_head():
    model = PolicyOnlyModel()
    replay = _replay()
    before = model.logits.detach().clone()
    loss, entropy, max_probability = counterfactual_soft_policy_replay_loss(
        model,
        replay,
        batch_size=4,
        reliability_mode="row_only",
    )
    assert torch.isfinite(loss)
    assert torch.isfinite(entropy)
    assert 0.0 < float(max_probability) < 1.0
    loss.backward()
    assert model.logits.grad is not None
    assert torch.isfinite(model.logits.grad).all()
    assert float(model.logits.grad.abs().sum()) > 0.0
    optimizer = torch.optim.SGD(model.parameters(), lr=0.1)
    optimizer.step()
    assert not torch.equal(before, model.logits.detach())


def test_policy_only_replay_advances_cursor_once():
    model = PolicyOnlyModel()
    replay = _replay(rows=10)
    counterfactual_soft_policy_replay_loss(
        model,
        replay,
        batch_size=4,
        reliability_mode="row_only",
    )
    assert replay["cursor"] == 4
