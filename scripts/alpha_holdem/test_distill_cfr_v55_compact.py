from __future__ import annotations

import numpy as np

from alpha_holdem.distill_cfr_v55_compact import compact_row_to_numpy


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
