import numpy as np

from alpha_holdem.legacy_observation_bridge_v6 import action_prefix, reconstruct_legacy_state
from alpha_holdem.policy_contract_v6 import action_table, apply_incr
from alpha_holdem.rules_v6 import ChipState


def test_root_reconstruction_and_prefix():
    state = ChipState.new(deck=list(range(52)))
    parsed, commitments = reconstruct_legacy_state(state)
    assert action_prefix(state) == ""
    assert parsed["st"] == 0 and parsed["pos"] == 1
    assert commitments["pot"] == 150 and commitments["to_call"] == 50


def test_multistreet_reconstruction_is_exact():
    state = ChipState.new(deck=list(range(52)))
    state = apply_incr(state, "c")
    state = apply_incr(state, "k")
    assert state.street == 1
    assert action_prefix(state) == "ck/"
    _, table = action_table(state)
    state = apply_incr(state, table[4])
    state = apply_incr(state, "c")
    assert state.street == 2
    parsed, commitments = reconstruct_legacy_state(state)
    assert parsed["st"] == 2 and parsed["pos"] == state.actor
    assert commitments["pot"] == state.pot


def test_card_indexing_matches_rank_major_suit_minor():
    state = ChipState.new(deck=np.arange(52).tolist())
    assert state.holes[0] == (0, 1)
