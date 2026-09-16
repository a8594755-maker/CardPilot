import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.rules_v6 import ChipState
from scripts.alpha_holdem.v6_history_consistent_hole_posterior import (
    deck_for_holes,
    event_action,
    same_public_financial_state,
)


def test_deck_for_holes_preserves_candidate_opponent_and_board():
    deck = deck_for_holes(
        candidate_seat=1,
        candidate_holes=(8, 9),
        opponent_holes=(2, 3),
        board=(10, 11, 12),
    )
    state = ChipState.new(deck).act('c').act('k')
    assert state.holes == ((2, 3), (8, 9))
    assert state.board == (10, 11, 12)
    assert len(set(deck)) == 52


def test_event_action_and_public_state_comparison():
    first = ChipState.new(list(range(52))).act('b', 200)
    assert event_action(first.history[-1]) == 'b200'
    second = ChipState.new(list(range(52))).act('b', 200)
    assert same_public_financial_state(first, second)
