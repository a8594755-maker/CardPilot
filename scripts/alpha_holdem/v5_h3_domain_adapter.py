#!/usr/bin/env python3
"""Implement H3-DOMAIN-ADAPTER-001 for identity-bound Path-1 source rows.

Input is JSONL using schema ``path1.v55_bridge_source.v1``.  Output is sharded
NPZ actor-only supervision plus a provenance JSONL and manifest.  Any malformed
row, source identity mismatch, unsupported target mass, card conflict, or missing
OOD label fails the complete conversion; partial files retain a ``.partial`` name.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import numpy as np

from alpha_holdem.environment_v55 import (
    RAISE_FRACTIONS,
    build_action_table,
    encode_action_history,
    encode_cards,
    encode_extra,
)
from alpha_holdem.v5_h3_v55_bridge import (
    Fixture,
    _deployment_config,
)
from deep_cfr.game_state import Action, ActionType, HUNLGameState, Street


SOURCE_SCHEMA = "path1.v55_bridge_source.v2"
OUTPUT_SCHEMA = "v5.hybrid.h3.domain_adapter.actor_row.v1"
OOD_LABEL = "SYNTHETIC_PATH1_SRP_ENTRY_OOD_NOT_DEPLOYMENT_REACHABLE"
LOCK_SHA256 = "fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e"
FULL_SCOPE = "FULL_BOARD_CORPUS"
SMOKE_SCOPE = "SMOKE_PREFIX_ONLY_FORBIDDEN_TRAINING"
MAX_ROUNDING_RESIDUAL = 0.0050000001
MAX_ACTION_ERROR_OVER_SOURCE_POT = 0.5


@dataclass
class AdaptedRow:
    card_info: np.ndarray
    action_info: np.ndarray
    extra_info: np.ndarray
    legal_mask: np.ndarray
    actor_target: np.ndarray
    metadata: dict


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _pad_board(visible_board: list[int], used: set[int]) -> tuple[int, int, int, int, int]:
    if len(visible_board) not in (3, 4, 5):
        raise ValueError("board_cards must contain exactly 3, 4, or 5 cards")
    full = list(visible_board)
    for card in range(52):
        if len(full) == 5:
            break
        if card not in used and card not in full:
            full.append(card)
    return tuple(full)  # type: ignore[return-value]


def _fixture_from_row(row: dict) -> Fixture:
    player = int(row["player"])
    if player not in (0, 1):
        raise ValueError("player must be 0 or 1")
    hole = [int(card) for card in row["hole_cards"]]
    board = [int(card) for card in row["board_cards"]]
    if len(hole) != 2 or len(set(hole)) != 2:
        raise ValueError("hole_cards must contain two distinct cards")
    if any(card < 0 or card >= 52 for card in hole + board):
        raise ValueError("card outside 0..51")
    if len(set(hole + board)) != len(hole + board):
        raise ValueError("hole/board card conflict")
    full_board = _pad_board(board, set(hole + board))
    return Fixture(
        name=str(row["info_set_key"]),
        history_key=str(row["history_key"]),
        player=player,
        hero_hole=(hole[0], hole[1]),
        board=full_board,
    )


def _snapshot_state_from_row(row: dict, fixture: Fixture) -> tuple[HUNLGameState, dict]:
    snapshot = row.get("path1_state_snapshot")
    events = row.get("path1_history_events")
    if not isinstance(snapshot, dict) or not isinstance(events, list):
        raise ValueError("path1_snapshot_or_history_missing")
    street_name = str(snapshot.get("street"))
    street_by_name = {"FLOP": Street.FLOP, "TURN": Street.TURN, "RIVER": Street.RIVER}
    if street_name not in street_by_name:
        raise ValueError("path1_snapshot_street_invalid")
    pot = float(snapshot["pot"])
    stacks = [float(value) for value in snapshot["stacks"]]
    facing_bet = float(snapshot["facingBet"])
    current_player = int(snapshot["currentPlayer"])
    raise_count = int(snapshot["raiseCount"])
    if (
        not np.isfinite([pot, *stacks, facing_bet]).all()
        or pot <= 0
        or len(stacks) != 2
        or min(stacks) < 0
        or facing_bet < 0
        or current_player not in (0, 1)
        or current_player != fixture.player
        or raise_count < 0
    ):
        raise ValueError("path1_snapshot_numeric_or_player_invalid")

    street_order = {"FLOP": 1, "TURN": 2, "RIVER": 3}
    audit_pot = 5.0
    audit_stacks = [197.5, 197.5]
    audit_facing = 0.0
    audit_player = 0
    audit_street = "FLOP"
    audit_raise_count = 0
    audit_first_action = True
    for event in events:
        if not isinstance(event, dict):
            raise ValueError("path1_history_event_invalid")
        event_street = str(event.get("street"))
        if event_street not in street_order or street_order[event_street] < street_order[audit_street]:
            raise ValueError("path1_history_event_street_invalid")
        while street_order[audit_street] < street_order[event_street]:
            audit_street = "TURN" if audit_street == "FLOP" else "RIVER"
            audit_player = 0
            audit_facing = 0.0
            audit_raise_count = 0
            audit_first_action = True
        player = int(event.get("player", -1))
        if player != audit_player:
            raise ValueError("path1_history_event_player_sequence_mismatch")
        event_type = str(event.get("actionType"))
        amount_raw = event.get("additionalAmount")
        if event_type in {"CHECK", "FOLD"}:
            if amount_raw is not None:
                raise ValueError("path1_history_passive_amount_not_null")
            audit_player = 1 - audit_player
            audit_first_action = False
        elif event_type == "CALL":
            amount = float(amount_raw)
            expected_call = min(audit_facing, audit_stacks[player])
            if abs(amount - expected_call) > 1e-9:
                raise ValueError("path1_history_call_amount_mismatch")
            audit_stacks[player] -= amount
            audit_pot += amount
            audit_player = 1 - audit_player
            audit_facing = 0.0
            audit_first_action = False
        elif event_type in {"BET", "RAISE", "ALLIN"}:
            amount = float(amount_raw)
            if not np.isfinite(amount) or amount <= 0 or amount > audit_stacks[player] + 1e-9:
                raise ValueError("path1_history_sized_amount_invalid")
            was_facing = audit_facing > 0
            audit_stacks[player] -= amount
            audit_pot += amount
            audit_facing = amount
            if was_facing:
                audit_raise_count += 1
            audit_player = 1 - audit_player
            audit_first_action = False
        else:
            raise ValueError("path1_history_event_action_invalid")
    while street_order[audit_street] < street_order[street_name]:
        audit_street = "TURN" if audit_street == "FLOP" else "RIVER"
        audit_player = 0
        audit_facing = 0.0
        audit_raise_count = 0
        audit_first_action = True
    audited_snapshot = {
        "pot": audit_pot,
        "stacks": audit_stacks,
        "facingBet": audit_facing,
        "currentPlayer": audit_player,
        "street": audit_street,
        "raiseCount": audit_raise_count,
        "isFirstAction": audit_first_action,
    }
    expected_snapshot = {
        "pot": pot,
        "stacks": stacks,
        "facingBet": facing_bet,
        "currentPlayer": current_player,
        "street": street_name,
        "raiseCount": raise_count,
        "isFirstAction": bool(snapshot["isFirstAction"]),
    }
    for key in ("pot", "facingBet"):
        if abs(float(audited_snapshot[key]) - float(expected_snapshot[key])) > 1e-9:
            raise ValueError(f"path1_snapshot_event_replay_mismatch:{key}")
    if any(abs(a - b) > 1e-9 for a, b in zip(audited_snapshot["stacks"], expected_snapshot["stacks"], strict=True)):
        raise ValueError("path1_snapshot_event_replay_mismatch:stacks")
    for key in ("currentPlayer", "street", "raiseCount", "isFirstAction"):
        if audited_snapshot[key] != expected_snapshot[key]:
            raise ValueError(f"path1_snapshot_event_replay_mismatch:{key}")

    visible_board = [int(card) for card in row["board_cards"]]
    used = set(visible_board) | set(fixture.hero_hole)
    opponent_hole = tuple(card for card in range(52) if card not in used)[:2]
    used.update(opponent_hole)
    state = HUNLGameState(_deployment_config())
    state.pot = pot
    state.stacks = stacks
    state.street = street_by_name[street_name]
    state.current_player = current_player
    state.raise_count = raise_count
    state.street_committed = [0.0, 0.0]
    if facing_bet > 0:
        state.street_committed[1 - current_player] = facing_bet
    state.last_bet_size = facing_bet
    state.is_done = False
    state.folded_player = -1
    state.hole_cards = [opponent_hole, opponent_hole]
    state.hole_cards[fixture.player] = fixture.hero_hole
    state.hole_cards[1 - fixture.player] = opponent_hole
    state.board = visible_board
    state.deck = [card for card in range(52) if card not in used]
    state.actions_history = [
        (1, Action(ActionType.RAISE, 2.5)),
        (0, Action(ActionType.CALL)),
    ]
    action_type = {
        "CHECK": ActionType.CHECK,
        "CALL": ActionType.CALL,
        "FOLD": ActionType.FOLD,
        "BET": ActionType.BET,
        "RAISE": ActionType.RAISE,
        "ALLIN": ActionType.ALLIN,
    }
    current_street_events = 0
    for event in events:
        if not isinstance(event, dict) or event.get("actionType") not in action_type:
            raise ValueError("path1_history_event_invalid")
        event_street = str(event.get("street"))
        if event_street not in street_by_name:
            raise ValueError("path1_history_event_street_invalid")
        player = int(event["player"])
        if player not in (0, 1):
            raise ValueError("path1_history_event_player_invalid")
        amount_raw = event.get("additionalAmount")
        amount = 0.0 if amount_raw is None else float(amount_raw)
        if not np.isfinite(amount) or amount < 0:
            raise ValueError("path1_history_event_amount_invalid")
        state.actions_history.append((player, Action(action_type[event["actionType"]], amount)))
        if event_street == street_name:
            current_street_events += 1
    state.num_actions_this_street = current_street_events

    observed = {
        "pot": state.pot,
        "stacks": state.stacks,
        "street": state.street.name,
        "current_player": state.current_player,
        "raise_count": state.raise_count,
        "facing_bet": state.street_committed[1 - state.current_player] - state.street_committed[state.current_player],
    }
    expected = {
        "pot": pot,
        "stacks": stacks,
        "street": street_name,
        "current_player": current_player,
        "raise_count": raise_count,
        "facing_bet": facing_bet,
    }
    if observed != expected:
        raise ValueError(f"path1_snapshot_roundtrip_mismatch:{observed!r}!={expected!r}")
    return state, expected


def adapt_source_row(row: dict, *, expected_ordinal: int) -> AdaptedRow:
    if row.get("schema_version") != SOURCE_SCHEMA:
        raise ValueError("source_schema_mismatch")
    if row.get("bridge_design_lock_v3_sha256") != LOCK_SHA256:
        raise ValueError("bridge_design_lock_v3_identity_mismatch")
    bridge_scope = str(row.get("bridge_scope", ""))
    if bridge_scope not in (FULL_SCOPE, SMOKE_SCOPE):
        raise ValueError("bridge_scope_missing_or_invalid")
    source_file_sha256 = str(row.get("source_file_sha256", ""))
    if len(source_file_sha256) != 64 or any(char not in "0123456789abcdef" for char in source_file_sha256):
        raise ValueError("invalid_source_strategy_file_sha256")
    if int(row.get("source_row_ordinal", -1)) != expected_ordinal:
        raise ValueError("source_row_ordinal_mismatch")
    if row.get("path1_asset_classification") != "CORRECTED_LEGAL_ALLIN_QA_PASS":
        raise ValueError("source_board_not_corrected_qa_pass")
    if row.get("required_provenance_label") != OOD_LABEL:
        raise ValueError("missing_or_false_synthetic_ood_provenance")

    fixture = _fixture_from_row(row)
    deployment, snapshot_identity = _snapshot_state_from_row(row, fixture)
    source_actions = [str(action) for action in row["cfr_actions"]]
    probabilities = np.asarray(row["cfr_probabilities"], dtype=np.float64)
    if probabilities.shape != (len(source_actions),):
        raise ValueError("cfr_probability_length_mismatch")
    if not np.isfinite(probabilities).all() or (probabilities < 0).any():
        raise ValueError("invalid_cfr_probability")
    if abs(float(probabilities.sum()) - 1.0) > 1e-9:
        raise ValueError("cfr_probability_mass_mismatch")
    source_sum = float(row.get("source_probability_sum", float("nan")))
    residual = float(row.get("rounding_residual", float("nan")))
    residual_index = int(row.get("rounding_residual_action_index", -1))
    if not np.isfinite(source_sum) or not np.isfinite(residual):
        raise ValueError("missing_rounding_residual_provenance")
    if abs((1.0 - source_sum) - residual) > 1e-12:
        raise ValueError("rounding_residual_identity_mismatch")
    if abs(residual) > MAX_ROUNDING_RESIDUAL:
        raise ValueError("rounding_residual_out_of_contract")
    if residual_index < 0 or residual_index >= len(probabilities):
        raise ValueError("rounding_residual_action_index_invalid")
    raw_probabilities = probabilities.copy()
    raw_probabilities[residual_index] -= residual
    if (
        not np.isfinite(raw_probabilities).all()
        or (raw_probabilities < -1e-12).any()
        or (raw_probabilities > 1.0 + 1e-12).any()
        or abs(float(raw_probabilities.sum()) - source_sum) > 1e-12
    ):
        raise ValueError("rounding_residual_reconstruction_failed")
    expected_residual_index = int(np.argmax(raw_probabilities))
    if residual_index != expected_residual_index:
        raise ValueError("rounding_residual_tie_break_or_max_action_mismatch")

    descriptors = row.get("cfr_action_descriptors")
    if not isinstance(descriptors, list) or len(descriptors) != len(source_actions):
        raise ValueError("cfr_action_descriptors_missing_or_length_mismatch")
    nominal_slots: list[int] = []
    for action, descriptor in zip(source_actions, descriptors, strict=True):
        if not isinstance(descriptor, dict) or descriptor.get("source_action_name") != action:
            raise ValueError("cfr_action_descriptor_identity_mismatch")
        slot = int(descriptor["nominal_v55_slot"])
        nominal_slots.append(slot)
        if action == "fold" and slot != 0:
            raise ValueError("fold_slot_identity_mismatch")
        if action in ("check", "call") and slot != 1:
            raise ValueError("passive_slot_identity_mismatch")
        if action == "allin" and slot != 8:
            raise ValueError("allin_slot_identity_mismatch")
        if action.startswith(("bet_", "raise_")) and slot not in range(2, 8):
            raise ValueError("sized_action_slot_identity_mismatch")
        if not (
            action in {"fold", "check", "call", "allin"}
            or action.startswith("bet_")
            or action.startswith("raise_")
        ):
            raise ValueError("unsupported_cfr_action_name")

    nominal_target = np.zeros(9, dtype=np.float64)
    for slot, probability in zip(nominal_slots, probabilities, strict=True):
        nominal_target[slot] += float(probability)
    bridge_nominal_target = np.asarray(row.get("nominal_v55_actor_target"), dtype=np.float64)
    if bridge_nominal_target.shape != (9,) or not np.isfinite(bridge_nominal_target).all():
        raise ValueError("nominal_v55_actor_target_missing_or_invalid")
    if not np.allclose(nominal_target, bridge_nominal_target, rtol=0.0, atol=1e-12):
        raise ValueError("nominal_v55_actor_target_mapping_mismatch")

    legal_mask, action_table = build_action_table(deployment)
    target = np.zeros(9, dtype=np.float64)
    projections: list[dict] = []
    sized_mass = 0.0
    projection_mass = 0.0
    for action, descriptor, probability, nominal_slot in zip(
        source_actions, descriptors, probabilities, nominal_slots, strict=True
    ):
        final_slot: int
        if action == "fold":
            final_slot = 0
        elif action in ("check", "call"):
            final_slot = 1
        elif action == "allin":
            final_slot = 8
        else:
            source_amount = float(descriptor["exact_additional_amount"])
            source_fraction = float(descriptor["exact_amount_over_source_pot"])
            if not np.isfinite(source_amount) or source_amount <= 0 or not np.isfinite(source_fraction):
                raise ValueError("sized_source_amount_invalid")
            candidates = [
                (abs(float(action_table[slot].amount) - source_amount), slot, action_table[slot])
                for slot in range(2, 8)
                if legal_mask[slot] > 0
                and action_table[slot] is not None
                and action_table[slot].type in (ActionType.BET, ActionType.RAISE)
            ]
            if not candidates:
                raise ValueError("no_legal_nonallin_sized_candidate")
            amount_error, final_slot, actual_action = min(candidates, key=lambda item: (item[0], item[1]))
            error_over_pot = amount_error / max(float(snapshot_identity["pot"]), 1e-9)
            if error_over_pot > MAX_ACTION_ERROR_OVER_SOURCE_POT:
                raise ValueError(f"action_projection_error_exceeds_lock:{error_over_pot}")
            sized_mass += float(probability)
            projected = final_slot != nominal_slot
            if projected:
                projection_mass += float(probability)
            projections.append({
                "source_action": action,
                "source_amount": source_amount,
                "source_pot_fraction": source_fraction,
                "nominal_slot": nominal_slot,
                "actual_legal_slot": final_slot,
                "actual_action_amount": float(actual_action.amount),
                "absolute_amount_error_over_source_pot": error_over_pot,
                "probability_mass": float(probability),
                "projected": projected,
            })
        if legal_mask[final_slot] <= 0:
            raise ValueError(f"fixed_semantic_or_final_slot_illegal:{final_slot}")
        target[final_slot] += float(probability)

    unsupported_mass = float(target[legal_mask <= 0].sum())
    if unsupported_mass != 0.0:
        raise ValueError(f"unsupported_target_mass:{unsupported_mass}")
    if abs(float(target.sum()) - 1.0) > 1e-9:
        raise ValueError("adapted_target_mass_mismatch")

    player = fixture.player
    return AdaptedRow(
        card_info=encode_cards(deployment, player),
        action_info=encode_action_history(deployment, player),
        extra_info=encode_extra(deployment, player),
        legal_mask=legal_mask.astype(np.float32, copy=False),
        actor_target=target.astype(np.float32),
        metadata={
            "schema_version": OUTPUT_SCHEMA,
            "design_lock_sha256": LOCK_SHA256,
            "source_file_sha256": source_file_sha256,
            "source_row_ordinal": expected_ordinal,
            "board_id": int(row["board_id"]),
            "info_set_key": str(row["info_set_key"]),
            "bucket_identity": str(row["bucket_identity"]),
            "required_provenance_label": OOD_LABEL,
            "bridge_scope": bridge_scope,
            "training_eligible": bridge_scope == FULL_SCOPE,
            "source_probability_sum": source_sum,
            "rounding_residual": residual,
            "rounding_residual_action_index": residual_index,
            "deployment_reachable": False,
            "critic_target_present": False,
            "unsupported_target_mass": unsupported_mass,
            "path1_snapshot_identity": snapshot_identity,
            "nominal_v55_slots": nominal_slots,
            "projection_records": projections,
            "sized_probability_mass": sized_mass,
            "projection_probability_mass": projection_mass,
        },
    )


def iter_source(path: Path) -> Iterator[tuple[int, dict]]:
    with path.open("r", encoding="utf-8") as stream:
        for ordinal, line in enumerate(stream):
            if not line.strip():
                raise ValueError(f"blank_source_row:{ordinal}")
            try:
                yield ordinal, json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid_json_row:{ordinal}:{exc}") from exc


def _write_shard(out_dir: Path, index: int, rows: list[AdaptedRow]) -> dict:
    final = out_dir / f"actor_rows_{index:05d}.npz"
    partial = out_dir / f"actor_rows_{index:05d}.npz.partial"
    arrays = {
        "card_info": np.stack([row.card_info for row in rows]),
        "action_info": np.stack([row.action_info for row in rows]),
        "extra_info": np.stack([row.extra_info for row in rows]),
        "legal_mask": np.stack([row.legal_mask for row in rows]),
        "actor_target": np.stack([row.actor_target for row in rows]),
    }
    with partial.open("wb") as stream:
        np.savez_compressed(stream, **arrays)
    partial.replace(final)
    return {"path": str(final.resolve()), "rows": len(rows), "sha256": file_sha256(final)}


def convert(source: Path, out_dir: Path, shard_rows: int, validate_only: bool) -> dict:
    if shard_rows <= 0:
        raise ValueError("shard_rows must be positive")
    source_sha = file_sha256(source)
    out_dir.mkdir(parents=True, exist_ok=True)
    rows: list[AdaptedRow] = []
    shards: list[dict] = []
    metadata_partial = out_dir / "provenance.jsonl.partial"
    metadata_final = out_dir / "provenance.jsonl"
    metadata_stream = None if validate_only else metadata_partial.open("w", encoding="utf-8", newline="\n")
    count = 0
    bridge_scope: str | None = None
    sized_probability_mass = 0.0
    projection_probability_mass = 0.0
    projection_error_mass: list[tuple[float, float]] = []
    maximum_projection_error = 0.0
    projected_sized_actions = 0
    try:
        for ordinal, source_row in iter_source(source):
            adapted = adapt_source_row(source_row, expected_ordinal=ordinal)
            row_scope = str(adapted.metadata["bridge_scope"])
            if bridge_scope is None:
                bridge_scope = row_scope
            elif bridge_scope != row_scope:
                raise ValueError("mixed_bridge_scope_forbidden")
            count += 1
            sized_probability_mass += float(adapted.metadata["sized_probability_mass"])
            projection_probability_mass += float(adapted.metadata["projection_probability_mass"])
            for projection in adapted.metadata["projection_records"]:
                error = float(projection["absolute_amount_error_over_source_pot"])
                mass = float(projection["probability_mass"])
                projection_error_mass.append((error, mass))
                maximum_projection_error = max(maximum_projection_error, error)
                if projection["projected"]:
                    projected_sized_actions += 1
            if metadata_stream:
                metadata_stream.write(json.dumps(adapted.metadata, sort_keys=True) + "\n")
                rows.append(adapted)
                if len(rows) >= shard_rows:
                    shards.append(_write_shard(out_dir, len(shards), rows))
                    rows = []
        if metadata_stream and rows:
            shards.append(_write_shard(out_dir, len(shards), rows))
        if count == 0:
            raise ValueError("empty_source")
    finally:
        if metadata_stream:
            metadata_stream.close()
    if not validate_only:
        metadata_partial.replace(metadata_final)

    weighted_p95 = 0.0
    total_error_mass = sum(mass for _, mass in projection_error_mass)
    if total_error_mass > 0:
        threshold = 0.95 * total_error_mass
        cumulative = 0.0
        for error, mass in sorted(projection_error_mass):
            cumulative += mass
            weighted_p95 = error
            if cumulative >= threshold:
                break
    projection_mass_fraction = (
        projection_probability_mass / sized_probability_mass
        if sized_probability_mass > 0 else 0.0
    )

    return {
        "schema_version": "v5.hybrid.h3.domain_adapter.manifest.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_VALIDATE_ONLY" if validate_only else "PASS_CONVERTED",
        "design_lock_sha256": LOCK_SHA256,
        "source": str(source.resolve()),
        "bridge_source_jsonl_sha256": source_sha,
        "rows": count,
        "actor_only": True,
        "critic_rows": 0,
        "required_provenance_label": OOD_LABEL,
        "bridge_scope": bridge_scope,
        "training_eligible": bridge_scope == FULL_SCOPE,
        "projection_risk": {
            "sized_probability_mass": sized_probability_mass,
            "projection_probability_mass": projection_probability_mass,
            "projection_mass_fraction": projection_mass_fraction,
            "projected_sized_actions": projected_sized_actions,
            "probability_weighted_p95_amount_error_over_source_pot": weighted_p95,
            "maximum_amount_error_over_source_pot": maximum_projection_error,
            "per_action_error_gate": MAX_ACTION_ERROR_OVER_SOURCE_POT,
            "sized_actions_mapped_to_allin": 0,
            "snapshot_roundtrip_mismatches": 0,
            "unsupported_target_mass": 0.0,
        },
        "shards": shards,
        "provenance": None if validate_only else {
            "path": str(metadata_final.resolve()),
            "sha256": file_sha256(metadata_final),
        },
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-jsonl", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--shard-rows", type=int, default=50_000)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    try:
        result = convert(args.source_jsonl, args.out_dir, args.shard_rows, args.validate_only)
        exit_code = 0
    except Exception as exc:
        result = {
            "schema_version": "v5.hybrid.h3.domain_adapter.manifest.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "error": str(exc),
            "behavior_launch_authorized": False,
            "official_hands_authorized": 0,
        }
        exit_code = 2
    args.manifest.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
