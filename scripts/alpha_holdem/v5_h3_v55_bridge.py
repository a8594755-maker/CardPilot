#!/usr/bin/env python3
"""Fail-closed CFR SRP -> AlphaHoldem v5.5 observation bridge audit.

This is an offline H3 engineering tool.  It does not train or evaluate a policy.
It reconstructs identical realised postflop histories under two contracts:

* the Path-1 teacher sizing/cap contract; and
* the actual v5.5 deployment sizing/cap contract.

The 200bb Path-1 solve starts at a 5bb pot with 197.5bb behind.  To preserve the
full-game v5.5 stack normalisation and action-history tensor, the bridge records
the implied BTN 2.5bb open / BB call as explicit synthetic provenance.  The audit
separately proves whether that entry state is reachable through the actual v5.5
preflop action grid; it must never silently treat a synthetic state as reachable.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

import numpy as np

from alpha_holdem.environment_v55 import (
    RAISE_CAP_UNLIMITED,
    build_action_table,
    encode_action_history,
    encode_cards,
    encode_extra,
)
from deep_cfr.game_state import (
    Action,
    ActionType,
    BetSizeConfig,
    EXPANDED_BET_SIZES_WITH_PREFLOP,
    GameConfig,
    HUNLGameState,
    Street,
)


PATH1_SIZES = BetSizeConfig(
    preflop=[],
    flop=[0.33, 0.67, 1.0],
    turn=[0.5, 0.75, 1.25],
    river=[0.5, 1.0, 1.5],
)

REPLAY_CONTRACT_REVISION = "path1_cfr_raise_count_street_reset_v2"


@dataclass(frozen=True)
class Fixture:
    name: str
    history_key: str
    player: int
    hero_hole: tuple[int, int]
    board: tuple[int, int, int, int, int]


FIXTURES = (
    Fixture("flop_root", "", 0, (20, 25), (0, 5, 10, 15, 30)),
    Fixture("flop_facing_bet", "1", 1, (21, 26), (1, 6, 11, 16, 31)),
    Fixture("flop_after_raise_cap", "12", 0, (22, 27), (2, 7, 12, 17, 32)),
    Fixture("turn_root", "xx/", 0, (23, 28), (3, 8, 13, 18, 33)),
    Fixture("turn_root_after_flop_raise_call", "x12c/", 0, (22, 29), (4, 9, 14, 19, 34)),
    Fixture("river_root", "xx/xx/", 0, (24, 29), (4, 9, 14, 19, 34)),
)


def _teacher_config() -> GameConfig:
    return GameConfig(
        starting_pot=1.5,
        effective_stack=200.0,
        bet_sizes=PATH1_SIZES,
        raise_cap_per_street=1,
        raise_cap_preflop=4,
        include_preflop=True,
    )


def _deployment_config() -> GameConfig:
    return GameConfig(
        starting_pot=1.5,
        effective_stack=200.0,
        bet_sizes=EXPANDED_BET_SIZES_WITH_PREFLOP,
        raise_cap_per_street=RAISE_CAP_UNLIMITED,
        raise_cap_preflop=4,
        include_preflop=True,
    )


def _base_synthetic_srp_state(config: GameConfig, fixture: Fixture) -> HUNLGameState:
    used = set(fixture.board) | set(fixture.hero_hole)
    opponent_hole = tuple(card for card in range(52) if card not in used)[:2]
    used.update(opponent_hole)

    state = HUNLGameState(config)
    state.pot = 5.0
    state.stacks = [197.5, 197.5]
    state.street = Street.FLOP
    state.street_committed = [0.0, 0.0]
    state.current_player = 0
    state.actions_history = [
        (1, Action(ActionType.RAISE, 2.5)),
        (0, Action(ActionType.CALL)),
    ]
    state.raise_count = 0
    state.last_bet_size = 0.0
    state.num_actions_this_street = 0
    state.is_done = False
    state.folded_player = -1
    holes = [opponent_hole, opponent_hole]
    holes[fixture.player] = fixture.hero_hole
    holes[1 - fixture.player] = opponent_hole
    state.hole_cards = holes
    state.board = list(fixture.board[:3])

    future = list(fixture.board[3:])
    remaining = [card for card in range(52) if card not in used]
    state.deck = remaining + list(reversed(future))
    return state


def _fraction(config: GameConfig, street: Street, index: int) -> float:
    sizes = config.bet_sizes.for_street(street)
    if index < 0 or index >= len(sizes):
        raise ValueError(f"size index {index} unavailable on {street.name}")
    return sizes[index]


def _realised_action(state: HUNLGameState, char: str, sizing_config: GameConfig) -> Action:
    player = state.current_player
    committed = state.street_committed[player]
    opponent_committed = state.street_committed[1 - player]
    to_call = max(0.0, opponent_committed - committed)
    if char == "x":
        return Action(ActionType.CHECK)
    if char == "c":
        return Action(ActionType.CALL)
    if char == "f":
        return Action(ActionType.FOLD)
    if char == "A":
        return Action(ActionType.ALLIN, committed + state.stacks[player])
    if char < "1" or char > "9":
        raise ValueError(f"unsupported history character: {char!r}")

    fraction = _fraction(sizing_config, state.street, int(char) - 1)
    if to_call <= 0:
        additional = min(round(state.pot * fraction, 2), state.stacks[player])
        return Action(ActionType.BET, committed + additional)
    pot_after_call = state.pot + to_call
    additional = min(to_call + round(pot_after_call * fraction, 2), state.stacks[player])
    return Action(ActionType.RAISE, committed + additional)


def replay_fixture(
    config: GameConfig,
    fixture: Fixture,
    *,
    cfr_raise_count_contract: bool = False,
) -> HUNLGameState:
    state = _base_synthetic_srp_state(config, fixture)
    expected_street = Street.FLOP
    cfr_raise_count = 0
    for char in fixture.history_key:
        if char == "/":
            expected_street = Street(int(expected_street) + 1)
            cfr_raise_count = 0
            if state.street != expected_street:
                raise ValueError(
                    f"history delimiter expected {expected_street.name}, got {state.street.name}"
                )
            continue
        committed = state.street_committed[state.current_player]
        opponent_committed = state.street_committed[1 - state.current_player]
        was_facing_bet = opponent_committed > committed
        action = _realised_action(state, char, _teacher_config())
        street_before_action = state.street
        state = state.apply(action)
        # Path-1's tree counts raises over an existing bet; its opening BET does
        # not consume raiseCapPerStreet.  HUNLGameState counts BET as well, so a
        # teacher-mask reconstruction must restore the source contract here.
        if was_facing_bet and action.type in (
            ActionType.RAISE,
            ActionType.ALLIN,
        ):
            cfr_raise_count += 1
        # A call can advance the street inside apply().  The Path-1 raise cap is
        # per street, so never restore the previous street's raise count onto
        # the newly-created street state.
        if state.street != street_before_action:
            cfr_raise_count = 0
        if cfr_raise_count_contract:
            state.raise_count = cfr_raise_count
        if state.is_done:
            raise ValueError(f"fixture {fixture.name} became terminal at {char!r}")

    if state.current_player != fixture.player:
        raise ValueError(
            f"fixture {fixture.name} player mismatch: {state.current_player} != {fixture.player}"
        )
    visible = 2 + int(state.street)
    if state.board != list(fixture.board[:visible]):
        raise ValueError(f"fixture {fixture.name} board reconstruction mismatch")
    return state


def _array_sha(array: np.ndarray) -> str:
    return hashlib.sha256(np.ascontiguousarray(array).tobytes()).hexdigest()


def _mask_slots(mask: np.ndarray) -> list[int]:
    return np.flatnonzero(mask > 0).astype(int).tolist()


def _state_identity(state: HUNLGameState) -> dict:
    return {
        "pot": state.pot,
        "stacks": state.stacks,
        "street": state.street.name,
        "current_player": state.current_player,
        "street_committed": state.street_committed,
        "raise_count": state.raise_count,
        "board": state.board,
    }


def audit_fixture(fixture: Fixture) -> dict:
    teacher = replay_fixture(
        _teacher_config(), fixture, cfr_raise_count_contract=True
    )
    deployment = replay_fixture(_deployment_config(), fixture)
    teacher_identity = _state_identity(teacher)
    deployment_identity = _state_identity(deployment)
    teacher_core = {key: value for key, value in teacher_identity.items() if key != "raise_count"}
    deployment_core = {
        key: value for key, value in deployment_identity.items() if key != "raise_count"
    }
    if teacher_core != deployment_core:
        raise ValueError(f"fixture {fixture.name} realised state identity mismatch")

    teacher_mask, _ = build_action_table(teacher)
    deployment_mask, _ = build_action_table(deployment)
    card = encode_cards(deployment, fixture.player)
    action = encode_action_history(deployment, fixture.player)
    extra = encode_extra(deployment, fixture.player)
    unsupported_teacher_slots = [
        slot for slot in _mask_slots(teacher_mask) if deployment_mask[slot] <= 0
    ]
    deployment_only_slots = [
        slot for slot in _mask_slots(deployment_mask) if teacher_mask[slot] <= 0
    ]
    return {
        "name": fixture.name,
        "history_key": fixture.history_key,
        "state": deployment_identity,
        "teacher_raise_count": teacher.raise_count,
        "deployment_v55_raise_count": deployment.raise_count,
        "teacher_mask_slots": _mask_slots(teacher_mask),
        "deployment_v55_mask_slots": _mask_slots(deployment_mask),
        "unsupported_teacher_slots": unsupported_teacher_slots,
        "deployment_only_slots": deployment_only_slots,
        "observation": {
            "card_info_shape": list(card.shape),
            "action_info_shape": list(action.shape),
            "extra_info": extra.astype(float).tolist(),
            "legal_mask_shape": list(deployment_mask.shape),
            "card_info_sha256": _array_sha(card),
            "action_info_sha256": _array_sha(action),
            "extra_info_sha256": _array_sha(extra),
            "legal_mask_sha256": _array_sha(deployment_mask),
        },
    }


def enumerate_reachable_preflop_entry() -> dict:
    """Enumerate actual v5.5 preflop leaves and search for Path-1's exact entry."""
    initial = HUNLGameState(_deployment_config())
    stack = [initial]
    seen: set[tuple] = set()
    leaves: list[dict] = []
    exact_paths = 0

    while stack:
        state = stack.pop()
        signature = (
            int(state.street),
            round(state.pot, 8),
            tuple(round(value, 8) for value in state.stacks),
            tuple(round(value, 8) for value in state.street_committed),
            state.current_player,
            state.raise_count,
            state.num_actions_this_street,
        )
        if signature in seen:
            continue
        seen.add(signature)
        if state.is_done:
            continue
        if state.street != Street.PREFLOP:
            leaf = {"pot": state.pot, "stacks": state.stacks}
            leaves.append(leaf)
            if (
                abs(state.pot - 5.0) < 1e-9
                and all(abs(value - 197.5) < 1e-9 for value in state.stacks)
            ):
                exact_paths += 1
            continue
        for action in state.legal_actions():
            stack.append(state.apply(action))

    unique_leaves = {
        (round(row["pot"], 8), tuple(round(value, 8) for value in row["stacks"]))
        for row in leaves
    }
    nearest = sorted(
        (
            {
                "pot": pot,
                "stacks": list(stacks),
                "l1_distance": abs(pot - 5.0) + sum(abs(value - 197.5) for value in stacks),
            }
            for pot, stacks in unique_leaves
        ),
        key=lambda row: (row["l1_distance"], row["pot"], row["stacks"]),
    )[:5]
    return {
        "states_visited": len(seen),
        "unique_nonterminal_flop_entries": len(unique_leaves),
        "exact_path1_entry_paths": exact_paths,
        "path1_entry_reachable": exact_paths > 0,
        "nearest_entries": nearest,
    }


