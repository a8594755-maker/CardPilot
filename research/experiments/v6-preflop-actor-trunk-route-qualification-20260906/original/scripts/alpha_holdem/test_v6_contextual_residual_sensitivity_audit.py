import numpy as np
import pytest

from scripts.alpha_holdem.v6_contextual_residual_sensitivity_audit import summarize_state


def test_summarize_state_separates_generic_and_contextual_delta():
    base = np.asarray([2.0, 1.0, -1.0])
    candidates = np.asarray([[2.2, 1.0, -1.0], [1.8, 1.3, -1.0]])
    result = summarize_state(base, candidates, np.asarray([0, 1]))
    assert result["generic_delta_rms"] > 0
    assert result["contextual_delta_rms"] > 0
    assert result["maximum_context_logit_spread"] == pytest.approx(0.4)
    assert not result["context_action_disagreement"]


def test_summarize_state_detects_context_argmax_crossing():
    base = np.asarray([1.0, 0.9])
    candidates = np.asarray([[1.2, 0.9], [0.8, 1.1]])
    result = summarize_state(base, candidates, np.asarray([0, 1]))
    assert result["context_action_disagreement"]
    assert result["base_action_changed"]
    assert result["crossing_slack"] >= 0
