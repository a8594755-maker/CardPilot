import numpy as np

from scripts.alpha_holdem.v6_context_reliability_feasibility import auc_higher_positive, normalized_reliability


def test_normalized_reliability_uniform_zero_and_one_hot_one():
    probabilities = np.asarray([[0.5, 0.5], [1.0, 0.0]])
    reliability = normalized_reliability(probabilities)
    assert np.allclose(reliability, [0.0, 1.0])


def test_auc_higher_positive_handles_separation_and_ties():
    assert auc_higher_positive(np.asarray([2.0, 3.0]), np.asarray([0.0, 1.0])) == 1.0
    assert auc_higher_positive(np.asarray([1.0]), np.asarray([1.0])) == 0.5
