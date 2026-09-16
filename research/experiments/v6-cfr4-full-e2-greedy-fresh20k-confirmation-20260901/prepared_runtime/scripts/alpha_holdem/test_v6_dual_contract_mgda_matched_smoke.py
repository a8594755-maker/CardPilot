import numpy as np
import torch

from scripts.alpha_holdem.v6_dual_contract_mgda_matched_smoke import (
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
