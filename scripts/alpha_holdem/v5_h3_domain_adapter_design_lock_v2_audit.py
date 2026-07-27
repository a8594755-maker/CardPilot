#!/usr/bin/env python3
"""Independent fail-closed audit for H3-DOMAIN-ADAPTER-001-V2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "reports" / "v5_h3_domain_adapter_design_lock_v2_20260713.json"
EXPECTED_LOCK_SHA = "cab56df24be190a8486b4036a73ce4a028062e186e01764083f5c9f2f4f4088a"
EXPECTED_V1_SHA = "3b1a9e117e4bd48151c317f9ce868708a3c074a907eecf99e5d8cdd2424d2fa9"
EXPECTED_EVIDENCE_SHA = "e5519cb10325d286cecbf60d8a0dd40c4bb6bfca8a21b4b469af7def926a7b85"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(lock_path: Path = LOCK) -> dict:
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    evidence = ROOT / "reports" / "v5_h3_bridge_probability_rounding_audit_20260713.json"
    v1 = ROOT / "reports" / "v5_h3_domain_adapter_design_lock_20260713.json"
    checks = {
        "lock_sha": sha256(lock_path) == EXPECTED_LOCK_SHA,
        "schema": lock.get("schema_version") == "v5.hybrid.h3.domain_adapter.design_lock.v2",
        "v1_identity": sha256(v1) == EXPECTED_V1_SHA,
        "evidence_identity": sha256(evidence) == EXPECTED_EVIDENCE_SHA,
        "evidence_pin": lock["new_frozen_probability_serialization_contract"]["evidence_report_sha256"] == EXPECTED_EVIDENCE_SHA,
        "residual_bound": lock["new_frozen_probability_serialization_contract"]["maximum_allowed_absolute_source_sum_residual"] == 0.0050000001,
        "residual_rule": "first maximum-probability" in lock["new_frozen_probability_serialization_contract"]["correction"],
        "tie_break": lock["new_frozen_probability_serialization_contract"]["tie_break"] == "lowest source action index",
        "unsupported_mass_zero": lock["preserved_v1_contract"]["unsupported_target_mass_tolerance"] == 0.0,
        "smoke_forbidden": lock["new_frozen_bridge_scope_contract"]["smoke_training_eligible"] is False,
        "smoke_ceiling": lock["new_frozen_bridge_scope_contract"]["smoke_prefix_ceiling_rows"] == 10000,
        "full_600_gate": lock["preserved_v1_contract"]["required_complete_boards_for_h3_preregistration"] == 600,
        "corrected_root": lock["source_identity_and_qa_contract"]["only_asset_root"].endswith("pipeline_v3_hu_srp_200bb_legalallin_v2"),
        "iterations": lock["source_identity_and_qa_contract"]["metadata"]["iterations"] == 80000,
        "illegal_allin_zero": lock["source_identity_and_qa_contract"]["strict_streaming_qa"]["illegal_post_allin_extra_action_rows"] == 0,
        "actor_only": lock["preserved_v1_contract"]["actor_only"] is True,
        "critic_forbidden": lock["preserved_v1_contract"]["critic_supervision_forbidden"] is True,
        "no_prereg_authority": lock["h3_preregistration_authorized"] is False,
        "no_behavior_authority": lock["behavior_launch_authorized"] is False,
        "no_official_hands": lock["official_hands_authorized"] == 0,
    }
    passed = sum(bool(value) for value in checks.values())
    return {
        "schema_version": "v5.hybrid.h3.domain_adapter.design_lock_v2.audit.v1",
        "overall": "PASS_IMMUTABLE_OFFLINE_CORRECTION_LOCK" if passed == len(checks) else "FAIL_CLOSED",
        "lock_sha256": sha256(lock_path),
        "assertions_passed": passed,
        "assertions_total": len(checks),
        "checks": checks,
        "h3_preregistration_authorized": False,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
    }


def main() -> int:
    result = audit()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"].startswith("PASS") else 2


if __name__ == "__main__":
    raise SystemExit(main())
