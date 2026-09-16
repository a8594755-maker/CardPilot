from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))

from alpha_holdem.environment_v55 import HUNLEnvironment
from scripts.alpha_holdem.train_v5 import (
    exp003_mirrored_deck_from_env,
    exp003_reset_env_with_deck,
    fixed_training_deck,
)


def make_env() -> HUNLEnvironment:
    return HUNLEnvironment(
        starting_stack=200.0,
        action_history_style='v4',
        raise_action_mapping='preflop_pot_fraction_v2',
    )


def test_mirrored_deck_swaps_only_private_cards():
    env = make_env()
    deck = fixed_training_deck(2026085200, 0, 17)
    exp003_reset_env_with_deck(env, deck)

    mirrored = exp003_mirrored_deck_from_env(env)

    assert mirrored[:2] == deck[2:4]
    assert mirrored[2:4] == deck[:2]
    assert mirrored[4:] == deck[4:]
    assert sorted(mirrored) == list(range(52))


def test_mirrored_reset_materializes_swapped_holes_and_same_future_deck():
    env = make_env()
    deck = fixed_training_deck(2026085200, 0, 23)
    exp003_reset_env_with_deck(env, deck)
    original_holes = list(env.state.hole_cards)
    mirrored = exp003_mirrored_deck_from_env(env)

    observation = exp003_reset_env_with_deck(env, mirrored)

    assert env.state.hole_cards == [original_holes[1], original_holes[0]]
    assert env.state.deck[4:] == deck[4:]
    assert env.state.board == []
    assert observation['player'] == env.state.current_player


def test_mirrored_reset_is_deterministic_for_registered_deck():
    env = make_env()
    deck = fixed_training_deck(2026085200, 0, 31)
    first = exp003_reset_env_with_deck(env, deck)
    first_holes = list(env.state.hole_cards)
    first_cards = first['card_info'].copy()

    second = exp003_reset_env_with_deck(env, deck)

    assert env.state.hole_cards == first_holes
    assert (second['card_info'] == first_cards).all()


def test_mirrored_deck_skips_missing_or_short_state():
    assert exp003_mirrored_deck_from_env(SimpleNamespace(state=None)) is None
    assert exp003_mirrored_deck_from_env(
        SimpleNamespace(state=SimpleNamespace(deck=[0, 1, 2]))
    ) is None
