import numpy as np

from scripts.alpha_holdem.v6_broad_league_domain_feasibility import (
    collect_balanced_states,
    mean_js_divergence,
)


def test_collect_balanced_states_is_deterministic_and_balanced():
    first = collect_balanced_states(16, 123)
    second = collect_balanced_states(16, 123)
    assert [state.street for state in first] == [0] * 4 + [1] * 4 + [2] * 4 + [3] * 4
    assert [state.history for state in first] == [state.history for state in second]
    assert all(not state.terminal for state in first)


def test_mean_js_divergence_identity_and_separation():
    left = np.asarray([[1.0, 0.0], [0.5, 0.5]])
    assert mean_js_divergence(left, left) == 0.0
    right = np.asarray([[0.0, 1.0], [0.5, 0.5]])
    assert 0.0 < mean_js_divergence(left, right) < 1.0
