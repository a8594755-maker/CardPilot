#!/usr/bin/env python3
"""Independent fail-closed audit of Hybrid Route Review 011 result."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RESULT = ROOT / "reports/v5_hybrid_route_review_011_result_20260719.json"
OUT = ROOT / "reports/v5_hybrid_route_review_011_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(RESULT.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = d.get("schema_version") == "v5.hybrid.route_review.result.v11.v1"
    checks["identity"] = d.get("design_id") == "HYBRID-ROUTE-REVIEW-011"
    checks["pass_review"] = d.get("overall") == "PASS_ROUTE_REVIEW"
    checks["prereg_hash"] = sha(ROOT / "reports/v5_hybrid_route_review_011_preregistration_20260719.json") == d.get("registration_sha256")
    checks["prereg_audit_hash"] = sha(ROOT / "reports/v5_hybrid_route_review_011_preregistration_audit_20260719.json") == d.get("registration_audit_sha256")
    prereg_audit = json.loads((ROOT / "reports/v5_hybrid_route_review_011_preregistration_audit_20260719.json").read_text(encoding="utf-8"))
    checks["prereg_audit_pass"] = prereg_audit.get("overall") == "PASS" and prereg_audit.get("checks_passed") == 45
    evidence = d["evidence_matrix"]
    h14 = evidence["H14"]
    checks["h14_judgment_hash"] = sha(ROOT / "reports/v5_hybrid_h14_judgment_20260719.json") == h14.get("judgment_sha256")
    checks["h14_incident_hash"] = sha(ROOT / "reports/v5_hybrid_h14_resource_isolation_incident_20260719.json") == h14.get("incident_sha256")
    checks["h14_audit_hash"] = sha(ROOT / "reports/v5_hybrid_h14_terminal_audit_20260719.json") == h14.get("terminal_audit_sha256")
    checks["h14_partial_identity"] = h14.get("control_training_progress_hands") == 180772 and h14.get("partial_checkpoint_sha256") == "1be248ca54b072413c6a5fe77f7b494c724d35ed8f821c62644fc0e24e44a7d9"
    checks["h14_no_science"] = h14.get("control_endpoint") is False and h14.get("treatment_launched") is False and h14.get("mirror_launched") is False and h14.get("official_hands") == 0 and h14.get("method_effect_evidence") == "NONE"
    checks["h14_closed"] = h14.get("resume_extend_reclassify_or_reuse") == "FORBIDDEN"
    control = evidence["control_plane_history"]
    checks["three_failures"] = control.get("consecutive_behavior_windows_without_completed_comparison") == 3 and all(key in control for key in ("h12", "h13", "h14"))
    checks["no_direct_h15"] = control.get("direct_h15_launch_supported") is False
    checks["repairable"] = control.get("repairable_prospectively") is True and control.get("required_next") == "TRAINERLESS_STRESS_VALIDATION"
    source = evidence["clean_source"]
    checks["source_hash"] = sha(ROOT / source["checkpoint_path"]) == source.get("checkpoint_sha256")
    checks["source_identity"] = source.get("iteration") == 35051 and source.get("hands") == 576021901 and source.get("available") is True
    external = evidence["external"]
    checks["external_l0"] = external.get("official_hands") == 5000 and external.get("level") == "L0" and external.get("promotion_or_formal100k_authorized") is False
    checks["external_point_ci"] = external.get("bb_per_100") == -146.17260000000002 and external.get("ci95") == [-238.59789051053525, -53.7473094894648]
    checks["no_action_tune"] = external.get("action_regret") == "MISSING" and external.get("action_specific_tuning") == "FORBIDDEN"
    path1 = evidence["Path1"]
    checks["path1_asset_lock"] = sha(ROOT / "reports/v5_h3_path1_successor_asset_lock_20260713.json") == path1.get("asset_lock_sha256")
    checks["path1_recovery"] = sha(ROOT / "reports/v5_h14_orphan_recovery_20260719.json") == path1.get("h14_recovery_sha256")
    checks["path1_restart"] = path1.get("alive_at_h14_recovery") is False and path1.get("restart_authorized") is True and "NO_OVERWRITE" in path1.get("restart_contract", "")
    checks["path1_no_ingest"] = path1.get("training_ingestion") == "FORBIDDEN"
    alternatives = evidence["alternatives"]
    checks["terminal_alternatives"] = all("TERMINAL" in alternatives[key] for key in ("W1", "EXP005_C", "H14"))
    checks["direct_h15_deferred"] = alternatives.get("direct_H15") == "DEFERRED_UNTIL_CPV003_PASS"
    checks["route_not_exhausted_alt"] = alternatives.get("route_exhaustion") == "FALSE_REPAIRABLE_ENGINEERING_PREREQUISITE_EXISTS"
    decision = d["decision"]
    checks["selected_cpv003"] = decision.get("selected_next") == "CPV003_TRAINERLESS_LIFECYCLE_STRESS_GATE_THEN_SEPARATE_H15"
    checks["route_not_exhausted"] = decision.get("route_exhausted") is False
    checks["engineering_only"] = decision.get("classification") == "ENGINEERING_PREREQUISITE_NOT_BEHAVIOR_WINDOW"
    cpv = decision["cpv003"]
    checks["dummy_only"] = cpv.get("dummy_processes_only") is True and cpv.get("train_v5") is False and cpv.get("gpu") is False and cpv.get("official_hands") == 0
    checks["stress_gate"] = cpv.get("stress_cycles") == 20 and cpv.get("readiness_deadline_seconds") == 10 and cpv.get("cleanup_deadline_seconds") == 15
    repairs = " ".join(cpv.get("required_repairs", [])).lower()
    checks["readiness_repair"] = "initial_ready" in repairs and "before full process scan" in repairs
    checks["creation_repair"] = "creation identity" in repairs and "pid reuse" in repairs
    checks["cleanup_repair"] = "complete tagged descendant tree" in repairs
    checks["cpv_terminal_effects"] = cpv.get("terminal_pass_effect") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY" and cpv.get("fail_or_inconclusive_effect") == "NEW_ROUTE_REVIEW_NO_BEHAVIOR_LAUNCH"
    h15 = decision["future_h15_if_cpv003_passes"]
    checks["future_h15_source"] = h15.get("source_checkpoint_sha256") == source.get("checkpoint_sha256") and h15.get("source_iteration") == 35051 and h15.get("source_hands") == 576021901
    checks["future_single_variable"] = h15.get("single_variable") == "catch-up value loss MSE versus SmoothL1 beta1.0" and h15.get("fresh_same_start_fixed_hands") == 20000000
    checks["no_partial_reuse"] = h15.get("h14_partial_reuse") == "FORBIDDEN"
    checks["future_no_launch"] = h15.get("launch_authority", "").startswith("NONE_UNTIL_SEPARATE_PREREGISTRATION")
    path_decision = decision["path1_restart"]
    checks["path1_decision"] = path_decision.get("authorized") is True and path_decision.get("overwrite") is False and path_decision.get("workers") == 6 and path_decision.get("priority") == "BelowNormal" and path_decision.get("gpu") is False and path_decision.get("asset_generation_only") is True
    checks["no_behavior_authority"] = d.get("behavior_launch_authorized") == "NONE_CPV003_ENGINEERING_ONLY"
    checks["path1_authorized"] = d.get("path1_restart_authorized") is True
    checks["official_zero"] = d.get("official_hands_authorized") == 0
    checks["no_strength"] = d.get("strength_claim") == "FORBIDDEN"
    failed = sorted(key for key, value in checks.items() if not value)
    result = {
        "schema_version": "v5.hybrid.route_review.audit.v11.v1",
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
        "path1_restart_authorized": d.get("path1_restart_authorized") if not failed else False,
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
