#!/usr/bin/env python3
"""Independent fail-closed audit of CPV004 preregistration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_cpv004_preregistration_20260719.json"
OUT = ROOT / "reports/v5_cpv004_preregistration_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    c: dict[str, bool] = {}
    c["schema"] = d.get("schema_version") == "v5.cpv004.preregistration.v1"
    c["identity"] = d.get("design_id") == "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE"
    c["engineering_only"] = d.get("status") == "REGISTERED_ENGINEERING_ONLY_NO_BEHAVIOR_LAUNCH"
    authority = d["authority"]
    c["route_result"] = sha(ROOT / "reports/v5_hybrid_route_review_012_result_20260719.json") == authority.get("route_review_012_result_sha256")
    c["route_audit"] = sha(ROOT / "reports/v5_hybrid_route_review_012_audit_20260719.json") == authority.get("route_review_012_audit_sha256")
    c["route_selection"] = authority.get("selected_next") == d.get("design_id") and authority.get("route_exhausted") is False
    predecessor = d["predecessor"]
    c["cpv003_result"] = sha(ROOT / "reports/v5_cpv003_result_20260719.json") == predecessor.get("cpv003_result_sha256")
    c["cpv003_audit"] = sha(ROOT / "reports/v5_cpv003_result_audit_20260719.json") == predecessor.get("cpv003_audit_sha256")
    c["cpv003_diagnosis"] = sha(ROOT / "reports/v5_cpv003_failure_diagnosis_20260719.json") == predecessor.get("cpv003_diagnosis_sha256")
    c["cpv003_closed"] = predecessor.get("verdict") == "TERMINAL_FAIL_CLOSED_NO_REOPEN_NO_RECLASSIFY"
    c["single_change"] = "once after the complete" in d.get("single_engineering_change", "") and "diagnostic-only" in d.get("single_engineering_change", "")
    fixture = d["fixture"]
    c["fixture"] = fixture.get("seed") == 2026071903 and fixture.get("stress_cycles") == 20 and len(fixture.get("roles", [])) == 5 and fixture.get("adaptive_extension") is False
    c["new_runner"] = fixture.get("runner", "").endswith("v5_cpv004_lifecycle_stress.py")
    c["shared_tools"] = all(fixture.get(key, "").endswith(name) for key, name in (
        ("dummy_supervisor", "v5_cpv003_dummy_supervisor.py"),
        ("dummy_child", "v5_cpv003_dummy_child.py"),
        ("guard_module", "v5_lifecycle_guard_v2.py"),
    ))
    gates = d["gates"]
    c["readiness"] = gates.get("initial_ready_deadline_seconds") == 10.0 and gates.get("initial_ready_before_process_scan") is True
    c["twenty"] = gates.get("stress_cycles_required") == 20
    c["roles"] = gates.get("all_roles_exact_pass_each_cycle") is True
    c["eight_bindings"] = len(gates.get("identity_binding", [])) == 8
    c["four_adversarial"] = len(gates.get("adversarial_tokens_required", [])) == 4
    c["supervisor_states"] = gates.get("supervisor_exit_classification") == "LIFECYCLE_SHUTDOWN" and gates.get("supervisor_pid_reuse_classification") == "LIFECYCLE_SHUTDOWN_PID_REUSED_NOT_RESOURCE_VIOLATION"
    c["cleanup_deadline"] = gates.get("cleanup_deadline_seconds") == 15.0
    c["final_cleanup_gate"] = gates.get("cleanup_zero_tagged_survivors") == "ONE_FINAL_SCAN_AFTER_COMPLETE_SEQUENCE"
    c["snapshots_diagnostic"] = gates.get("per_child_survivor_snapshots") == "DIAGNOSTIC_ONLY_NOT_GATE"
    c["exit_codes"] = gates.get("injected_readiness_failure_exit_nonzero") is True and gates.get("normal_cycle_exit_zero") is True
    c["bundle_audit"] = gates.get("full_cycle_bundle_required") is True and gates.get("independent_audit_required") is True
    prohibited = " ".join(d["prohibited"]).lower()
    c["no_compute"] = all(token in prohibited for token in ("train_v5.py", "gpu use", "mirror evaluation", "slumbot", "official hands"))
    c["no_reopen"] = "cpv003 rerun" in prohibited and "h14 resume" in prohibited
    c["no_h15"] = "h15 preregistration or launch before terminal cpv004 pass" in prohibited
    rule = d["verdict_rule"]
    c["verdicts"] = all(name in rule for name in ("PASS", "FAIL", "INCONCLUSIVE")) and rule.get("no_posthoc_threshold_change") is True
    effect = d["terminal_effect"]
    c["pass_effect"] = effect.get("PASS") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY"
    c["fail_effect"] = effect.get("FAIL_OR_INCONCLUSIVE") == "REQUIRES_ROUTE_REVIEW_013_NO_BEHAVIOR_LAUNCH"
    c["path1"] = "EXISTING_EXACT_ASSET_JOB" in d["path1"].get("policy", "") and "NO_GPU" in d["path1"].get("policy", "")
    c["no_behavior"] = d.get("behavior_launch_authority") == "NONE"
    c["official_zero"] = d.get("official_hands_authorized") == 0
    c["no_strength"] = d.get("strength_claim") == "FORBIDDEN"
    failed = sorted(name for name, passed in c.items() if not passed)
    artifact = {
        "schema_version": "v5.cpv004.preregistration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": sha(P),
        "checks": c,
        "checks_passed": sum(c.values()),
        "checks_total": len(c),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
