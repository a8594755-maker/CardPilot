#!/usr/bin/env python3
"""Independent terminal audit for H16 pre-arm calibration failure."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
OUT = REPORTS / "v5_hybrid_h16_prearm_terminal_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite immutable H16 terminal audit")
    paths = {
        "prereg": REPORTS / "v5_hybrid_h16_preregistration_20260719.json",
        "lock": REPORTS / "v5_hybrid_h16_design_lock_v1_20260719.json",
        "lock_audit": REPORTS / "v5_hybrid_h16_design_lock_audit_v1_20260719.json",
        "preflight": REPORTS / "v5_hybrid_h16_preflight_v1_20260719.json",
        "perf": REPORTS / "v5_hybrid_h16_control_perf_cal_20260719.json",
        "perf_audit": REPORTS / "v5_hybrid_h16_control_perf_cal_audit_20260719.json",
        "judgment": REPORTS / "v5_hybrid_h16_judgment_20260719.json",
    }
    expected = {
        "prereg": "51065761b6b291ef757ea467611203cbe79d45a5e4d54c163edaf79ef8fa1bb0",
        "lock": "c5e6ac1bb44a106c296652de54401390c631bc1ec12efa0f0aae83d237650faf",
        "lock_audit": "072440ce60aaf64a9ee97413a37931f6ee676470f5792c6ecb9081837edab9ed",
        "preflight": "c480ae1387eccc4ef0965de2eca0bfb59321daed6935e92fe4c790097ef2c81d",
        "perf": "2350872161547b969bd4f2f3837114c92cbd93817a02ec63fff77cd8e9bcc80f",
        "perf_audit": "04b8ad68415cfd883457de533e51a0ef0829787b3978a5dba393ab672028a1b7",
        "judgment": "96e0a4bea8c119c991ad1cd2710e7897d7938a161451e7cf7fec65400a8c86d0",
    }
    checks: dict[str, bool] = {
        f"{name}_hash": path.is_file() and sha(path) == expected[name]
        for name, path in paths.items()
    }
    prereg, lock, lock_audit = load(paths["prereg"]), load(paths["lock"]), load(paths["lock_audit"])
    preflight, perf, perf_audit, judgment = (
        load(paths["preflight"]), load(paths["perf"]), load(paths["perf_audit"]), load(paths["judgment"])
    )
    checks["registered_failure_action"] = "FAIL_CLOSED_NO_ARM_LAUNCH_AND_SELECT_PCV005" in prereg["representative_prearm_calibration"]["failure_action"]
    checks["lock_and_audit_pass"] = lock.get("status") == "LOCKED" and lock_audit.get("overall") == "PASS_IMMUTABLE_H16_DESIGN_LOCK"
    checks["preflight_pass"] = preflight.get("overall") == "PASS_READY_H16_CONTROL_LAUNCH"
    checks["perf_execution_fail"] = perf.get("overall") == "FAIL_CLOSED" and perf.get("classification") == "H16_REPRESENTATIVE_PERF_CAL_EXECUTION_FAILURE" and "forced-KL/catch-up shape" in perf.get("error", "")
    checks["perf_audit_fail_closed"] = perf_audit.get("overall") == "FAIL_CLOSED" and perf_audit.get("artifact_sha256") == expected["perf"]
    checks["judgment_identity"] = judgment.get("verdict") == "FAIL" and judgment.get("classification") == "H16_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_EXECUTION_NO_LAUNCH"
    control = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h16_control_catchmse_same35051_20m_r1_20260719"
    treatment = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h16_treatment_catchsmoothl1b1_same35051_20m_r1_20260719"
    checks["arm_dirs_absent"] = not control.exists() and not treatment.exists()
    sentinel_path = REPORTS / "v5_active_window.json"
    sentinel = load(sentinel_path) if sentinel_path.is_file() else {}
    checks["sentinel_not_h16_active"] = not (sentinel.get("design_id") == "H16" and sentinel.get("terminal") is not True)
    trainers = []
    forbidden = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).replace("\\", "/").lower()
            if "scripts/alpha_holdem/train_v5.py" in command:
                trainers.append(process.pid)
            if any(token in command for token in ("v5_hybrid_h16_mirror.py", "v5_slumbot", "play_slumbot")):
                forbidden.append(process.pid)
        except psutil.Error:
            pass
    checks["no_trainer"] = not trainers
    checks["no_evaluator_or_slumbot"] = not forbidden
    path1 = psutil.Process(23720)
    path1_workers = []
    for child in path1.children(recursive=False):
        try:
            if "solve-worker.ts" in " ".join(child.cmdline()).replace("\\", "/"):
                path1_workers.append(child.pid)
        except psutil.Error:
            pass
    checks["path1_unchanged"] = path1.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS and len(path1_workers) == 6
    checks["no_method_inference"] = judgment["interpretation"]["method_effect"] == "NONE_NO_ARM_LAUNCHED"
    checks["rerun_forbidden"] = judgment["interpretation"]["rerun_same_gate"] == "FORBIDDEN"
    checks["route_review_required"] = judgment.get("route_review_required") is True
    checks["no_official"] = judgment["lifecycle"]["official_hands"] == 0
    failed = sorted(name for name, passed in checks.items() if not passed)
    artifact = {
        "schema_version": "v5.hybrid.h16.prearm_terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": judgment.get("classification"),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "judgment_sha256": expected["judgment"],
        "trainer_pids": trainers,
        "forbidden_process_pids": forbidden,
        "path1": {"coordinator_pid": 23720, "worker_pids": path1_workers, "priority": "BelowNormal"},
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(artifact, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(artifact, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
