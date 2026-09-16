from dataclasses import replace

import numpy as np

from scripts.alpha_holdem.physical_v6_cfr import (
    PhysicalV6Encoder,
    exploration_strategy,
    legal_slot_actions,
    prior_residual_strategy,
    regret_strategy,
)
from scripts.alpha_holdem.policy_contract_v6 import action_table, apply_incr
from scripts.alpha_holdem.rules_v6 import ChipState


def test_adapter_uses_exact_shared_action_slots_and_transitions():
    state = ChipState.new(tuple(range(52)))
    _, table = action_table(state)
    assert legal_slot_actions(state) == [
        (slot, action) for slot, action in enumerate(table) if action is not None
    ]
    for _, action in legal_slot_actions(state):
        child = apply_incr(state, action)
        child.assert_invariants()


def test_encoder_is_invariant_to_unobserved_opponent_holes():
    state = ChipState.new(tuple(range(52)))
    altered = replace(state, holes=((10, 11), state.holes[1]))
    np.testing.assert_array_equal(
        PhysicalV6Encoder.encode(state), PhysicalV6Encoder.encode(altered)
    )


def test_encoder_changes_with_acting_players_private_cards():
    state = ChipState.new(tuple(range(52)))
    altered = replace(state, holes=(state.holes[0], (10, 11)))
    assert not np.array_equal(
        PhysicalV6Encoder.encode(state), PhysicalV6Encoder.encode(altered)
    )


def test_regret_strategy_masks_illegal_slots():
    advantages = np.arange(9, dtype=np.float32)
    mask = np.zeros(9, dtype=np.float32)
    mask[[0, 1, 4]] = 1
    strategy = regret_strategy(advantages, mask)
    assert np.isclose(strategy.sum(), 1.0)
    assert np.all(strategy[mask == 0] == 0)
    assert strategy[4] > strategy[1] > strategy[0]


def test_opponent_exploration_adds_support_only_to_legal_slots():
    strategy = np.zeros(9, dtype=np.float32)
    strategy[1] = 1
    mask = np.zeros(9, dtype=np.float32)
    mask[[0, 1, 4, 8]] = 1
    mixed = exploration_strategy(strategy, mask, 0.1)
    assert np.isclose(mixed.sum(), 1)
    assert np.all(mixed[mask == 0] == 0)
    assert np.all(mixed[[0, 4, 8]] > 0)
    assert mixed[1] > mixed[0]


def test_zero_residual_reproduces_normalized_prior_exactly():
    prior = np.asarray([0.0, 0.2, 0.0, 0.3, 0.5, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    mask = (prior > 0).astype(np.float32)
    strategy = prior_residual_strategy(prior, np.zeros(9, dtype=np.float32), mask)
    np.testing.assert_allclose(strategy, prior, atol=1e-7)
    assert int(np.argmax(strategy)) == int(np.argmax(prior))


def test_prior_residual_is_state_conditioned_and_legality_safe():
    prior = np.asarray([0.0, 0.6, 0.0, 0.3, 0.1, 0.0, 0.0, 0.0, 0.0], dtype=np.float32)
    mask = (prior > 0).astype(np.float32)
    residual = np.zeros(9, dtype=np.float32)
    residual[4] = 3.0
    strategy = prior_residual_strategy(prior, residual, mask)
    assert np.isclose(strategy.sum(), 1.0)
    assert np.all(strategy[mask == 0] == 0)
    assert int(np.argmax(strategy)) == 4


def test_terminal_payoffs_are_zero_sum_bb():
    state = ChipState.new(tuple(range(52)))
    terminal = state.act("f")
    payoffs = terminal.payoffs()
    assert sum(payoffs) == 0
    assert payoffs == (50, -50)
