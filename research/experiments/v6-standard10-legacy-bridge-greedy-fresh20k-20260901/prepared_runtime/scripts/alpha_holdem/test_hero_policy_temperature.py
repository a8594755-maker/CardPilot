import copy

import numpy as np
import pytest
import torch

from alpha_holdem.train_mp3_hybrid_h1 import (
    temperature_policy_distribution,
    trinal_clip_ppo_update,
)


class TinyModel(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.policy_head = torch.nn.Linear(3, 9)
        self.value_head = torch.nn.Linear(3, 1)

    def forward(self, cards, actions, extras, masks):
        logits = self.policy_head(extras).masked_fill(masks <= 0, -1e9)
        return logits, self.value_head(extras)


def test_unit_temperature_is_exact_existing_distribution():
    logits = torch.tensor([[1.2, -0.4, 0.3]])
    probs, dist = temperature_policy_distribution(logits, 1.0)
    assert torch.equal(probs, torch.softmax(logits, dim=-1))
    assert torch.equal(dist.probs, probs)


def test_low_temperature_concentrates_without_changing_argmax():
    logits = torch.tensor([[1.2, -0.4, 0.3]])
    unit, _ = temperature_policy_distribution(logits, 1.0)
    sharp, _ = temperature_policy_distribution(logits, 0.5)
    assert sharp.argmax(-1).item() == unit.argmax(-1).item() == 0
    assert sharp.max().item() > unit.max().item()
    assert torch.allclose(sharp, torch.softmax(logits / 0.5, dim=-1))


def test_temperature_validation_rejects_nonpositive_values():
    with pytest.raises(ValueError, match='positive'):
        temperature_policy_distribution(torch.zeros((1, 2)), 0.0)


def test_real_ppo_uses_matching_temperature_likelihoods():
    torch.set_num_threads(1)
    torch.manual_seed(91)
    source = TinyModel()
    base_rows = []
    for index in range(64):
        extras = np.asarray([index % 2, index % 3, index / 64], dtype=np.float32)
        action = index % 9
        with torch.no_grad():
            tensor = torch.tensor(extras)
            logits = source.policy_head(tensor)
            value = float(source.value_head(tensor).squeeze())
        base_rows.append((extras, action, logits, value, float((index % 5) - 2)))
    outputs, models = [], []
    for temperature in (1.0, 0.5):
        model = copy.deepcopy(source)
        transitions = []
        for extras, action, logits, value, reward in base_rows:
            old_log_prob = float((logits / temperature).log_softmax(-1)[action])
            transitions.append((
                np.zeros((6, 4, 13), np.float32),
                np.zeros((25, 4, 5), np.float32), extras,
                np.ones(9, np.float32), action, old_log_prob, reward, value,
                1.0, 10.0, 10.0, 1.0,
            ))
        torch.manual_seed(92)
        np.random.seed(92)
        outputs.append(trinal_clip_ppo_update(
            model, torch.optim.Adam(model.parameters(), lr=0.001),
            transitions, 'cpu', epochs=1, mini_batch_size=16,
            critic_contract='critic_v2', policy_temperature=temperature,
        ))
        models.append(model)
    assert outputs[0]['policy_temperature'] == 1.0
    assert outputs[1]['policy_temperature'] == 0.5
    assert abs(outputs[0]['approx_kl']) < 0.01
    assert abs(outputs[1]['approx_kl']) < 0.01
    assert not torch.equal(models[0].policy_head.weight, models[1].policy_head.weight)
