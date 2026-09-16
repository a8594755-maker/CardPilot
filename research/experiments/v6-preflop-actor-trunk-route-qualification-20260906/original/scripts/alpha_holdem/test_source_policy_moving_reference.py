import copy
import io
import random

import numpy as np
import pytest
import torch

from alpha_holdem.source_policy_reference import (
    advance_moving_reference,
    categorical_policy_kl,
    moving_reference_checkpoint_state,
    restore_moving_reference_checkpoint,
    restore_training_rng_state,
)


def test_explicit_kl_directions_match_manual_legal_support_and_are_asymmetric():
    current = torch.tensor(
        [[0.4, -0.7, 99.0, 1.2], [-1.0, 77.0, 0.3, 0.8]],
        dtype=torch.float64,
        requires_grad=True,
    )
    reference = torch.tensor(
        [[-0.2, 1.1, -91.0, 0.6], [0.9, -88.0, -0.4, 0.2]],
        dtype=torch.float64,
    )
    legal = torch.tensor([[1, 1, 0, 1], [1, 0, 1, 1]], dtype=torch.float32)
    temperature = 0.73

    reverse = categorical_policy_kl(
        current,
        reference,
        legal,
        temperature=temperature,
        direction="reference_to_current",
    )
    forward = categorical_policy_kl(
        current,
        reference,
        legal,
        temperature=temperature,
        direction="current_to_reference",
    )
    expected_reverse = []
    expected_forward = []
    for row in range(2):
        keep = legal[row].bool()
        log_current = torch.log_softmax(current[row, keep] / temperature, 0)
        log_reference = torch.log_softmax(reference[row, keep] / temperature, 0)
        expected_reverse.append(
            (log_reference.exp() * (log_reference - log_current)).sum()
        )
        expected_forward.append(
            (log_current.exp() * (log_current - log_reference)).sum()
        )
    assert torch.allclose(reverse, torch.stack(expected_reverse), atol=1e-7)
    assert torch.allclose(forward, torch.stack(expected_forward), atol=1e-7)
    assert not torch.allclose(reverse, forward)

    forward.sum().backward()
    assert torch.isfinite(current.grad).all()
    assert current.grad[0, 2].item() == 0.0
    assert current.grad[1, 1].item() == 0.0


def test_legacy_direction_preserves_original_softmax_clamp_formula():
    current = torch.tensor([[0.3, -1.2, -1e9, 0.7]], dtype=torch.float32)
    reference = torch.tensor([[-0.8, 1.4, -1e9, 0.1]], dtype=torch.float32)
    legal = torch.tensor([[1, 1, 0, 1]], dtype=torch.float32)
    temperature = 0.61
    reference_probs = torch.softmax(reference / temperature, dim=-1)
    current_probs = torch.softmax(current / temperature, dim=-1)
    original = (
        reference_probs
        * (
            reference_probs.clamp_min(1e-8).log()
            - current_probs.clamp_min(1e-8).log()
        )
    ).sum(dim=-1)
    actual = categorical_policy_kl(
        current,
        reference,
        legal,
        temperature=temperature,
        direction="reference_to_current",
    )
    assert torch.equal(actual, original)


def test_current_to_reference_gradient_matches_finite_difference():
    current = torch.tensor([[0.2, -0.5, 0.9]], dtype=torch.float64, requires_grad=True)
    reference = torch.tensor([[-0.4, 0.7, 0.1]], dtype=torch.float64)
    legal = torch.ones_like(current)
    loss = categorical_policy_kl(
        current,
        reference,
        legal,
        direction="current_to_reference",
    ).sum()
    loss.backward()
    analytic = current.grad.detach().clone()
    eps = 1e-4
    finite = torch.zeros_like(current)
    for col in range(current.shape[1]):
        plus = current.detach().clone()
        minus = current.detach().clone()
        plus[0, col] += eps
        minus[0, col] -= eps
        finite[0, col] = (
            categorical_policy_kl(
                plus, reference, legal, direction="current_to_reference"
            ).sum()
            - categorical_policy_kl(
                minus, reference, legal, direction="current_to_reference"
            ).sum()
        ) / (2 * eps)
    assert torch.allclose(analytic, finite, atol=3e-4, rtol=2e-3)


