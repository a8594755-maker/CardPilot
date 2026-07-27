#!/usr/bin/env python3
"""Focused deterministic tests for the offline H3 v5.5 bridge audit."""

from __future__ import annotations

from copy import deepcopy

from alpha_holdem.v5_h3_v55_bridge import FIXTURES, _teacher_config, build_report, replay_fixture


def main() -> int:
    first = build_report()
    second = build_report()
    first_stable = deepcopy(first)
    second_stable = deepcopy(second)
    first_stable.pop("checked_at")
    second_stable.pop("checked_at")
    assert first_stable == second_stable

    assert first["overall"] == "PHASE1_FAIL_CLOSED_PATH1_SRP_ENTRY_UNREACHABLE"
    reachability = first["preflop_reachability"]
    assert reachability["path1_entry_reachable"] is False
    assert reachability["exact_path1_entry_paths"] == 0
    assert reachability["states_visited"] > 0
    assert first["checks"]["teacher_action_slots_supported_by_deployment_masks"] == "PASS"

    fixtures = first["fixtures"]
    assert len(fixtures) == 6
    assert any(row["deployment_only_slots"] for row in fixtures)
    for row in fixtures:
        assert row["unsupported_teacher_slots"] == []
        obs = row["observation"]
        assert obs["card_info_shape"] == [6, 4, 13]
        assert obs["action_info_shape"] == [25, 4, 5]
        assert obs["legal_mask_shape"] == [9]
        assert len(obs["card_info_sha256"]) == 64
        assert len(obs["action_info_sha256"]) == 64

    transition_fixture = next(row for row in FIXTURES if row.name == "turn_root_after_flop_raise_call")
    transition_state = replay_fixture(
        _teacher_config(), transition_fixture, cfr_raise_count_contract=True
    )
    assert transition_state.raise_count == 0
    assert len(transition_state.legal_actions()) == 5

    print("PASS 17/17 H3 v55 bridge deterministic/fail-closed/street-reset assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
