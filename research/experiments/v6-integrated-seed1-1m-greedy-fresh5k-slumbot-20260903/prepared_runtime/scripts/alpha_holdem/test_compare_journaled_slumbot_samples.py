import pytest

from scripts.alpha_holdem.compare_journaled_slumbot_samples import difference


def test_independent_difference_direction_and_units():
    result = difference([1.0, 2.0, 3.0], [0.0, 1.0, 2.0])
    assert result["delta_bb_per_100"] == pytest.approx(100.0)
    assert result["ci95_low_bb_per_100"] < result["delta_bb_per_100"]
    assert result["ci95_high_bb_per_100"] > result["delta_bb_per_100"]
