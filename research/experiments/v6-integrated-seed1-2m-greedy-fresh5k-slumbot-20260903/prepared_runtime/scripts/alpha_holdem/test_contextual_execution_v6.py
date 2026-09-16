import numpy as np
import pytest

from scripts.alpha_holdem.contextual_execution_v6 import SessionContextTracker


def test_session_tracker_requires_contiguous_hands_and_64_hand_cold_start():
    tracker = SessionContextTracker(64)
    terminal = {"client_pos": 0, "action": "f", "hole_cards": ["As", "Kd"], "board": []}
    for hand in range(1, 65):
        started = tracker.start_hand(hand)
        assert started["context_completed_hands"] == hand - 1
        assert started["context_cold_start"]
        finished = tracker.finish_hand(hand, terminal)
        assert finished["context_completed_hands"] == hand
    active = tracker.start_hand(65)
    assert not active["context_cold_start"]
    assert active["context_completed_hands"] == 64
    with pytest.raises(ValueError, match="contiguous"):
        tracker.start_hand(67)


def test_session_tracker_rejects_duplicate_finish():
    tracker = SessionContextTracker()
    terminal = {"client_pos": 0, "action": "f", "hole_cards": ["As", "Kd"], "board": []}
    tracker.start_hand(1)
    tracker.finish_hand(1, terminal)
    with pytest.raises(ValueError, match="already completed"):
        tracker.finish_hand(1, terminal)


def test_session_tracker_zero_context_is_finite():
    tracker = SessionContextTracker()
    metadata = tracker.start_hand(1)
    assert len(metadata["context_feature_vector"]) == 20
    assert np.isfinite(metadata["context_feature_vector"]).all()
