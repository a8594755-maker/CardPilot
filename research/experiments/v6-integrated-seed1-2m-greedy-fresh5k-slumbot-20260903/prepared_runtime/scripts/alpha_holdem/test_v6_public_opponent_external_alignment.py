import numpy as np

from scripts.alpha_holdem.v6_public_opponent_external_alignment import (
    bootstrap_alignment,
    kendall_tau,
    mean_ci95,
    rankdata,
    spearman,
)


def test_rank_statistics_match_exact_orderings():
    assert np.array_equal(rankdata([3, 1, 2]), np.asarray([2.0, 0.0, 1.0]))
    assert spearman([1, 2, 3], [2, 4, 6]) == 1.0
    assert spearman([1, 2, 3], [6, 4, 2]) == -1.0
    assert kendall_tau([1, 2, 3], [2, 4, 6]) == 1.0


def test_mean_ci95_uses_pair_level_units():
    result = mean_ci95([1.0, 2.0, 3.0])
    assert result["count"] == 3
    assert result["bb100"] == 200.0
    assert result["ci95_low_bb100"] < 200.0 < result["ci95_high_bb100"]


def test_bootstrap_alignment_detects_strict_signal():
    pair_matrix = np.asarray([
        [-3.0] * 100,
        [-2.0] * 100,
        [-1.0] * 100,
        [0.0] * 100,
        [1.0] * 100,
        [2.0] * 100,
    ])
    result = bootstrap_alignment(
        pair_matrix,
        np.arange(6, dtype=np.float64),
        np.full(6, 0.01),
        seed=7,
        samples=100,
    )
    assert result["fixed_external_spearman_p05"] == 1.0
    assert result["joint_measurement_probability_positive"] == 1.0
