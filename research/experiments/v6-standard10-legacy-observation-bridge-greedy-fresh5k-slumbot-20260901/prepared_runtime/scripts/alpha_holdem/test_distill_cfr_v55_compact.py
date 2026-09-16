from __future__ import annotations

import json

import numpy as np

from alpha_holdem.distill_cfr_v55_compact import compact_row_to_numpy, load_tensors


def test_compact_row_encodes_native_cards_history_and_target():
    row = {
        "schema": "cfr.v55.compact.v1",
        "boardId": 2,
        "player": 0,
        "street": "TURN",
        "historyKey": "x1c/",
        "bucket": "29-22",
        "holeCards": [40, 44],
        "boardCards": [0, 1, 5, 9],
        "state": {
            "pot": 8.3,
            "stacks": [196.0, 195.7],
            "facingBet": 0.0,
            "currentPlayer": 0,
            "street": "TURN",
            "toCall": 0.0,
            "isFirstAction": True,
            "raiseCount": 0,
        },
        "events": [
            {
                "street": "FLOP",
                "player": 0,
                "actionType": "CHECK",
                "additionalAmount": None,
            },
            {
                "street": "FLOP",
                "player": 1,
                "actionType": "BET",
                "additionalAmount": 1.65,
            },
            {
                "street": "FLOP",
                "player": 0,
                "actionType": "CALL",
                "additionalAmount": 1.65,
            },
        ],
        "preflop": {"topology": "single_raised", "historyShape": "BC"},
        "legalMask": [0, 1, 1, 0, 1, 0, 0, 0, 1],
        "target": [0, 0.4, 0.2, 0, 0.3, 0, 0, 0, 0.1],
        "h": "fixture",
        "s": "TURN",
    }
    card, action, extra, mask, target, street = compact_row_to_numpy(row)

    assert card.shape == (6, 4, 13)
    assert action.shape == (25, 4, 5)
    assert extra.shape == (2,)
    assert mask.shape == target.shape == (9,)
    assert street == 2
    assert card[0].sum() == 2
    assert card[4].sum() == 4
    assert card[5].sum() == 6
    # Canonical SRP preflop raise/call plus three source flop events.
    assert action[0, 1, 4] == 1
    assert action[1, 1, 2] == 1
    assert action[6, 1, 1] == 1
    assert action[7, 1, 3] == 1
    assert action[8, 1, 2] == 1
    assert action[24, 0, 0] == 1
    np.testing.assert_allclose(extra, [0.98, 0.9785])
    np.testing.assert_allclose(target.sum(), 1.0)
    assert np.all(target[mask == 0] == 0)


def test_three_bet_rows_encode_bbc_before_postflop_actions():
    row = {
        "schema": "cfr.v55.compact.v1",
        "boardId": 0,
        "player": 1,
        "street": "FLOP",
        "historyKey": "x",
        "bucket": "0-0",
        "holeCards": [48, 49],
        "boardCards": [0, 5, 10],
        "state": {
            "pot": 17.5,
            "stacks": [191.25, 191.25],
            "currentPlayer": 1,
        },
        "events": [{
            "street": "FLOP",
            "player": 0,
            "actionType": "CHECK",
            "additionalAmount": None,
        }],
        "preflop": {"topology": "three_bet", "historyShape": "BBC"},
        "legalMask": [0, 1, 0, 1, 1, 1, 1, 1, 1],
        "target": [0, 1, 0, 0, 0, 0, 0, 0, 0],
    }

    _, action, _, _, _, _ = compact_row_to_numpy(row, obs_version="v4")

    assert action[0, 1, 4] == 1  # BTN opens to 2.5bb.
    assert action[1, 1, 4] == 1  # BB 3-bets to 8.75bb.
    assert action[2, 1, 2] == 1  # BTN calls and closes preflop.
    assert action[6, 1, 1] == 1  # First flop action starts in flop plane.
    np.testing.assert_allclose(action[0, 2, 0], 2.5 / 17.5 / 2.0)
    np.testing.assert_allclose(action[1, 2, 0], 8.75 / 17.5 / 2.0)


def test_loader_keeps_teacher_mask_but_expands_source_kl_mask(tmp_path):
    row = {
        "schema": "cfr.v55.compact.v1",
        "boardId": 0,
        "player": 0,
        "street": "FLOP",
        "historyKey": "x1",
        "bucket": "0-0",
        "holeCards": [48, 49],
        "boardCards": [0, 5, 10],
        "state": {
            "pot": 6.65,
            "stacks": [197.5, 195.85],
            "streetCommitted": [0.0, 1.65],
            "facingBet": 1.65,
            "currentPlayer": 0,
            "street": "FLOP",
            "toCall": 1.65,
            "isFirstAction": False,
            "raiseCount": 1,
        },
        "events": [
            {"street": "FLOP", "player": 0, "actionType": "CHECK", "additionalAmount": None},
            {"street": "FLOP", "player": 1, "actionType": "BET", "additionalAmount": 1.65},
        ],
        "preflop": {"topology": "single_raised", "historyShape": "BC"},
        "legalMask": [1, 1, 0, 0, 0, 0, 0, 0, 0],
        "target": [0.25, 0.75, 0, 0, 0, 0, 0, 0, 0],
    }
    path = tmp_path / "flop_0000.jsonl"
    path.write_text(json.dumps(row) + "\n", encoding="utf-8")

    tensors = load_tensors([path], 0, "v4")

    teacher_mask = tensors[3][0].numpy()
    deployment_mask = tensors[4][0].numpy()
    np.testing.assert_array_equal(teacher_mask, row["legalMask"])
    assert deployment_mask[0] == 1
    assert deployment_mask[1] == 1
    assert deployment_mask[2:].sum() > 0
