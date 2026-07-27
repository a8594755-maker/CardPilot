#!/usr/bin/env python3
"""Independent structural audit for H3-DOMAIN-ADAPTER-001."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def audit(path: Path, expected_sha256: str) -> dict:
    errors: list[str] = []
    actual_sha256 = sha256(path)
    if actual_sha256 != expected_sha256.lower():
        errors.append("design_lock_sha256_mismatch")
    try:
        lock = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {
            "overall": "FAIL_CLOSED",
            "errors": [f"invalid_json:{exc}"],
            "actual_sha256": actual_sha256,
        }

    checks = {
        "schema": lock.get("schema_version") == "v5.hybrid.h3.domain_adapter.design_lock.v1",
        "identity": lock.get("design_id") == "H3-DOMAIN-ADAPTER-001",
        "offline_only_status": lock.get("status") == "LOCKED_OFFLINE_DESIGN_IMPLEMENTATION_PENDING",
        "synthetic_entry_honest": lock.get("primary_adapter_contract", {}).get("entry_state", {}).get("deployment_reachable") is False,
        "synthetic_label_frozen": lock.get("primary_adapter_contract", {}).get("entry_state", {}).get("required_provenance_label") == "SYNTHETIC_PATH1_SRP_ENTRY_OOD_NOT_DEPLOYMENT_REACHABLE",
        "actual_v55_mask": str(lock.get("primary_adapter_contract", {}).get("legal_mask", "")).startswith("actual deployment v5.5"),
        "actor_only": lock.get("primary_adapter_contract", {}).get("actor_only") is True,
        "critic_forbidden": str(lock.get("primary_adapter_contract", {}).get("critic_target", "")).startswith("FORBIDDEN"),
        "neighbors_diagnostic_only": lock.get("reachability_sensitivity_contract", {}).get("may_enter_h3_training") is False,
        "corrected_600_gate": lock.get("offline_validation_gates", {}).get("h3_preregistration_gate", {}).get("required_complete_qa_pass_boards") == 600,
        "selection_seed": lock.get("input_contract", {}).get("selection_seed") == 20260712,
        "quarantine_enforced": lock.get("input_contract", {}).get("quarantined_original_assets_forbidden") is True,
        "no_behavior_authority": lock.get("h3_preregistration_authorized") is False and lock.get("behavior_launch_authorized") is False,
        "no_official_authority": lock.get("official_hands_authorized") == 0 and lock.get("strength_claim") == "FORBIDDEN",
    }
    errors.extend(name for name, passed in checks.items() if not passed)
    return {
        "schema_version": "v5.hybrid.h3.domain_adapter.design_lock.audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not errors else "FAIL_CLOSED",
        "design_lock": str(path.resolve()),
        "design_lock_sha256": actual_sha256,
        "expected_sha256": expected_sha256.lower(),
        "checks": checks,
        "passed": sum(checks.values()),
        "total": len(checks),
        "errors": errors,
        "behavior_launch_authorized": False,
        "official_hands_authorized": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.lock, args.expected_sha256)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["overall"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
