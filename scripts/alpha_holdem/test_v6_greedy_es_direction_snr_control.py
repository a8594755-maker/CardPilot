import numpy as np
import pytest

from scripts.alpha_holdem.v6_greedy_es_direction_snr_control import (
    rank_correlation,
    stable_direction_count,
)


def test_rank_correlation_tracks_order_not_scale():
    assert rank_correlation(np.asarray([1, 2, 3, 4]), np.asarray([10, 20, 30, 40])) == pytest.approx(1.0)
    assert rank_correlation(np.asarray([1, 2, 3, 4]), np.asarray([40, 30, 20, 10])) == pytest.approx(-1.0)


def test_stable_direction_count_requires_three_matching_quarter_signs():
    quarters = [
        np.asarray([1.0, 1.0, -1.0]),
        np.asarray([2.0, -1.0, -2.0]),
        np.asarray([3.0, 2.0, 1.0]),
        np.asarray([-1.0, 3.0, 2.0]),
    ]
    assert stable_direction_count(quarters) == 2
