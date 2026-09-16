import copy

import numpy as np
import torch

from alpha_holdem.train_mp3_hybrid_h1 import (
    greedy_advantage_margin_loss,
    trinal_clip_ppo_update,
)


class FixedDataModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


def test_margin_promotes_positive_sampled_action_over_greedy():
    logits = torch.tensor([[2.0, 1.0, -1e30]], requires_grad=True)
    actions = torch.tensor([1])
    advantages = torch.tensor([2.0])
    policy_rows = torch.tensor([True])
    loss, eligible, positive = greedy_advantage_margin_loss(
        logits, actions, advantages, policy_rows, margin=0.25
    )
    assert loss.item() == 1.25
    assert eligible.item() == positive.item() == 1
    loss.backward()
    assert logits.grad[0, 1] < 0.0
    assert logits.grad[0, 0] > 0.0
    assert logits.grad[0, 2] == 0.0


def test_margin_uses_detached_legal_argmax_and_skips_nonpositive_rows():
    logits = torch.tensor(
        [[0.1, 0.2, -1e30], [0.4, 0.3, -1e30]],
        requires_grad=True,
    )
    actions = torch.tensor([0, 1])
    advantages = torch.tensor([1.0, -1.0])
    policy_rows = torch.tensor([True, True])
    loss, eligible, positive = greedy_advantage_margin_loss(
        logits, actions, advantages, policy_rows, margin=0.1
    )
    assert eligible.item() == positive.item() == 1
    assert torch.isclose(loss, torch.tensor(0.2))


def test_margin_returns_differentiable_zero_without_eligible_rows():
    logits = torch.tensor([[2.0, 1.0]], requires_grad=True)
    loss, eligible, positive = greedy_advantage_margin_loss(
        logits,
        torch.tensor([0]),
        torch.tensor([1.0]),
        torch.tensor([True]),
        margin=0.1,
    )
    assert loss.item() == 0.0
    assert eligible.item() == 0 and positive.item() == 1
    loss.backward()
    assert torch.equal(logits.grad, torch.zeros_like(logits))


def test_margin_rejects_nonpositive_margin():
    logits = torch.zeros((1, 2))
    try:
        greedy_advantage_margin_loss(
            logits,
            torch.tensor([0]),
            torch.tensor([1.0]),
            torch.tensor([True]),
            margin=0.0,
        )
    except ValueError as exc:
        assert 'positive' in str(exc)
    else:
        raise AssertionError('nonpositive margin was accepted')


def test_margin_changes_real_ppo_actor_and_reports_eligibility():
    torch.set_num_threads(1)
    torch.manual_seed(71)
    source = FixedDataModel()
    with torch.no_grad():
        source.policy_head.bias[0] += 1.0
    models = [copy.deepcopy(source), copy.deepcopy(source)]
    transitions = []
    for index in range(64):
        extras = np.asarray(
            [index % 2, index % 3, (index % 7) / 7], dtype=np.float32
        )
        action = 1 + index % 8
        with torch.no_grad():
            tensor = torch.tensor(extras)
            logits = source.policy_head(tensor)
            old_log_prob = float(logits.log_softmax(-1)[action])
            value = float(source.value_head(tensor).squeeze())
        transitions.append(
            (
                np.zeros((6, 4, 13), np.float32),
                np.zeros((25, 4, 5), np.float32),
                extras,
                np.ones(9, np.float32),
                action,
                old_log_prob,
                float(1 + index % 3),
                value,
                1.0,
                10.0,
                10.0,
                1.0,
            )
        )
    optimizers = [torch.optim.Adam(model.parameters(), lr=0.001) for model in models]
    results = []
    for coefficient, model, optimizer in zip((0.0, 0.05), models, optimizers):
        torch.manual_seed(72)
        np.random.seed(72)
        results.append(
            trinal_clip_ppo_update(
                model,
                optimizer,
                transitions,
                'cpu',
                epochs=1,
                mini_batch_size=16,
                critic_contract='critic_v2',
                greedy_advantage_margin_coef=coefficient,
                greedy_advantage_margin=0.1,
            )
        )
    assert results[0]['greedy_advantage_margin_eligible_rows'] == 0
    assert results[1]['greedy_advantage_margin_eligible_rows'] > 0
    assert results[1]['greedy_advantage_margin_loss'] > 0.0
    assert not torch.equal(
        models[0].policy_head.weight,
        models[1].policy_head.weight,
    )
