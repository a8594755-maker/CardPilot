import copy

import numpy as np
import pytest
import torch

from alpha_holdem.train_mp3_hybrid_h1 import (
    source_greedy_margin_preservation_loss,
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


def call_loss(logits, reference, *, action=0, advantage=0.0, legal=None):
    if legal is None:
        legal = torch.ones_like(logits)
    return source_greedy_margin_preservation_loss(
        logits,
        reference,
        torch.tensor([action]),
        torch.tensor([advantage]),
        torch.tensor([True]),
        legal,
        max_margin=0.1,
        release_advantage=1.0,
    )


def test_exact_source_boundary_has_zero_loss_without_sharpening():
    logits = torch.tensor([[0.4, 0.2, -0.3]], requires_grad=True)
    loss, eligible, released, violations = call_loss(logits, logits.detach())
    assert loss.item() == 0.0
    assert eligible.item() == 1 and released.item() == violations.item() == 0
    loss.backward()
    assert torch.equal(logits.grad, torch.zeros_like(logits))


def test_eroded_source_boundary_pushes_source_up_and_competitor_down():
    logits = torch.tensor([[0.1, 0.2, -0.3]], requires_grad=True)
    reference = torch.tensor([[0.6, 0.2, -0.3]])
    loss, eligible, released, violations = call_loss(logits, reference)
    assert torch.isclose(loss, torch.tensor(0.2))
    assert eligible.item() == violations.item() == 1 and released.item() == 0
    loss.backward()
    assert logits.grad[0, 0] < 0.0
    assert logits.grad[0, 1] > 0.0
    assert logits.grad[0, 2] == 0.0


def test_strong_positive_different_action_releases_preservation():
    logits = torch.tensor([[0.1, 0.2, -0.3]], requires_grad=True)
    reference = torch.tensor([[0.6, 0.2, -0.3]])
    loss, eligible, released, violations = call_loss(
        logits, reference, action=1, advantage=1.01
    )
    assert loss.item() == 0.0
    assert eligible.item() == violations.item() == 0 and released.item() == 1
    loss.backward()
    assert torch.equal(logits.grad, torch.zeros_like(logits))


def test_illegal_reference_peak_is_ignored_and_validation_is_strict():
    logits = torch.tensor([[0.1, 0.0, 10.0]], requires_grad=True)
    reference = torch.tensor([[0.5, 0.0, 20.0]])
    legal = torch.tensor([[1.0, 1.0, 0.0]])
    loss, _, _, violations = call_loss(logits, reference, legal=legal)
    assert loss.item() == 0.0 and violations.item() == 0
    with pytest.raises(ValueError, match='positive'):
        source_greedy_margin_preservation_loss(
            logits, reference, torch.tensor([0]), torch.tensor([0.0]),
            torch.tensor([True]), legal, max_margin=0.0, release_advantage=1.0,
        )


def test_real_ppo_update_reports_preservation_and_changes_actor():
    torch.set_num_threads(1)
    torch.manual_seed(81)
    source = FixedDataModel()
    with torch.no_grad():
        source.policy_head.bias[0] += 0.5
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
        transitions.append((
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
        ))
    optimizers = [torch.optim.Adam(model.parameters(), lr=0.001) for model in models]
    results = []
    for coefficient, model, optimizer in zip((0.0, 1.0), models, optimizers):
        torch.manual_seed(82)
        np.random.seed(82)
        results.append(trinal_clip_ppo_update(
            model,
            optimizer,
            transitions,
            'cpu',
            epochs=2,
            mini_batch_size=16,
            critic_contract='critic_v2',
            reference_policy=copy.deepcopy(source),
            source_greedy_margin_coef=coefficient,
            source_greedy_margin_max=0.1,
            source_greedy_margin_release_advantage=100.0,
        ))
    assert results[0]['source_greedy_margin_eligible_rows'] == 0
    assert results[1]['source_greedy_margin_eligible_rows'] > 0
    assert results[1]['source_greedy_margin_violation_rows'] > 0
    assert results[1]['source_greedy_margin_loss'] > 0.0
    assert not torch.equal(models[0].policy_head.weight, models[1].policy_head.weight)
