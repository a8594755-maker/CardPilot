#!/usr/bin/env python3
"""Offline fail-closed audit of the complete H17 control plane."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/v5_h17_control_plane_integration_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite immutable H17 integration audit")
    prereg_path = ROOT / "reports/v5_hybrid_h17_preregistration_20260719.json"
    prereg_audit_path = ROOT / "reports/v5_hybrid_h17_preregistration_audit_20260719.json"
    rr_path = ROOT / "reports/v5_hybrid_route_review_015_result_20260719.json"
    rr_audit_path = ROOT / "reports/v5_hybrid_route_review_015_result_audit_20260719.json"
    prereg = json.loads(prereg_path.read_text(encoding="utf-8"))
    prereg_audit = json.loads(prereg_audit_path.read_text(encoding="utf-8"))
    rr = json.loads(rr_path.read_text(encoding="utf-8"))
    rr_audit = json.loads(rr_audit_path.read_text(encoding="utf-8"))
    protocol = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_protocol_watch.py").read_text(encoding="utf-8")
    ordered = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_ordered_rearm.py").read_text(encoding="utf-8")
    treatment = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_treatment_launch_watch.py").read_text(encoding="utf-8")
    rearm = (ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1").read_text(encoding="utf-8-sig")
    launch_control = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_launch_control.ps1").read_text(encoding="utf-8-sig")
    launch_treatment = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_launch_treatment.ps1").read_text(encoding="utf-8-sig")
    trainer = (ROOT / "scripts/alpha_holdem/train_v5.py").read_text(encoding="utf-8")
    perf = (ROOT / "scripts/alpha_holdem/v5_hybrid_h17_perf_cal.py").read_text(encoding="utf-8")
    checks: dict[str, bool] = {}
    checks["prereg_hash"] = sha(prereg_path) == "df256560d69928c9f70e6df5457c1575cc81124ba80f34f9b15261293cefe7fc"
    checks["prereg_audit_pass"] = prereg_audit.get("overall") == "PASS" and prereg_audit.get("checks_passed") == prereg_audit.get("checks_total")
    checks["route_review_authority"] = rr.get("decision", {}).get("selected_next") == "H17_CORRECTED_DETERMINISTIC_TRIGGER_SAME_SCIENCE_BASELINE_SMOOTHL1_KERNEL" and rr.get("decision", {}).get("route_exhausted") is False and rr_audit.get("overall") == "PASS"
    checks["representative_cal_registration"] = prereg.get("representative_prearm_calibration", {}).get("rows") == 4096 and prereg.get("representative_prearm_calibration", {}).get("full_update_throughput_ratio_min") == 0.85
    checks["protocol_guard_import"] = "from v5_lifecycle_guard_v2 import capture_process, supervisor_state" in protocol
    checks["protocol_initial_ready"] = all(token in protocol for token in ("INITIAL_READY", "initial_ready_at_epoch", "initial_ready_before_process_scan", "process_scan_started_at_epoch"))
    checks["protocol_ready_before_scan_source_order"] = protocol.index('"state": "INITIAL_READY"') < protocol.index("violations = forbidden_processes(")
    checks["protocol_supervisor_creation_identity"] = all(token in protocol for token in ("--allowed-supervisor-creation-time-epoch", "--allowed-supervisor-executable", "supervisor_lifecycle_state = supervisor_state(", 'if supervisor_lifecycle_state != "LIVE"', "action = stop(pid)"))
    checks["protocol_eight_bindings"] = all(token in protocol for token in ("creation_time", "executable", "script_sha256", "design_lock_sha256", "command_line_sha256", "role"))
    checks["ordered_creation_identity"] = "current_command_identity()" in ordered and 'supervisor["creation_time_epoch"]' in ordered and 'supervisor["executable"]' in ordered
    checks["ordered_initial_ready_wait"] = "wait_for_protocol_initial_ready" in ordered and ordered.index("wait_for_protocol_initial_ready") < ordered.index('wait_for_status(commands["protocol"][1]')
    checks["ordered_final_cleanup"] = all(token in ordered for token in ("terminate_identity_tree", "DIAGNOSTIC_ONLY_NOT_GATE", "final_survivors", "cleanup_deadline_seconds"))
    checks["safe_control_boundary"] = "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY" in treatment and "subprocess.run" not in treatment
    checks["ordered_accepts_safe_boundary"] = "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY" in ordered
    checks["canonical_h17_branch"] = all(token in rearm for token in ("$script:isHybridH17Arm", "Launch-H17OrderedRearm", "H17 exact ordered lifecycle terminally blocks every generic project path"))
    checks["canonical_h17_lock"] = "reports/v5_hybrid_h17_design_lock_v1_20260719.json" in rearm
    for label, source, seed in (("control", launch_control, "2026071980"), ("treatment", launch_treatment, "2026071981")):
        checks[f"{label}_launcher_lock"] = "v5_hybrid_h17_design_lock_v1_20260719.json" in source
        checks[f"{label}_launcher_prereg"] = "df256560d69928c9f70e6df5457c1575cc81124ba80f34f9b15261293cefe7fc" in source
        checks[f"{label}_representative_perf_seed"] = seed in source
        checks[f"{label}_representative_perf_shape"] = all(token in source for token in ("--rows 4096", "--warmup-updates 2", "--timed-updates 8", "--repeats 5", "full_update_throughput_ratio"))
        checks[f"{label}_launcher_exact_path1"] = "solve-v3-parallel.ts" in source and "solve-worker.ts" in source and "BelowNormal" in source
        checks[f"{label}_launcher_canonical_rearm"] = "v5_rearm_watchers.ps1" in source and "ORDERED_REARM_PASS_SUPERVISING" in source
    checks["trainer_h17_cli"] = all(token in trainer for token in ("--h17-window-arm", "--h17-catchup-loss", "--h17-preregistration", "H17 exact canonical source checkpoint identity/hash mismatch"))
    checks["perf_full_update"] = all(token in perf for token in ("trinal_clip_ppo_update", "identity_pair", "THROUGHPUT_RATIO_MIN = 0.85", "MSE_STABILITY_RATIO_MIN = 0.95", "FORCED_OLD_LOG_PROB_OFFSET = 10.0"))
    tests = [
        "scripts/alpha_holdem/test_v5_hybrid_h17_implementation.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_control_plane.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_control_plane_repairs.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_ordered_rearm.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_rearm_contract.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_health_watch.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_perf_cal.py",
        "scripts/alpha_holdem/test_v5_hybrid_h17_perf_cal_audit.py",
    ]
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", *tests], cwd=ROOT,
        text=True, capture_output=True, timeout=180,
    )
    checks["focused_tests_36"] = completed.returncode == 0 and "36 passed" in completed.stdout
    failed = sorted(name for name, passed in checks.items() if not passed)
    artifact = {
        "schema_version": "v5.hybrid.h17.control_plane_integration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "test_stdout": completed.stdout[-4000:],
        "test_stderr": completed.stderr[-4000:],
        "tool_sha256": {
            "protocol": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h17_protocol_watch.py"),
            "ordered_rearm": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h17_ordered_rearm.py"),
            "canonical_rearm": sha(ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1"),
            "control_launcher": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h17_launch_control.ps1"),
            "treatment_launcher": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h17_launch_treatment.ps1"),
            "trainer": sha(ROOT / "scripts/alpha_holdem/train_v5.py"),
            "perf_cal": sha(ROOT / "scripts/alpha_holdem/v5_hybrid_h17_perf_cal.py"),
        },
        "behavior_launch_authority": "NONE_INTEGRATION_AUDIT_ONLY",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
