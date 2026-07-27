#!/usr/bin/env python3
"""Offline audit that H15 integrates the CPV004 lifecycle contract."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/v5_h15_control_plane_integration_audit_v5_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite H15 integration audit")
    cpv_result_path = ROOT / "reports/v5_cpv004_result_20260719.json"
    cpv_audit_path = ROOT / "reports/v5_cpv004_result_audit_20260719.json"
    cpv_result = json.loads(cpv_result_path.read_text(encoding="utf-8"))
    cpv_audit = json.loads(cpv_audit_path.read_text(encoding="utf-8"))
    protocol = (ROOT / "scripts/alpha_holdem/v5_hybrid_h15_protocol_watch.py").read_text(encoding="utf-8")
    ordered = (ROOT / "scripts/alpha_holdem/v5_hybrid_h15_ordered_rearm.py").read_text(encoding="utf-8")
    treatment = (ROOT / "scripts/alpha_holdem/v5_hybrid_h15_treatment_launch_watch.py").read_text(encoding="utf-8")
    rearm = (ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1").read_text(encoding="utf-8-sig")
    launch_control = (ROOT / "scripts/alpha_holdem/v5_hybrid_h15_launch_control.ps1").read_text(encoding="utf-8-sig")
    launch_treatment = (ROOT / "scripts/alpha_holdem/v5_hybrid_h15_launch_treatment.ps1").read_text(encoding="utf-8-sig")
    trainer = (ROOT / "scripts/alpha_holdem/train_v5.py").read_text(encoding="utf-8")
    checks: dict[str, bool] = {}
    checks["cpv_result_hash"] = sha(cpv_result_path) == "69cdeedc406d5322a407cf3abd54d5f10d13d50ade87c84448b2a49dca132449"
    checks["cpv_audit_hash"] = sha(cpv_audit_path) == "b4b03759131ddfc71e04842459fafc3ea46ee684cd6de430a1c6f610cdee38cf"
    checks["cpv_pass"] = cpv_result.get("overall") == "PASS" and cpv_result.get("aggregate", {}).get("cycles_passed") == 20 and cpv_audit.get("overall") == "PASS"
    checks["protocol_guard_import"] = "from v5_lifecycle_guard_v2 import capture_process, supervisor_state" in protocol
    checks["protocol_initial_ready"] = all(token in protocol for token in ("INITIAL_READY", "initial_ready_at_epoch", "initial_ready_before_process_scan", "process_scan_started_at_epoch"))
    checks["protocol_ready_before_scan_source_order"] = protocol.index('"state": "INITIAL_READY"') < protocol.index("violations = forbidden_processes(")
    checks["protocol_supervisor_creation_identity"] = all(token in protocol for token in (
        "--allowed-supervisor-creation-time-epoch",
        "--allowed-supervisor-executable",
        "supervisor_lifecycle_state = supervisor_state(",
        'if supervisor_lifecycle_state != "LIVE"',
        "action = stop(pid)",
    ))
    checks["protocol_eight_bindings"] = all(token in protocol for token in ("creation_time", "executable", "script_sha256", "design_lock_sha256", "command_line_sha256", "role"))
    checks["ordered_creation_identity"] = "current_command_identity()" in ordered and 'supervisor["creation_time_epoch"]' in ordered and 'supervisor["executable"]' in ordered
    checks["ordered_initial_ready_wait"] = "wait_for_protocol_initial_ready" in ordered and ordered.index("wait_for_protocol_initial_ready") < ordered.index('wait_for_status(commands["protocol"][1]')
    checks["ordered_final_cleanup"] = all(token in ordered for token in ("terminate_identity_tree", "DIAGNOSTIC_ONLY_NOT_GATE", "final_survivors", "cleanup_deadline_seconds"))
    checks["safe_control_boundary"] = "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY" in treatment and "subprocess.run" not in treatment
    checks["ordered_accepts_safe_boundary"] = "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY" in ordered
    checks["canonical_h15_branch"] = all(token in rearm for token in ("$script:isHybridH15Arm", "Launch-H15OrderedRearm", "H15 exact ordered lifecycle terminally blocks every generic project path"))
    checks["canonical_h15_lock"] = "reports/v5_hybrid_h15_design_lock_v3_20260719.json" in rearm
    for label, source, seed in (("control", launch_control, "2026071905"), ("treatment", launch_treatment, "2026071906")):
        checks[f"{label}_launcher_lock"] = "v5_hybrid_h15_design_lock_v3_20260719.json" in source
        checks[f"{label}_launcher_prereg"] = "5631c27c29f1379ea16c5b246dccc312e830a2e50d5335dfac531798c882582c" in source
        checks[f"{label}_launcher_perf_seed"] = seed in source
        checks[f"{label}_launcher_exact_path1"] = "solve-v3-parallel.ts" in source and "solve-worker.ts" in source and "BelowNormal" in source
        checks[f"{label}_launcher_canonical_rearm"] = "v5_rearm_watchers.ps1" in source and "ORDERED_REARM_PASS_SUPERVISING" in source
    checks["trainer_h15_cli"] = all(token in trainer for token in ("--h15-window-arm", "--h15-catchup-loss", "--h15-preregistration", "H15 exact canonical source checkpoint identity/hash mismatch"))
    tests = [
        "scripts/alpha_holdem/test_v5_hybrid_h15_implementation.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_control_plane.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_control_plane_repairs.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_ordered_rearm.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_rearm_contract.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_health_watch.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_perf_cal.py",
        "scripts/alpha_holdem/test_v5_hybrid_h15_perf_cal_audit.py",
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=180,
    )
    checks["focused_tests_36"] = completed.returncode == 0 and "36 passed" in completed.stdout
    failed = sorted(name for name, passed in checks.items() if not passed)
    artifact = {
        "schema_version": "v5.hybrid.h15.control_plane_integration_audit.v5",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "test_stdout": completed.stdout[-4000:],
        "test_stderr": completed.stderr[-4000:],
        "tool_sha256": {
            "protocol": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h15_protocol_watch.py"),
            "ordered_rearm": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h15_ordered_rearm.py"),
            "canonical_rearm": sha(ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1"),
            "control_launcher": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h15_launch_control.ps1"),
            "treatment_launcher": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h15_launch_treatment.ps1"),
            "trainer": sha(ROOT / "scripts/alpha_holdem/train_v5.py"),
        },
        "behavior_launch_authority": "NONE_INTEGRATION_AUDIT_ONLY",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
