import numpy as np

from scripts.alpha_holdem.v6_state_conditioned_expert_router_audit import (
    _expert_payoff,
    estimate,
    private_features,
)


def _rows(xs, ys):
    return [{"x": np.asarray(x, dtype=np.float64), "y": float(y)} for x, y in zip(xs, ys)]


def test_right_expert_seat_payoff_mapping():
    row = {
        "left": 2, "right": 5,
        "left_reward_seat0_bb": 3.0,
        "left_reward_seat1_bb": -7.0,
    }
    assert _expert_payoff(row, 5, 2, 0) == 7.0
    assert _expert_payoff(row, 5, 2, 1) == -3.0


def test_private_features_are_seat_local_and_fixed_width():
    deck = list(range(52))
    x0 = private_features(deck, 0)
    x1 = private_features(deck, 1)
    changed = deck.copy()
    changed[-1], changed[-2] = changed[-2], changed[-1]
    assert x0.shape == x1.shape == (66,)
    assert np.array_equal(x0, private_features(changed, 0))
    assert np.array_equal(x1, private_features(changed, 1))
    assert not np.array_equal(x0, x1)


def test_independent_stream_router_estimator_recovers_complementarity():
    xs = [[1.0, -1.0], [1.0, 1.0]] * 100
    rows0 = _rows(xs, [2.0, 0.0] * 100)
    rows1 = _rows(xs, [0.0, 2.0] * 100)
    beta0 = np.asarray([0.0, -1.0])
    beta1 = np.asarray([0.0, 1.0])
    result = estimate(rows0, rows1, beta0, beta1, bootstrap=1000, seed=7)
    assert result["router_bb100"] == 200.0
    assert result["standard10_bb100"] == 100.0
    assert result["delta_vs_standard10_bb100"] == 100.0
    assert result["alternate_selection_fraction"] == 0.5
    assert result["delta_ci95"][0] > 0.0
