import random
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.legacy_observation_bridge_v6 import (
    legacy_observation_from_state,
)
from scripts.alpha_holdem.rules_v6 import ChipState
from scripts.alpha_holdem.v6_counterfactual_target_reliability import (
    resample_future_deck,
    select_best_slot,
)


def test_resample_future_deck_preserves_holes_and_public_board():
    state = ChipState.new(list(range(52)))
    state = state.act('c').act('k')
    assert state.street == 1 and len(state.board) == 3
    deck = resample_future_deck(state, random.Random(7))
    assert deck[:4] == state.deck[:4]
    assert tuple(deck[-index - 1] for index in range(3)) == state.board
    assert len(set(deck)) == 52
    assert deck != state.deck


def test_select_best_slot_prefers_source_then_lower_slot_on_ties():
    assert select_best_slot({0: 1.0, 1: 1.0, 2: 0.0}, source_slot=1) == 1
    assert select_best_slot({0: 1.0, 1: 1.0, 2: 0.0}, source_slot=2) == 0


def test_legacy_bridge_legal_slots_always_have_exact_physical_actions():
    state = ChipState.new(list(range(52))).act('b', 200)
    observation, table = legacy_observation_from_state(state)
    legal = np.flatnonzero(observation['legal_mask'])
    assert len(legal) > 0
    assert all(isinstance(table[int(slot)], str) for slot in legal)
