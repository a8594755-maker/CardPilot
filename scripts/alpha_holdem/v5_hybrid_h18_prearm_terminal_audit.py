#!/usr/bin/env python3
"""Independent terminal audit for H18 pre-arm calibration failure."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[2]
REPORTS = ROOT / "reports"
OUT = REPORTS / "v5_hybrid_h18_prearm_terminal_audit_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite immutable H18 terminal audit")
    paths = {
        "prereg": REPORTS / "v5_hybrid_h18_preregistration_20260719.json",
        "lock": REPORTS / "v5_hybrid_h18_design_lock_v1_20260719.json",
        "lock_audit": REPORTS / "v5_hybrid_h18_design_lock_audit_v1_20260719.json",
        "preflight": REPORTS / "v5_hybrid_h18_preflight_v1_20260719.json",
        "perf": REPORTS / "v5_hybrid_h18_control_perf_cal_20260719.json",
        "perf_audit": REPORTS / "v5_hybrid_h18_control_perf_cal_audit_20260719.json",
        "judgment": REPORTS / "v5_hybrid_h18_judgment_20260719.json",
    }
    expected = {
        "prereg": "8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481",
        "lock": "d82e6d8da6cd787e7f972e295344396ce35ad3828963fbfa9472548e5f9e3c7e",
        "lock_audit": "22ea9eb1a1d00f9f13233dba06c2176c26e4b9606bee3d47d106e2594bafba44",
        "preflight": "9e30127b9138247971be29aab8ac6d8efd2aa83e3bb0f3e5c00bdf5d2c352967",
        "perf": "cfee97ba4d8432aa87f2ebe69ab6e315b8a07d8b35981b99f46cb2154ce58d59",
        "perf_audit": "849357b609421b5cbceb7456879df2ca1eeb752adb5636b5ba42b018322406d3",
        "judgment": "2adcda7fa166f997f621827dd51a6475adba80d16282cd4e839805bc43156927",
    }
    checks: dict[str, bool] = {
        f"{name}_hash": path.is_file() and sha(path) == expected[name]
        for name, path in paths.items()
    }
    prereg, lock, lock_audit = load(paths["prereg"]), load(paths["lock"]), load(paths["lock_audit"])
    preflight, perf, perf_audit, judgment = (
        load(paths["preflight"]), load(paths["perf"]), load(paths["perf_audit"]), load(paths["judgment"])
    )
    checks["registered_failure_action"] = prereg["representative_prearm_calibration"]["failure_action"] == "FAIL_CLOSED_NO_ARM_LAUNCH_AND_ROUTE_REVIEW016"
    checks["lock_and_audit_pass"] = lock.get("status") == "LOCKED" and lock_audit.get("overall") == "PASS_IMMUTABLE_H18_DESIGN_LOCK"
    checks["preflight_pass"] = preflight.get("overall") == "PASS_READY_H18_CONTROL_LAUNCH"
    checks["perf_registered_gate_fail"] = (
        perf.get("overall") == "FAIL_CLOSED"
        and perf.get("classification") == "H18_REPRESENTATIVE_PERF_CAL_FAIL"
        and perf.get("gates", {}).get("full_update_throughput_ratio_pass") is True
        and perf.get("gates", {}).get("mse_repeat_stability_ratio_pass") is False
        and perf.get("gates", {}).get("numerical_gradient_actor_scope_identity_pass") is False
        and perf.get("identity", {}).get("forced_kl_and_three_catchup_epochs") is True
    )
    checks["perf_audit_fail_closed"] = perf_audit.get("overall") == "FAIL_CLOSED" and perf_audit.get("artifact_sha256") == expected["perf"]
    checks["judgment_identity"] = judgment.get("verdict") == "FAIL" and judgment.get("classification") == "H18_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_GATE_NO_LAUNCH"
    control = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h18_control_catchmse_same35051_20m_r1_20260719"
    treatment = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h18_treatment_catchsmoothl1b1_same35051_20m_r1_20260719"
    checks["arm_dirs_absent"] = not control.exists() and not treatment.exists()
    sentinel_path = REPORTS / "v5_active_window.json"
    sentinel = load(sentinel_path) if sentinel_path.is_file() else {}
    checks["sentinel_not_h18_active"] = not (sentinel.get("design_id") == "H18" and sentinel.get("terminal") is not True)
    trainers = []
    forbidden = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or []).replace("\\", "/").lower()
            if "scripts/alpha_holdem/train_v5.py" in command:
                trainers.append(process.pid)
            if any(token in command for token in ("v5_hybrid_h18_mirror.py", "v5_slumbot", "play_slumbot")):
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
        "schema_version": "v5.hybrid.h18.prearm_terminal_audit.v1",
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
