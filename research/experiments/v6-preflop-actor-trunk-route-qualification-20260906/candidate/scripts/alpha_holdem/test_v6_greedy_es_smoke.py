import numpy as np
import pytest
import torch

from scripts.alpha_holdem.dual_contract_residual_v6 import DualContractResidualPolicy
from scripts.alpha_holdem.v6_greedy_es_smoke import (
    es_update_direction,
    policy_vector,
    robust_score,
    set_policy_vector,
)


def test_robust_score_penalizes_group_dispersion():
    balanced = robust_score([[1.0, 1.0], [1.0, 1.0]], 0.5)
    dispersed = robust_score([[0.0, 0.0], [2.0, 2.0]], 0.5)
    assert balanced == pytest.approx(1.0)
    assert dispersed == pytest.approx(0.5)


def test_es_update_uses_mirrored_fitness_sign_and_is_unit_norm():
    directions = np.eye(3)
    update = es_update_direction(directions, np.asarray([2.0, -1.0, 0.0]))
    assert np.linalg.norm(update) == pytest.approx(1.0)
    assert update[0] > 0
    assert update[1] < 0


def test_policy_vector_roundtrip_only_changes_output_layer():
    base = torch.nn.Sequential(torch.nn.Linear(1, 9))
    model = DualContractResidualPolicy(base, hidden=8, policy_delta_cap=0.25)
    before = {name: value.detach().clone() for name, value in model.state_dict().items()}
    vector = policy_vector(model)
    replacement = np.linspace(-0.01, 0.01, vector.size)
    set_policy_vector(model, replacement)
    assert policy_vector(model) == pytest.approx(replacement, abs=1e-8)
    for name, value in model.state_dict().items():
        if not name.startswith("policy_delta."):
            assert torch.equal(value, before[name])
