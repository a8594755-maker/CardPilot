#!/usr/bin/env python3
"""Independent fail-closed audit of Route Review012 result."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "reports/v5_hybrid_route_review_012_result_20260719.json"
OUT = ROOT / "reports/v5_hybrid_route_review_012_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(RESULT.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = d.get("schema_version") == "v5.hybrid.route_review.result.v12.v1"
    checks["identity"] = d.get("design_id") == "HYBRID-ROUTE-REVIEW-012"
    checks["pass_review"] = d.get("overall") == "PASS_ROUTE_REVIEW"
    checks["prereg_hash"] = sha(ROOT / "reports/v5_hybrid_route_review_012_preregistration_20260719.json") == d.get("registration_sha256")
    checks["prereg_audit_hash"] = sha(ROOT / "reports/v5_hybrid_route_review_012_preregistration_audit_20260719.json") == d.get("registration_audit_sha256")
    prereg_audit = json.loads((ROOT / "reports/v5_hybrid_route_review_012_preregistration_audit_20260719.json").read_text(encoding="utf-8"))
    checks["prereg_audit_pass"] = prereg_audit.get("overall") == "PASS" and prereg_audit.get("checks_passed") == 30
    evidence = d["evidence_matrix"]
    cpv = evidence["cpv003"]
    checks["cpv_result_hash"] = sha(ROOT / "reports/v5_cpv003_result_20260719.json") == cpv.get("result_sha256")
    checks["cpv_audit_hash"] = sha(ROOT / "reports/v5_cpv003_result_audit_20260719.json") == cpv.get("audit_sha256")
    checks["cpv_diagnosis_hash"] = sha(ROOT / "reports/v5_cpv003_failure_diagnosis_20260719.json") == cpv.get("diagnosis_sha256")
    checks["cpv_terminal_fail"] = cpv.get("verdict") == "FAIL_CLOSED" and cpv.get("classification") == "CPV003_FAIL_REGISTERED_GATE" and cpv.get("terminal_reclassification") == "FORBIDDEN"
    checks["twenty_failed"] = cpv.get("cycles_passed") == 0 and cpv.get("cycles_failed") == 20
    gate = evidence["gate_localization"]
    checks["other_gates"] = gate.get("non_cleanup_gates") == "PASS_ALL_20_CYCLES"
    checks["final_zero"] = gate.get("final_tagged_survivors") == 0
    checks["within_deadline"] = gate.get("maximum_full_cleanup_elapsed_seconds", 99) <= gate.get("cleanup_deadline_seconds", 0)
    checks["predicate_identified"] = "INTERMEDIATE_PER_CHILD" in gate.get("failed_predicate", "")
    checks["prospective_only"] = gate.get("prospectively_correctable") is True and gate.get("method_or_strength_evidence") == "NONE"
    route = evidence["route_state"]
    checks["terminal_windows"] = all("TERMINAL_INCONCLUSIVE" in route[key] for key in ("h12", "h13", "h14"))
    checks["clean_source"] = route.get("clean_h11_source_available") is True
    checks["official_l0"] = route.get("latest_official_level") == "L0" and route.get("official_hands_this_review") == 0
    checks["path1_untouched"] = route.get("path1_policy") == "EXISTING_EXACT_JOB_ONLY_UNTOUCHED"
    decision = d["decision"]
    checks["selected_cpv004"] = decision.get("selected_next") == "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE"
    checks["route_not_exhausted"] = decision.get("route_exhausted") is False
    checks["engineering_only"] = decision.get("classification") == "ENGINEERING_PREREQUISITE_NOT_BEHAVIOR_WINDOW"
    contract = decision["cpv004_contract"]
    checks["single_change"] = "once after the complete" in contract.get("single_engineering_change", "") and "diagnostic-only" in contract.get("single_engineering_change", "")
    checks["fixture_frozen"] = contract.get("stress_cycles") == 20 and contract.get("seed") == 2026071903 and len(contract.get("roles", [])) == 5
    checks["deadlines_frozen"] = contract.get("readiness_deadline_seconds") == 10.0 and contract.get("cleanup_deadline_seconds") == 15.0
    checks["eight_fields"] = len(contract.get("identity_fields", [])) == 8
    checks["four_adversarial"] = len(contract.get("adversarial_tokens", [])) == 4
    checks["no_compute"] = all(contract.get(key) is False for key in ("trainer", "gpu", "evaluator", "slumbot")) and contract.get("official_hands") == 0
    checks["terminal_effects"] = contract.get("pass_effect") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY" and contract.get("fail_or_inconclusive_effect") == "REQUIRES_ROUTE_REVIEW_013_NO_BEHAVIOR_LAUNCH"
    checks["no_behavior"] = d.get("behavior_launch_authorized") == "NONE_CPV004_ENGINEERING_ONLY"
    checks["official_zero"] = d.get("official_hands_authorized") == 0
    checks["no_strength"] = d.get("strength_claim") == "FORBIDDEN"
    failed = sorted(name for name, passed in checks.items() if not passed)
    artifact = {
        "schema_version": "v5.hybrid.route_review.audit.v12.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result_sha256": sha(RESULT),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "selected_next": decision.get("selected_next") if not failed else None,
        "route_exhausted": decision.get("route_exhausted") if not failed else None,
        "behavior_launch_authority": "NONE_REVIEW_AUDIT_ONLY",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