def test_refresh_occurs_only_after_completed_update_boundary():
    current = torch.nn.Linear(3, 2)
    reference = copy.deepcopy(current)
    with torch.no_grad():
        current.weight.add_(1.0)
    first = advance_moving_reference(
        current,
        reference,
        refresh_interval_updates=2,
        completed_updates=0,
        last_refresh_update=0,
        reference_round=0,
    )
    assert first == {
        "completed_updates": 1,
        "last_refresh_update": 0,
        "reference_round": 0,
        "refreshed": False,
    }
    assert not torch.equal(current.weight, reference.weight)
    second = advance_moving_reference(
        current,
        reference,
        refresh_interval_updates=2,
        completed_updates=first["completed_updates"],
        last_refresh_update=first["last_refresh_update"],
        reference_round=first["reference_round"],
    )
    assert second["refreshed"] is True
    assert second["completed_updates"] == 2
    assert second["last_refresh_update"] == 2
    assert second["reference_round"] == 1
    assert torch.equal(current.weight, reference.weight)


def test_checkpoint_roundtrip_restores_reference_counters_optimizer_and_rng():
    random.seed(31)
    np.random.seed(32)
    torch.manual_seed(33)
    current = torch.nn.Linear(4, 2)
    reference = copy.deepcopy(current)
    optimizer = torch.optim.Adam(current.parameters(), lr=3e-4)
    optimizer.zero_grad()
    current(torch.ones(2, 4)).sum().backward()
    optimizer.step()
    with torch.no_grad():
        reference.weight.sub_(0.25)

    moving = moving_reference_checkpoint_state(
        reference,
        direction="current_to_reference",
        refresh_interval_updates=4,
        completed_updates=6,
        last_refresh_update=4,
        reference_round=1,
        activation_iteration=20,
        trainer_iteration=26,
    )
    expected_python = random.random()
    expected_numpy = float(np.random.random())
    expected_torch = torch.rand(3)
    payload = {
        "model": current.state_dict(),
        "optimizer": optimizer.state_dict(),
        "moving_source_policy_reference": moving,
    }
    buffer = io.BytesIO()
    torch.save(payload, buffer)
    buffer.seek(0)
    loaded = torch.load(buffer, weights_only=False)

    resumed_current = torch.nn.Linear(4, 2)
    resumed_reference = torch.nn.Linear(4, 2)
    resumed_optimizer = torch.optim.Adam(resumed_current.parameters(), lr=9e-2)
    resumed_current.load_state_dict(loaded["model"])
    resumed_optimizer.load_state_dict(loaded["optimizer"])
    restored = restore_moving_reference_checkpoint(
        resumed_reference,
        loaded["moving_source_policy_reference"],
        direction="current_to_reference",
        refresh_interval_updates=4,
    )
    restore_training_rng_state(restored["rng_state"])
    assert random.random() == expected_python
    assert float(np.random.random()) == expected_numpy
    assert torch.equal(torch.rand(3), expected_torch)
    assert restored["completed_updates"] == 6
    assert restored["last_refresh_update"] == 4
    assert restored["reference_round"] == 1
    assert restored["activation_iteration"] == 20
    assert restored["trainer_iteration"] == 26
    for expected, actual in zip(reference.parameters(), resumed_reference.parameters()):
        assert torch.equal(expected, actual)
    assert resumed_optimizer.param_groups[0]["lr"] == pytest.approx(3e-4)
    assert len(resumed_optimizer.state) == len(optimizer.state)


def test_resume_rejects_direction_interval_and_cadence_mismatch():
    reference = torch.nn.Linear(2, 2)
    state = moving_reference_checkpoint_state(
        reference,
        direction="current_to_reference",
        refresh_interval_updates=3,
        completed_updates=4,
        last_refresh_update=3,
        reference_round=1,
        activation_iteration=10,
        trainer_iteration=14,
    )
    with pytest.raises(RuntimeError, match="direction mismatch"):
        restore_moving_reference_checkpoint(
            copy.deepcopy(reference),
            state,
            direction="reference_to_current",
            refresh_interval_updates=3,
        )
    with pytest.raises(RuntimeError, match="interval mismatch"):
        restore_moving_reference_checkpoint(
            copy.deepcopy(reference),
            state,
            direction="current_to_reference",
            refresh_interval_updates=2,
        )
    corrupt = copy.deepcopy(state)
    corrupt["last_refresh_update"] = 0
    with pytest.raises(RuntimeError, match="refresh cadence"):
        restore_moving_reference_checkpoint(
            copy.deepcopy(reference),
            corrupt,
            direction="current_to_reference",
            refresh_interval_updates=3,
        )
    stale = copy.deepcopy(state)
    stale["trainer_iteration"] = 15
    with pytest.raises(RuntimeError, match="trainer iteration"):
        restore_moving_reference_checkpoint(
            copy.deepcopy(reference),
            stale,
            direction="current_to_reference",
            refresh_interval_updates=3,
        )
