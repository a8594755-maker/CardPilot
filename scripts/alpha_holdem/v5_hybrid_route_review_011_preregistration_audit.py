#!/usr/bin/env python3
"""Independent fail-closed audit of Route Review 011 preregistration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_hybrid_route_review_011_preregistration_20260719.json"
OUT = ROOT / "reports/v5_hybrid_route_review_011_preregistration_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = d.get("schema_version") == "v5.hybrid.route_review.preregistration.v11.v1"
    checks["identity"] = d.get("design_id") == "HYBRID-ROUTE-REVIEW-011"
    checks["reporting_only"] = d.get("status") == "REGISTERED_REPORTING_ONLY_NO_LAUNCH"
    trigger = d["trigger"]
    bindings = {
        "h14_judgment": "reports/v5_hybrid_h14_judgment_20260719.json",
        "h14_incident": "reports/v5_hybrid_h14_resource_isolation_incident_20260719.json",
        "h14_terminal_audit": "reports/v5_hybrid_h14_terminal_audit_20260719.json",
    }
    for key, rel in bindings.items():
        checks[f"trigger_{key}"] = sha(ROOT / rel) == trigger[f"{key}_sha256"]
    audit = json.loads((ROOT / bindings["h14_terminal_audit"]).read_text(encoding="utf-8"))
    checks["h14_terminal_pass"] = audit.get("overall") == "PASS_COMPLETE_H14_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION"
    checks["partial_not_endpoint"] = trigger.get("h14_training_progress_hands") == 180772 and trigger.get("h14_endpoint_frozen") is False
    checks["terminal_class"] = trigger.get("h14_terminal") == "H14_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION"
    frozen = d["frozen_inputs"]
    frozen_paths = {
        "route_review_010_result": "reports/v5_hybrid_route_review_010_result_20260717.json",
        "route_review_010_audit": "reports/v5_hybrid_route_review_010_audit_20260717.json",
        "h14_design_lock_v6": "reports/v5_hybrid_h14_design_lock_v6_20260717.json",
        "h14_recovery": "reports/v5_h14_orphan_recovery_20260719.json",
        "path1_asset_lock": "reports/v5_h3_path1_successor_asset_lock_20260713.json",
        "cal_ext_002_completion": "reports/v5_cal_ext_002_completion_20260716.json",
        "cal_ext_002_completion_audit": "reports/v5_cal_ext_002_completion_audit_20260716.json",
    }
    for key, rel in frozen_paths.items():
        checks[f"frozen_{key}"] = sha(ROOT / rel) == frozen[f"{key}_sha256"]
    truth = d["truth_constraints"]
    checks["terminal_branches"] = all("TERMINAL" in truth[key] for key in ("w1", "exp005c", "h12", "h13", "h14"))
    checks["h14_never_reopen"] = "NEVER_REOPEN" in truth["h14"]
    checks["partial_forbidden"] = truth.get("h14_partial") == "FORBIDDEN_FOR_METHOD_MODEL_STRENGTH_OR_SUCCESSOR_SOURCE"
    checks["official_l0"] = truth.get("official_strength") == "L0"
    checks["no_action_tuning"] = truth.get("action_regret") == "MISSING" and truth.get("action_specific_tuning") == "FORBIDDEN"
    checks["path1_stopped"] = "STOPPED" in truth.get("path1", "")
    order = d["candidate_order"]
    checks["candidate_order"] = len(order) == 4 and order[0].startswith("CPV003_") and order[-1] == "ROUTE_EXHAUSTION_ESCALATION"
    rules = " ".join(d["decision_rule"]).lower()
    checks["rule_no_h14_reopen"] = "never resume" in rules and "h14 partial" in rules
    checks["rule_three_failures"] = "three consecutive lifecycle-control failures" in rules
    checks["rule_trainerless"] = "trainerless engineering prerequisite" in rules
    checks["rule_separate_h15"] = "separately preregistered h15" in rules
    checks["rule_cpv_fail"] = "cpv003 fail or inconclusive" in rules
    checks["rule_path1"] = "no-overwrite" in rules and "six belownormal" in rules and "zero gpu" in rules
    checks["rule_no_action_tune"] = "action regret" in rules
    checks["rule_exhaustion"] = "route exhaustion only" in rules
    gate = d["cpv003_registered_gate"]
    checks["readiness_gate"] = "within10 seconds" in gate.get("readiness", "") and gate.get("stress_cycles") == 20
    checks["creation_identity"] = all(token in gate.get("supervisor_identity", "") for token in ("creation_time", "command_line_sha256", "design_lock_sha256", "PID reuse"))
    checks["all_roles"] = all(role in gate.get("registered_children", "") for role in ("health", "protocol", "endpoint", "treatment_launch", "completion"))
    checks["adversarial"] = all(token in gate.get("adversarial_children", "") for token in ("unregistered sibling", "wrong parent", "wrong script hash", "wrong command hash"))
    checks["cleanup"] = "within15 seconds" in gate.get("cleanup", "") and "zero tagged survivors" in gate.get("cleanup", "")
    checks["rearm_gate"] = "nonzero" in gate.get("rearm", "") and "zero only" in gate.get("rearm", "")
    checks["immutable_bundle"] = "immutable" in gate.get("artifact", "") and "independent" in gate.get("artifact", "")
    checks["cpv_no_behavior"] = gate.get("behavior_launch_authority") == "NONE_CPV003_ONLY"
    path1 = d["path1_recovery_gate"]
    checks["path1_authority"] = path1.get("authority") == "AUTHORIZED_AFTER_ROUTE_REVIEW_011_PASS"
    checks["path1_exact"] = path1.get("overwrite") is False and path1.get("iterations_per_board") == 80000 and path1.get("seed") == 20260712 and path1.get("samples_per_bucket") == 1 and path1.get("workers") == 6 and path1.get("priority") == "BelowNormal" and path1.get("gpu") is False
    checks["path1_no_ingest"] = path1.get("training_ingestion") == "FORBIDDEN"
    out_contract = d["output_contract"]
    checks["no_launch"] = out_contract.get("behavior_launch_authority") == "NONE_REVIEW_ONLY"
    checks["official_zero"] = out_contract.get("official_hands_authority") == 0
    checks["no_strength"] = out_contract.get("strength_claim") == "FORBIDDEN"
    failed = sorted(key for key, value in checks.items() if not value)
    result = {
        "schema_version": "v5.hybrid.route_review.preregistration_audit.v11.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": sha(P),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "behavior_launch_authority": "NONE_AUDIT_ONLY",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
