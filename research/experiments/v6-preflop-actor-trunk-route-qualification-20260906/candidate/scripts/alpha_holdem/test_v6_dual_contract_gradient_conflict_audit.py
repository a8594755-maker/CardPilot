import numpy as np
import torch

from scripts.alpha_holdem.v6_dual_contract_gradient_conflict_audit import (
    flatten_gradients,
    minimum_norm_simplex,
)


def test_minimum_norm_simplex_finds_balanced_common_descent_direction():
    unit = np.asarray([[1.0, 0.0], [0.0, 1.0], [1.0, 1.0]])
    unit /= np.linalg.norm(unit, axis=1, keepdims=True)
    gram = unit @ unit.T
    objective, _, weights, products = minimum_norm_simplex(gram)
    assert np.all(weights >= 0.0)
    assert np.isclose(weights.sum(), 1.0)
    assert objective > 0.0
    assert np.all(products >= objective - 1e-8)
    assert np.all((unit @ (weights @ unit)) > 0.0)


def test_minimum_norm_simplex_detects_no_strict_common_direction():
    gram = np.asarray([[1.0, -1.0], [-1.0, 1.0]])
    objective, _, weights, _ = minimum_norm_simplex(gram)
    assert np.isclose(weights.sum(), 1.0)
    assert objective < 1e-12


def test_flatten_gradients_includes_unused_parameter_as_zero():
    used = torch.nn.Parameter(torch.tensor([2.0, 3.0]))
    unused = torch.nn.Parameter(torch.tensor([5.0]))
    flat = flatten_gradients((used.square()).sum(), [used, unused])
    assert torch.equal(flat, torch.tensor([4.0, 6.0, 0.0]))
