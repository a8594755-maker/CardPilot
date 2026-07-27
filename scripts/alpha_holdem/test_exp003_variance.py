#!/usr/bin/env python3
"""Small offline checks for the EXP-003 trainer candidate."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from alpha_holdem.environment_v55 import HUNLEnvironmentV55
from alpha_holdem.train_v5_exp003 import (
    exp003_allin_ev_reward,
    exp003_exact_showdown_counts,
    exp003_mirrored_deck_from_env,
    exp003_reset_env_with_deck,
)
from deep_cfr.game_state import GameConfig, HUNLGameState, Street
from deep_cfr.hand_eval import card_from_str


def test_mirrored_deck_preserves_board_order() -> None:
    env = HUNLEnvironmentV55(starting_stack=200.0)
    env.reset()
    original = env.state.deck.copy()

    mirrored = exp003_mirrored_deck_from_env(env)
    assert mirrored is not None
    assert mirrored[:4] == [original[2], original[3], original[0], original[1]]
    assert mirrored[4:] == original[4:]

    obs = exp003_reset_env_with_deck(env, mirrored)
    assert env.state.hole_cards[0] == (original[2], original[3])
    assert env.state.hole_cards[1] == (original[0], original[1])
    assert env.state.deck[-5:] == original[-5:]
    assert obs['player'] == 1


def test_allin_ev_turn_enumeration_is_zero_sum() -> None:
    hole0 = (card_from_str('As'), card_from_str('Ah'))
    hole1 = (card_from_str('Ks'), card_from_str('Kh'))
    board4 = [
        card_from_str('2c'),
        card_from_str('7d'),
        card_from_str('Jc'),
        card_from_str('3h'),
    ]
    final_board = board4 + [card_from_str('4d')]

    state = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(hole0, hole1, board4)
    state.board = final_board
    state.stacks = [0.0, 0.0]
    state.is_done = True
    state.folded_player = -1
    state.street = Street.SHOWDOWN

    ev0, runouts0, skipped0 = exp003_allin_ev_reward(state, 0, tuple(board4))
    ev1, runouts1, skipped1 = exp003_allin_ev_reward(state, 1, tuple(board4))
    counts = exp003_exact_showdown_counts(tuple(sorted(hole0)), tuple(sorted(hole1)), tuple(sorted(board4)))

    assert not skipped0
    assert not skipped1
    assert runouts0 == runouts1 == counts[3] == 44
    assert abs(ev0 + ev1) < 1e-9
    assert -200.0 <= ev0 <= 200.0
    assert -200.0 <= ev1 <= 200.0

    capped = exp003_allin_ev_reward(state, 0, tuple(board4), max_runouts=10)
    assert capped is not None
    _ev_cap, runouts_cap, skipped_cap = capped
    assert not skipped_cap
    assert runouts_cap == 10


def test_allin_ev_preflop_bounded_is_deterministic_zero_sum() -> None:
    hole0 = (card_from_str('As'), card_from_str('Ah'))
    hole1 = (card_from_str('Ks'), card_from_str('Kh'))
    final_board = [
        card_from_str('2c'),
        card_from_str('7d'),
        card_from_str('Jc'),
        card_from_str('3h'),
        card_from_str('4d'),
    ]

    state = HUNLGameState(GameConfig.full_200bb()).deal_with_cards(hole0, hole1, [])
    state.board = final_board
    state.stacks = [0.0, 0.0]
    state.is_done = True
    state.folded_player = -1
    state.street = Street.SHOWDOWN

    ev0_a, runouts0_a, skipped0_a = exp003_allin_ev_reward(state, 0, tuple(), max_runouts=100)
    ev0_b, runouts0_b, skipped0_b = exp003_allin_ev_reward(state, 0, tuple(), max_runouts=100)
    ev1, runouts1, skipped1 = exp003_allin_ev_reward(state, 1, tuple(), max_runouts=100)

    assert not skipped0_a
    assert not skipped0_b
    assert not skipped1
    assert runouts0_a == runouts0_b == runouts1 == 100
    assert ev0_a == ev0_b
    assert abs(ev0_a + ev1) < 1e-9


def main() -> None:
    test_mirrored_deck_preserves_board_order()
    test_allin_ev_turn_enumeration_is_zero_sum()
    test_allin_ev_preflop_bounded_is_deterministic_zero_sum()
    print('PASS: EXP-003 mirror deck and all-in EV smoke checks')


if __name__ == '__main__':
    main()
