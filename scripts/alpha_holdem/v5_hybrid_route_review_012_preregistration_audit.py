#!/usr/bin/env python3
"""Independent fail-closed audit of Route Review012 preregistration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_hybrid_route_review_012_preregistration_20260719.json"
OUT = ROOT / "reports/v5_hybrid_route_review_012_preregistration_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = d.get("schema_version") == "v5.hybrid.route_review.preregistration.v12.v1"
    checks["identity"] = d.get("design_id") == "HYBRID-ROUTE-REVIEW-012"
    checks["reporting_only"] = d.get("status") == "REGISTERED_REPORTING_ONLY_NO_LAUNCH"
    trigger = d["trigger"]
    paths = {
        "cpv003_result": "reports/v5_cpv003_result_20260719.json",
        "cpv003_audit": "reports/v5_cpv003_result_audit_20260719.json",
        "cpv003_diagnosis": "reports/v5_cpv003_failure_diagnosis_20260719.json",
    }
    for key, relative in paths.items():
        checks[f"hash_{key}"] = sha(ROOT / relative) == trigger[f"{key}_sha256"]
    result = json.loads((ROOT / paths["cpv003_result"]).read_text(encoding="utf-8"))
    audit = json.loads((ROOT / paths["cpv003_audit"]).read_text(encoding="utf-8"))
    diagnosis = json.loads((ROOT / paths["cpv003_diagnosis"]).read_text(encoding="utf-8"))
    checks["cpv_terminal_fail"] = result.get("overall") == "FAIL_CLOSED" and result.get("classification") == trigger.get("cpv003_terminal")
    checks["cpv_audit_pass"] = audit.get("overall") == "PASS" and audit.get("audited_cpv003_verdict") == "FAIL_CLOSED"
    checks["review_required"] = trigger.get("route_review_required") is True and result.get("terminal_effect") == "REQUIRES_ROUTE_REVIEW_012_NO_BEHAVIOR_LAUNCH"
    observed = diagnosis["observed_facts"]
    checks["final_zero"] = observed.get("final_tagged_survivors_each_cycle") == 0
    checks["cleanup_fast"] = observed.get("maximum_full_cleanup_elapsed_seconds", 99) <= observed.get("registered_cleanup_deadline_seconds", 0)
    checks["other_gates_pass"] = all(observed.get(key) is True for key in (
        "all_five_roles_exact_pass",
        "all_four_adversarial_tokens_pass",
        "all_normal_supervisor_exit_zero",
        "all_supervisor_shutdown_classifications_pass",
        "all_pid_reuse_classifications_pass",
        "injected_readiness_failure_pass",
    ))
    checks["no_compute"] = observed.get("trainer_launched") is False and observed.get("gpu_used") is False and observed.get("official_hands") == 0
    mechanism = diagnosis["failure_mechanism"]
    checks["isolated_false_negative"] = mechanism.get("type") == "PROSPECTIVE_TEST_PREDICATE_FALSE_NEGATIVE" and mechanism.get("method_or_strength_inference") == "NONE"
    correction = diagnosis["prospective_correction"]
    checks["no_auto_rerun"] = correction.get("automatic_rerun") == "FORBIDDEN"
    checks["single_correction"] = correction.get("candidate") == "CPV004_TRAINERLESS_LIFECYCLE_STRESS_GATE" and "only once after the complete" in correction.get("single_engineering_change", "")
    truth = d["frozen_truth"]
    checks["terminal_truth"] = all("TERMINAL" in truth[key] for key in ("cpv003_verdict", "h12", "h13", "h14"))
    checks["clean_source"] = truth.get("clean_future_source") == "H11_CONTROL_ITER35051_HANDS576021901_SHA96A007"
    checks["official_l0"] = truth.get("official_strength") == "L0" and truth.get("latest_official", "").startswith("5000_GREEDY_DIRECT")
    checks["path1_unchanged"] = "EXISTING_EXACT_ASSET_JOB_ONLY" in truth.get("path1", "") and "NO_GPU" in truth.get("path1", "")
    order = d["candidate_order"]
    checks["candidate_order"] = len(order) == 4 and order[0].startswith("CPV004_") and order[-1] == "ROUTE_EXHAUSTION_ESCALATION"
    rules = " ".join(d["decision_rule"])
    checks["rule_no_reopen"] = "Never reopen" in rules and "old registration" in rules
    checks["rule_final_observation"] = "evaluated once after the complete cleanup sequence" in rules
    checks["rule_retains"] = "retains20 cycles,seed2026071903" in rules and "15-second cleanup deadline" in rules
    checks["rule_h15_separate"] = "separate H15 preregistration" in rules and "Route Review013" in rules
    checks["rule_no_compute"] = "Do not launch trainer" in rules and "official hands" in rules
    checks["rule_exhaustion"] = "route exhaustion only" in rules.lower()
    out = d["output_contract"]
    checks["no_behavior"] = out.get("behavior_launch_authority") == "NONE_REVIEW_ONLY"
    checks["official_zero"] = out.get("official_hands_authority") == 0
    checks["no_strength"] = out.get("strength_claim") == "FORBIDDEN"
    failed = sorted(name for name, passed in checks.items() if not passed)
    artifact = {
        "schema_version": "v5.hybrid.route_review.preregistration_audit.v12.v1",
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
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
