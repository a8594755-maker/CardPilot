import numpy as np
import pytest
import torch

from scripts.alpha_holdem.v6_dual_contract_mgda_matched_smoke import (
    aggregate_cagrad_policy_gradients,
    aggregate_policy_gradients,
    set_flat_gradient,
)


def test_mgda_is_norm_matched_and_improves_worst_alignment():
    gradients = np.asarray([[1.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    decision_weights = np.asarray([0.9, 0.1], dtype=np.float64)
    control, control_metrics = aggregate_policy_gradients(
        gradients, decision_weights, False
    )
    treatment, treatment_metrics = aggregate_policy_gradients(
        gradients, decision_weights, True
    )
    assert np.isclose(np.linalg.norm(treatment), np.linalg.norm(control))
    assert treatment_metrics["applied_worst_alignment"] > control_metrics[
        "applied_worst_alignment"
    ]
    assert treatment_metrics["applied_worst_alignment"] > 0.0


def test_set_flat_gradient_roundtrips_parameter_shapes():
    first = torch.nn.Parameter(torch.zeros(2, 2))
    second = torch.nn.Parameter(torch.zeros(3))
    values = torch.arange(7, dtype=torch.float32)
    set_flat_gradient([first, second], values)
    assert torch.equal(first.grad, values[:4].view(2, 2))
    assert torch.equal(second.grad, values[4:])


def test_cagrad_zero_is_exact_weighted_mean():
    gradients = np.asarray([[2.0, 0.0], [0.0, 1.0]], dtype=np.float64)
    weights = np.asarray([0.25, 0.75], dtype=np.float64)
    aggregate, metrics = aggregate_cagrad_policy_gradients(gradients, weights, 0.0)
    assert aggregate.tolist() == [0.5, 0.75]
    assert metrics["ordinary_applied_cosine"] == 1.0
    assert metrics["applied_to_ordinary_norm_ratio"] == 1.0


def test_cagrad_identical_tasks_preserve_gradient_and_solver_contract():
    gradients = np.asarray([[2.0, -1.0], [2.0, -1.0], [2.0, -1.0]])
    weights = np.full(3, 1.0 / 3.0)
    aggregate, metrics = aggregate_cagrad_policy_gradients(gradients, weights, 0.5)
    assert aggregate == pytest.approx([2.0, -1.0], abs=1e-8)
    assert sum(metrics["cagrad_weights"]) == pytest.approx(1.0)
    assert metrics["cagrad_solver_success"] is True
    assert metrics["ordinary_applied_cosine"] == pytest.approx(1.0)


def test_cagrad_conflict_direction_retains_mean_and_improves_worst_alignment():
    gradients = np.asarray([[1.0, 0.0], [-0.4, 1.0], [0.2, -0.3]])
    weights = np.full(3, 1.0 / 3.0)
    aggregate, metrics = aggregate_cagrad_policy_gradients(gradients, weights, 0.5)
    assert np.isfinite(aggregate).all()
    assert metrics["ordinary_applied_cosine"] > 0.8
    assert metrics["applied_worst_alignment"] >= metrics["ordinary_worst_alignment"] - 1e-8
    assert metrics["applied_to_ordinary_norm_ratio"] > 0.0
