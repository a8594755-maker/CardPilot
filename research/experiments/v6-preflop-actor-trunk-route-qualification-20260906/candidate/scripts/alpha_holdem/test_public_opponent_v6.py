from dataclasses import replace

import numpy as np
import torch

from scripts.alpha_holdem.public_opponent_v6 import (
    PublicOpponentPolicy,
    decide,
    strategy,
)
from scripts.alpha_holdem.physical_v6_cfr import PhysicalV6Encoder
from scripts.alpha_holdem.rules_v6 import ChipState
from scripts.alpha_holdem.v6_slumbot_opponent_model_feasibility import PublicOpponentModel


def _policy():
    torch.manual_seed(7)
    return PublicOpponentPolicy(PublicOpponentModel().eval(), None, "test", ())


def test_public_strategy_is_legal_and_normalized():
    state = ChipState.new(tuple(range(52)))
    probabilities = strategy(_policy(), state)
    mask = PhysicalV6Encoder.legal_mask(state)
    assert np.isclose(probabilities.sum(), 1.0)
    assert np.all(probabilities >= 0)
    assert np.all(probabilities[mask == 0] == 0)
    action, metadata = decide(_policy(), state, np.random.default_rng(3))
    assert action is not None
    assert metadata["behavior_probability"] > 0


def test_public_strategy_is_invariant_to_acting_players_private_cards():
    state = ChipState.new(tuple(range(52)))
    altered = replace(state, holes=(state.holes[0], (10, 11)))
    np.testing.assert_array_equal(strategy(_policy(), state), strategy(_policy(), altered))


def test_public_action_sampling_replays_from_rng_seed():
    state = ChipState.new(tuple(range(52)))
    first = decide(_policy(), state, np.random.default_rng(99))
    second = decide(_policy(), state, np.random.default_rng(99))
    assert first == second


def test_public_strategy_respects_stricter_execution_legal_mask():
    state = ChipState.new(tuple(range(52)))
    physical_mask = PhysicalV6Encoder.legal_mask(state)
    execution_mask = physical_mask.copy()
    removable = np.flatnonzero(execution_mask > 0)[-1]
    execution_mask[removable] = 0
    probabilities = strategy(_policy(), state, execution_mask)
    assert probabilities[removable] == 0
    assert np.isclose(probabilities.sum(), 1.0)
    for seed in range(32):
        _, metadata = decide(
            _policy(), state, np.random.default_rng(seed), execution_mask
        )
        assert execution_mask[metadata["selected_action_slot"]] > 0