def build_report() -> dict:
    reachability = enumerate_reachable_preflop_entry()
    fixtures = [audit_fixture(fixture) for fixture in FIXTURES]
    state_roundtrip_pass = all(not row["unsupported_teacher_slots"] for row in fixtures)
    return {
        "schema_version": "v5.hybrid.h3.v55_bridge.phase1.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "scope": "OFFLINE_ENGINEERING_PREREQUISITE_ONLY",
        "overall": (
            "PHASE1_FAIL_CLOSED_PATH1_SRP_ENTRY_UNREACHABLE"
            if not reachability["path1_entry_reachable"]
            else "PHASE1_PASS"
        ),
        "contracts": {
            "path1": {
                "starting_pot": 5.0,
                "remaining_stack_each": 197.5,
                "implied_preflop": "BTN open to 2.5bb, BB call",
                "postflop_sizes": {
                    "flop": PATH1_SIZES.flop,
                    "turn": PATH1_SIZES.turn,
                    "river": PATH1_SIZES.river,
                },
                "raise_cap_per_street": 1,
            },
            "deployment_v55": {
                "preflop_sizes": EXPANDED_BET_SIZES_WITH_PREFLOP.preflop,
                "postflop_sizes": EXPANDED_BET_SIZES_WITH_PREFLOP.flop,
                "raise_cap_per_street": RAISE_CAP_UNLIMITED,
            },
        },
        "checks": {
            "deterministic_synthetic_state_observation_construction": "PASS",
            "realised_teacher_to_deployment_state_identity": "PASS",
            "teacher_action_slots_supported_by_deployment_masks": (
                "PASS" if state_roundtrip_pass else "FAIL"
            ),
            "actual_v55_preflop_reachability_of_path1_entry": (
                "PASS" if reachability["path1_entry_reachable"] else "FAIL"
            ),
            "synthetic_preflop_provenance_required": not reachability["path1_entry_reachable"],
            "corrected_successor_asset_validation": "PENDING_FIRST_QA_BOARD",
        },
        "preflop_reachability": reachability,
        "fixtures": fixtures,
        "decision": {
            "h3_preregistration_authorized": False,
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
            "required_next_evidence": [
                "freeze an explicit domain-adapter contract for synthetic SRP observations or select only truly reachable v55 states",
                "validate the adapter against corrected QA-PASS successor boards",
                "keep critic supervision forbidden because Path-1 exports no registered value target",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = build_report()
    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0 if report["overall"].startswith("PHASE1_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
