import numpy as np

from scripts.alpha_holdem.physical_v6_cfr import legal_slot_actions
from scripts.alpha_holdem.rules_v6 import ChipState
from scripts.alpha_holdem.v6_deep_cfr_neural_smoke import (
    _anchor_action,
    _passive_network,
    _strategy,
)


def test_passive_initialization_selects_check_call():
    state = ChipState.new(tuple(range(52)))
    strategy = _strategy(_passive_network(), state)
    assert int(np.argmax(strategy)) == 1
    assert strategy[1] == 1.0


def test_fixed_anchor_actions_are_legal_and_seeded():
    state = ChipState.new(tuple(range(52)))
    legal = {action for _, action in legal_slot_actions(state)}
    assert _anchor_action("call_station", state, np.random.default_rng(1)) == "c"
    first = _anchor_action("uniform", state, np.random.default_rng(5))
    second = _anchor_action("uniform", state, np.random.default_rng(5))
    assert first == second
    assert first in legal


def test_min_bet_anchor_uses_smallest_fractional_slot():
    state = ChipState.new(tuple(range(52))).act("c").act("k")
    action = _anchor_action("min_bet", state, np.random.default_rng(1))
    fractional = [a for slot, a in legal_slot_actions(state) if 2 <= slot < 8]
    assert action == fractional[0]
