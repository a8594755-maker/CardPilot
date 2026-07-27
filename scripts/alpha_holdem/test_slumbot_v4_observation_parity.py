from __future__ import annotations

import numpy as np

from alpha_holdem.environment import encode_action_history as encode_training_v4
from alpha_holdem.offline_slumbot_awr import reconstruct
from alpha_holdem.play_slumbot import (
    encode_action_history as encode_slumbot,
    parse_action,
)
from deep_cfr.game_state import Action, ActionType, GameConfig, HUNLGameState


def test_slumbot_v4_history_matches_training_encoder_for_srp_root():
    state = HUNLGameState(GameConfig.full_200bb()).deal_new_hand()
    state = state.apply(Action(ActionType.RAISE, 2.5))
    state = state.apply(Action(ActionType.CALL))
    assert int(state.current_player) == 0
    assert float(state.pot) == 5.0

    training = encode_training_v4(state, player=0)
    parsed = parse_action("b125c/")
    deployment = encode_slumbot(
        parsed,
        client_pos=0,
        current_pos=int(parsed["pos"]),
        obs_version="v4",
    )
    np.testing.assert_allclose(deployment, training, atol=0.0, rtol=0.0)


def test_offline_teacher_inherits_preflop_v2_action_slots():
    record = {
        "hand_idx": 0,
        "move_idx": 0,
        "who": "opp",
        "client_pos": 0,
        "opp_pos": 1,
        "action_str_before": "",
        "street": 0,
        "board": [],
        "opp_hole": ["As", "8h"],
        "hero_hole": ["9h", "4c"],
        "action_move": "b",
        "action_amount": 200,
        "winnings_hero": -100,
    }
    corrected = reconstruct(
        record,
        "v4",
        actor="opp",
        raise_action_mapping="preflop_pot_fraction_v2",
    )
    legacy = reconstruct(
        record,
        "v4",
        actor="opp",
        raise_action_mapping="legacy_total_over_pot",
    )
    assert corrected is not None and corrected["selected"] == 3
    assert corrected["return_bb"] == 1.0
    assert legacy is not None and legacy["selected"] == 7
