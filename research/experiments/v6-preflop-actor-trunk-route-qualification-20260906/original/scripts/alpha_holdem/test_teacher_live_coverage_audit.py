from __future__ import annotations

from alpha_holdem.teacher_live_coverage_audit import (
    action_shape,
    dump_signature,
    preflop_topology,
    teacher_signature,
)


def test_action_shape_and_topology():
    assert action_shape("b200c/xb300c/") == ("BC", "KBC", "")
    assert preflop_topology("KC") == "limped_or_checked"
    assert preflop_topology("BC") == "single_raised"
    assert preflop_topology("BBC") == "three_bet"
    assert preflop_topology("BBBC") == "four_bet_plus"


def test_teacher_and_dump_fixed_srp_coarse_signature_match():
    teacher = {
        "street": "FLOP",
        "player": 0,
        "state": {
            "pot": 4.0,
            "stacks": [198.0, 198.0],
            "toCall": 0.0,
            "raiseCount": 0,
        },
        "events": [],
        "legalMask": [0, 1, 1, 1, 1, 1, 1, 1, 1],
    }
    live = {
        "street": 1,
        "client_pos": 0,
        "action_str_before": "b200c/",
        "pot_before": 400,
        "to_call": 0,
        "stack_remaining": 19800,
        "policy_legal_mask": [0, 1, 1, 1, 1, 1, 1, 1, 1],
    }
    teacher_sig = teacher_signature(teacher)
    live_sig = dump_signature(live)
    for key in (
        "street",
        "position",
        "topology",
        "facing_bet",
        "raise_count",
        "legal_mask",
        "history",
        "current_depth",
        "pot_bucket",
        "spr_bucket",
    ):
        assert teacher_sig[key] == live_sig[key]


def test_dump_three_bet_is_outside_fixed_srp_topology():
    live = {
        "street": 1,
        "client_pos": 1,
        "action_str_before": "b250b900c/",
        "pot_before": 1850,
        "to_call": 0,
        "stack_remaining": 19100,
        "policy_legal_mask": [0, 1, 1, 1, 1, 1, 1, 1, 1],
    }
    signature = dump_signature(live)
    assert signature["position"] == "SB"
    assert signature["topology"] == "three_bet"
    assert signature["history"] == "BBC/"


def test_compact_row_can_declare_three_bet_preflop_context():
    row = {
        "street": "FLOP",
        "player": 0,
        "state": {
            "pot": 17.5,
            "stacks": [191.25, 191.25],
            "toCall": 0,
            "raiseCount": 0,
        },
        "events": [],
        "preflop": {"topology": "three_bet", "historyShape": "BBC"},
        "legalMask": [0, 1, 1, 1, 1, 1, 1, 1, 1],
    }
    signature = teacher_signature(row)
    assert signature["topology"] == "three_bet"
    assert signature["history"] == "BBC/"
