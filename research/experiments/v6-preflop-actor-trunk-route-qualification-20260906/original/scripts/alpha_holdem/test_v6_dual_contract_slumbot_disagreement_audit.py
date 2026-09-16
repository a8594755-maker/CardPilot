import pytest

from scripts.alpha_holdem.v6_dual_contract_slumbot_disagreement_audit import (
    action_kind,
    mean_ci,
)


def test_mean_ci_uses_hand_level_bb100_units():
    result = mean_ci([1.0, -1.0, 0.5, -0.5])
    assert result["n"] == 4
    assert result["mean_bb100"] == 0.0
    assert result["ci95_low_bb100"] == pytest.approx(-result["ci95_high_bb100"])


def test_action_kind_preserves_physical_classes():
    assert [action_kind(value) for value in ("f", "c", "k", "b400")] == [
        "fold", "call", "check", "raise",
    ]
