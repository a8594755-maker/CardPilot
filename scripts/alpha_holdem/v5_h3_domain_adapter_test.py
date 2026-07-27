#!/usr/bin/env python3
"""Focused tests for H3-DOMAIN-ADAPTER-001 implementation."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np

from alpha_holdem.v5_h3_domain_adapter import (
    FULL_SCOPE,
    LOCK_SHA256,
    OOD_LABEL,
    SMOKE_SCOPE,
    adapt_source_row,
    convert,
)


def _row(ordinal: int, source_sha: str, history: str, player: int, actions: list[str]) -> dict:
    contracts = {
        "": {
            "snapshot": {"pot": 5.0, "stacks": [197.5, 197.5], "facingBet": 0.0, "currentPlayer": 0, "street": "FLOP", "toCall": 0.0, "isFirstAction": True, "raiseCount": 0},
            "events": [],
            "amounts": [None, 1.65, 3.35, 5.0, 197.5],
            "slots": [1, 2, 4, 6, 8],
        },
        "1": {
            "snapshot": {"pot": 6.65, "stacks": [195.85, 197.5], "facingBet": 1.65, "currentPlayer": 1, "street": "FLOP", "toCall": 1.65, "isFirstAction": False, "raiseCount": 0},
            "events": [{"street": "FLOP", "player": 0, "actionType": "BET", "additionalAmount": 1.65}],
            "amounts": [None, None, 4.39, 7.21, 9.95, 197.5],
            "slots": [0, 1, 4, 6, 7, 8],
        },
        "1c/": {
            "snapshot": {"pot": 8.3, "stacks": [195.85, 195.85], "facingBet": 0.0, "currentPlayer": 0, "street": "TURN", "toCall": 0.0, "isFirstAction": True, "raiseCount": 0},
            "events": [
                {"street": "FLOP", "player": 0, "actionType": "BET", "additionalAmount": 1.65},
                {"street": "FLOP", "player": 1, "actionType": "CALL", "additionalAmount": 1.65},
            ],
            "amounts": [None, 4.15, 6.23, 10.38, 195.85],
            "slots": [1, 3, 5, 6, 8],
        },
    }
    contract = contracts[history]
    slots = contract["slots"]
    assert len(slots) == len(actions)
    probabilities = [1.0 / len(actions)] * len(actions)
    target = [0.0] * 9
    for slot, probability in zip(slots, probabilities, strict=True):
        target[slot] += probability
    return {
        "schema_version": "path1.v55_bridge_source.v2",
        "bridge_design_lock_v3_sha256": LOCK_SHA256,
        "bridge_scope": FULL_SCOPE,
        "board_id": 2,
        "info_set_key": f"fixture-{ordinal}",
        "player": player,
        "history_key": history,
        "bucket_identity": f"b{ordinal}",
        "hole_cards": [20 + ordinal, 25 + ordinal],
        "board_cards": [0 + ordinal, 5 + ordinal, 10 + ordinal],
        "cfr_actions": actions,
        "cfr_action_descriptors": [
            {
                "source_action_name": action,
                "exact_additional_amount": amount,
                "exact_amount_over_source_pot": None if amount is None else amount / contract["snapshot"]["pot"],
                "nominal_v55_slot": slot,
            }
            for action, amount, slot in zip(actions, contract["amounts"], slots, strict=True)
        ],
        "cfr_probabilities": probabilities,
        "nominal_v55_actor_target": target,
        "path1_state_snapshot": contract["snapshot"],
        "path1_history_events": contract["events"],
        "source_probability_sum": 1.0,
        "rounding_residual": 0.0,
        "rounding_residual_action_index": 0,
        "source_file_sha256": source_sha,
        "source_row_ordinal": ordinal,
        "path1_asset_classification": "CORRECTED_LEGAL_ALLIN_QA_PASS",
        "required_provenance_label": OOD_LABEL,
    }


def main() -> int:
    root_actions = ["check", "bet_0", "bet_1", "bet_2", "allin"]
    facing_actions = ["fold", "call", "raise_0", "raise_1", "raise_2", "allin"]
    direct = _row(0, "a" * 64, "", 0, root_actions)
    adapted = adapt_source_row(direct, expected_ordinal=0)
    assert adapted.card_info.shape == (6, 4, 13)
    assert adapted.action_info.shape == (25, 4, 5)
    assert adapted.extra_info.shape == (2,)
    assert adapted.legal_mask.shape == (9,)
    assert adapted.actor_target.shape == (9,)
    assert abs(float(adapted.actor_target.sum()) - 1.0) < 1e-6
    assert float(adapted.actor_target[adapted.legal_mask <= 0].sum()) == 0.0
    assert adapted.metadata["deployment_reachable"] is False
    assert adapted.metadata["critic_target_present"] is False

    with tempfile.TemporaryDirectory() as temp:
        temp_path = Path(temp)
        source = temp_path / "source.jsonl"
        rows = [
            _row(0, "", "", 0, root_actions),
            _row(1, "", "1", 1, facing_actions),
            _row(2, "", "1c/", 0, root_actions),
        ]
        # Each row binds its immutable upstream strategy file.  The adapter
        # independently hashes the bridge-source JSONL in its output manifest.
        identity = "b" * 64
        for row in rows:
            row["source_file_sha256"] = identity
        source.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
        # Directly validate both rows against the frozen upstream identity.
        for ordinal, row in enumerate(rows):
            adapt_source_row(row, expected_ordinal=ordinal)

        converted = convert(source, temp_path / "out", shard_rows=1, validate_only=False)
        assert converted["overall"] == "PASS_CONVERTED"
        assert converted["bridge_scope"] == FULL_SCOPE
        assert converted["training_eligible"] is True
        assert converted["rows"] == 3
        assert len(converted["shards"]) == 3
        assert converted["projection_risk"]["unsupported_target_mass"] == 0.0
        assert converted["projection_risk"]["snapshot_roundtrip_mismatches"] == 0
        with np.load(converted["shards"][0]["path"]) as shard:
            assert shard["card_info"].shape == (1, 6, 4, 13)
            assert shard["action_info"].shape == (1, 25, 4, 5)
            assert shard["actor_target"].shape == (1, 9)

        bad = dict(rows[0])
        bad["required_provenance_label"] = "REACHABLE"
        try:
            adapt_source_row(bad, expected_ordinal=0)
            raise AssertionError("tampered OOD provenance passed")
        except ValueError as exc:
            assert "synthetic_ood" in str(exc)

        bad_mass = dict(rows[0])
        bad_mass["cfr_probabilities"] = [0.1] * len(root_actions)
        try:
            adapt_source_row(bad_mass, expected_ordinal=0)
            raise AssertionError("invalid probability mass passed")
        except ValueError as exc:
            assert "probability_mass" in str(exc)

        bad_slot = dict(rows[0])
        bad_slot["cfr_action_descriptors"] = [dict(value) for value in rows[0]["cfr_action_descriptors"]]
        bad_slot["cfr_action_descriptors"][0]["nominal_v55_slot"] = 8
        try:
            adapt_source_row(bad_slot, expected_ordinal=0)
            raise AssertionError("tampered semantic slots passed")
        except ValueError as exc:
            assert "passive_slot" in str(exc)

        bad_snapshot = dict(rows[0])
        bad_snapshot["path1_state_snapshot"] = dict(rows[0]["path1_state_snapshot"])
        bad_snapshot["path1_state_snapshot"]["pot"] = 6.0
        try:
            adapt_source_row(bad_snapshot, expected_ordinal=0)
            raise AssertionError("tampered source snapshot passed")
        except ValueError as exc:
            assert "snapshot_event_replay_mismatch" in str(exc)

        bad_scope = dict(rows[0])
        bad_scope["bridge_scope"] = "TRAINING"
        try:
            adapt_source_row(bad_scope, expected_ordinal=0)
            raise AssertionError("invalid bridge scope passed")
        except ValueError as exc:
            assert "bridge_scope" in str(exc)

        bad_residual = dict(rows[0])
        bad_residual["rounding_residual"] = 0.001
        try:
            adapt_source_row(bad_residual, expected_ordinal=0)
            raise AssertionError("tampered residual passed")
        except ValueError as exc:
            assert "residual_identity" in str(exc)

        smoke_rows = [dict(rows[0])]
        smoke_rows[0]["bridge_scope"] = SMOKE_SCOPE
        smoke_source = temp_path / "smoke.jsonl"
        smoke_source.write_text(json.dumps(smoke_rows[0]) + "\n", encoding="utf-8")
        smoke = convert(smoke_source, temp_path / "smoke-out", shard_rows=1, validate_only=True)
        assert smoke["bridge_scope"] == SMOKE_SCOPE
        assert smoke["training_eligible"] is False

    print("PASS 45/45 H3 snapshot-adapter state/action/mass/scope/projection/tamper assertions")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
