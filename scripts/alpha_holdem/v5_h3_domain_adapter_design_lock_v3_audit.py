#!/usr/bin/env python3
"""Independent fail-closed audit for H3-DOMAIN-ADAPTER-001-V3-SNAPSHOT."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "reports" / "v5_h3_domain_adapter_design_lock_v3_20260713.json"
V2_FAIL = ROOT / "reports" / "v5_h3_first_corrected_board_smoke_v2_terminal_fail_20260713.json"
GAP = ROOT / "reports" / "v5_h3_path1_snapshot_state_gap_audit_20260713.json"
EXPECTED_LOCK_SHA = "fe8ae6ecb32829be62f9acd3acf0935df1ee3778b4761ebbf2c2d2b6f5f5832e"
EXPECTED_V2_FAIL_SHA = "2efe8fa27e0f43b81ac550c39d87dc4c9e6b77821eafc28b312330a0b7ae07c5"
EXPECTED_GAP_SHA = "225e29cd94126c8900a7a5b1d0eef0edad40e819731aadcbae2fab8827e9c699"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(lock_path: Path = LOCK) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    mapping = lock["legality_aware_action_mapping"]
    smoke = lock["first_corrected_board_smoke_gate"]
    full = lock["full_selected_corpus_domain_risk_gate"]
    snapshot = lock["synthetic_v55_snapshot_construction"]
    checks = {
        "lock_sha": sha256(lock_path) == EXPECTED_LOCK_SHA,
        "schema": lock.get("schema_version") == "v5.hybrid.h3.domain_adapter.design_lock.v3",
        "status": lock.get("status") == "LOCKED_OFFLINE_IMPLEMENTATION_PENDING",
        "v2_fail_identity": sha256(V2_FAIL) == EXPECTED_V2_FAIL_SHA,
        "gap_identity": sha256(GAP) == EXPECTED_GAP_SHA,
        "v2_fail_pin": lock["supersedes_terminal_v2_without_reclassification"]["v2_terminal_failure_artifact_sha256"] == EXPECTED_V2_FAIL_SHA,
        "v2_not_reclassified": lock["supersedes_terminal_v2_without_reclassification"]["v2_verdict_remains"] == "FAIL_CLOSED_UNSUPPORTED_V55_TARGET_MASS",
        "gap_pin": lock["frozen_new_evidence"]["snapshot_state_gap_audit_sha256"] == EXPECTED_GAP_SHA,
        "direct_snapshot": "direct state construction" in snapshot["method"],
        "apply_forbidden": "forbidden" in snapshot["method"].lower(),
        "snapshot_exact_fields": set(snapshot["required_exact_roundtrip_fields"]) == {"pot", "stacks", "street", "current_player", "raise_count", "facing_bet"},
        "actual_legal_mapping": "actual legal non-all-in" in mapping["sized_bet_or_raise"],
        "lower_slot_tie": "lower slot" in mapping["sized_bet_or_raise"],
        "sized_to_allin_forbidden": mapping["sized_action_to_allin"] == "FORBIDDEN",
        "no_legal_candidate_fail": mapping["no_legal_sized_candidate"] == "FAIL_CLOSED",
        "no_drop_or_renorm": all(word in mapping["mass_handling"] for word in ("drop", "renormalization", "forbidden")),
        "per_action_error": mapping["maximum_absolute_amount_error_over_source_pot_per_action"] == 0.5,
        "smoke_fixed_board_rows_runs": smoke["board_selection"].endswith("fixed board6") and smoke["rows"] == 1000 and smoke["runs"] == 2,
        "smoke_zero_unsupported": smoke["unsupported_target_mass"] == 0.0,
        "smoke_no_allin_projection": smoke["sized_actions_mapped_to_allin"] == 0,
        "full_600": full["qa_pass_boards"] == 600,
        "full_projection_mass_cap": full["maximum_projection_mass_fraction"] == 0.25,
        "full_p95_error_cap": full["maximum_probability_weighted_p95_amount_error_over_source_pot"] == 0.25,
        "full_max_error_cap": full["maximum_per_action_amount_error_over_source_pot"] == 0.5,
        "actor_only": lock["preserved_v2_contract"]["actor_only"] is True and lock["preserved_v2_contract"]["critic_supervision_forbidden"] is True,
        "no_dataset_authority": lock.get("dataset_materialization_authorized") is False,
        "no_behavior_authority": lock.get("h3_preregistration_authorized") is False and lock.get("behavior_launch_authorized") is False,
        "no_official_hands": lock.get("official_hands_authorized") == 0,
    }
    passed = sum(bool(value) for value in checks.values())
    return {
        "schema_version": "v5.hybrid.h3.domain_adapter.design_lock_v3.audit.v1",
        "overall": "PASS_IMMUTABLE_SNAPSHOT_ADAPTER_LOCK" if passed == len(checks) else "FAIL_CLOSED",
        "lock_sha256": sha256(lock_path),
        "assertions_passed": passed,
        "assertions_total": len(checks),
        "checks": checks,
        "dataset_materialization_authorized": False,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
