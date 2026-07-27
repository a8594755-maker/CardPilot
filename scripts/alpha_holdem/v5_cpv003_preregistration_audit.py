#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_cpv003_preregistration_20260719.json"
OUT = ROOT / "reports/v5_cpv003_preregistration_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    checks: dict[str, bool] = {}
    checks["schema"] = d.get("schema_version") == "v5.cpv003.preregistration.v1"
    checks["identity"] = d.get("design_id") == "CPV003_TRAINERLESS_LIFECYCLE_STRESS_GATE"
    checks["engineering_only"] = d.get("status") == "REGISTERED_ENGINEERING_ONLY_NO_BEHAVIOR_LAUNCH"
    authority = d["authority"]
    checks["route_result"] = sha(ROOT / "reports/v5_hybrid_route_review_011_result_20260719.json") == authority.get("route_review_011_result_sha256")
    checks["route_audit"] = sha(ROOT / "reports/v5_hybrid_route_review_011_audit_20260719.json") == authority.get("route_review_011_audit_sha256")
    route_audit = json.loads((ROOT / "reports/v5_hybrid_route_review_011_audit_20260719.json").read_text(encoding="utf-8"))
    checks["route_pass"] = route_audit.get("overall") == "PASS" and route_audit.get("selected_next") == authority.get("selected_next") and route_audit.get("route_exhausted") is False
    prohibited = " ".join(d["prohibited"]).lower()
    checks["no_trainer"] = "train_v5.py" in prohibited and "checkpoint" in prohibited
    checks["no_eval"] = "mirror" in prohibited and "slumbot" in prohibited and "official hands" in prohibited
    checks["no_h14_reuse"] = "h14 resume" in prohibited and "partial reuse" in prohibited
    checks["no_h15_before_pass"] = "h15 preregistration or launch before terminal cpv003 pass" in prohibited
    fixture = d["fixture"]
    checks["seed_cycles"] = fixture.get("seed") == 2026071903 and fixture.get("stress_cycles") == 20 and fixture.get("adaptive_extension") is False
    checks["five_roles"] = fixture.get("roles") == ["health", "protocol", "endpoint", "treatment_launch", "completion"]
    checks["three_tools"] = all(str(fixture.get(key, "")).startswith("scripts/alpha_holdem/") for key in ("dummy_supervisor", "dummy_child", "guard_module"))
    gates = d["gates"]
    checks["ready_deadline"] = gates.get("initial_ready_deadline_seconds") == 10.0 and gates.get("initial_ready_before_process_scan") is True
    checks["twenty_exact"] = gates.get("stress_cycles_required") == 20 and gates.get("all_roles_exact_pass_each_cycle") is True
    checks["eight_bindings"] = gates.get("identity_binding") == ["pid", "parent_pid", "creation_time", "executable", "command_line_sha256", "script_sha256", "design_lock_sha256", "role"]
    checks["four_adversarial"] = gates.get("adversarial_tokens_required") == ["unregistered_sibling", "wrong_parent", "wrong_script_sha256", "wrong_command_line_sha256"]
    checks["supervisor_exit"] = gates.get("supervisor_exit_classification") == "LIFECYCLE_SHUTDOWN"
    checks["pid_reuse"] = gates.get("supervisor_pid_reuse_classification") == "LIFECYCLE_SHUTDOWN_PID_REUSED_NOT_RESOURCE_VIOLATION"
    checks["cleanup"] = gates.get("cleanup_deadline_seconds") == 15.0 and gates.get("cleanup_zero_tagged_survivors") is True
    checks["exit_codes"] = gates.get("injected_readiness_failure_exit_nonzero") is True and gates.get("normal_cycle_exit_zero") is True
    checks["bundle_audit"] = gates.get("full_cycle_bundle_required") is True and gates.get("independent_audit_required") is True
    verdict = d["verdict_rule"]
    checks["verdicts"] = all(key in verdict for key in ("PASS", "FAIL", "INCONCLUSIVE")) and verdict.get("no_posthoc_threshold_change") is True
    effect = d["terminal_effect"]
    checks["pass_effect"] = effect.get("PASS") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY"
    checks["fail_effect"] = effect.get("FAIL_OR_INCONCLUSIVE") == "REQUIRES_ROUTE_REVIEW_012_NO_BEHAVIOR_LAUNCH"
    path1 = d["path1"]
    checks["path1_progress"] = sha(ROOT / "reports/v5_path1_legalallin_v2_progress_553_20260719.json") == path1.get("progress_artifact_sha256")
    checks["path1_policy"] = path1.get("coordinator_pid") == 23720 and "NO_RESTART" in path1.get("policy", "") and "NO_GPU" in path1.get("policy", "")
    checks["no_behavior_authority"] = d.get("behavior_launch_authority") == "NONE"
    checks["official_zero"] = d.get("official_hands_authorized") == 0
    checks["no_strength"] = d.get("strength_claim") == "FORBIDDEN"
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.cpv003.preregistration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": sha(P),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
