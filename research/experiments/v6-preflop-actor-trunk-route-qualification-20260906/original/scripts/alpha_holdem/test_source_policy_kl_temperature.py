import copy

import numpy as np
import pytest
import torch

from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


def rows(model):
    result = []
    for index in range(48):
        extras = np.asarray([index % 2, index % 3, index / 48], dtype=np.float32)
        action = index % 9
        with torch.no_grad():
            tensor = torch.tensor(extras)
            logits = model.policy_head(tensor)
            value = float(model.value_head(tensor).squeeze())
        result.append((
            np.zeros((6, 4, 13), np.float32),
            np.zeros((25, 4, 5), np.float32),
            extras,
            np.ones(9, np.float32),
            action,
            float(logits.log_softmax(-1)[action]),
            float((index % 5) - 2),
            value,
            1.0,
            10.0,
            10.0,
            1.0,
        ))
    return result


def run(model, reference, temperature):
    torch.manual_seed(303)
    np.random.seed(303)
    return trinal_clip_ppo_update(
        model,
        torch.optim.Adam(model.parameters(), lr=0.0),
        rows(model),
        'cpu',
        epochs=1,
        mini_batch_size=48,
        critic_contract='critic_v2',
        reference_policy=reference,
        reference_policy_kl_coef=0.1,
        reference_policy_temperature=temperature,
    )


def test_default_reference_temperature_inherits_policy_temperature():
    torch.manual_seed(301)
    reference = TinyModel()
    model = copy.deepcopy(reference)
    with torch.no_grad():
        model.policy_head.bias[0] += 0.4
    inherited = run(copy.deepcopy(model), reference, None)
    explicit = run(copy.deepcopy(model), reference, 1.0)
    assert inherited['reference_policy_temperature'] == 1.0
    assert explicit['reference_policy_temperature'] == 1.0
    assert inherited['reference_policy_kl'] == explicit['reference_policy_kl']


def test_low_reference_temperature_changes_only_reference_loss_contract():
    torch.manual_seed(302)
    reference = TinyModel()
    model = copy.deepcopy(reference)
    with torch.no_grad():
        model.policy_head.bias[0] += 0.7
        model.policy_head.bias[1] -= 0.4
    unit = run(copy.deepcopy(model), reference, 1.0)
    sharp = run(copy.deepcopy(model), reference, 0.5)
    assert unit['policy_temperature'] == sharp['policy_temperature'] == 1.0
    assert unit['reference_policy_temperature'] == 1.0
    assert sharp['reference_policy_temperature'] == 0.5
    assert sharp['reference_policy_kl'] != unit['reference_policy_kl']


def test_nonpositive_reference_temperature_rejected():
    model = TinyModel()
    with pytest.raises(ValueError, match='reference policy temperature must be positive'):
        run(model, copy.deepcopy(model), 0.0)
