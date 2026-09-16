import pytest

from scripts.alpha_holdem.v6_cagrad_vs_mgda_matched_audit import paired_summary


def test_paired_summary_uses_bb100_scale_and_finite_interval():
    result = paired_summary([1.0, -1.0, 2.0, 0.0])
    assert result["pairs"] == 4
    assert result["delta_bb100"] == pytest.approx(50.0)
    assert result["delta_ci95_lower_bb100"] < result["delta_bb100"]
    assert result["delta_ci95_upper_bb100"] > result["delta_bb100"]
