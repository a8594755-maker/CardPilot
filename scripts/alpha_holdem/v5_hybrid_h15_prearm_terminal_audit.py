#!/usr/bin/env python3
"""Independent audit of terminal H15 pre-arm PERF-CAL failure."""
from __future__ import annotations

import argparse
import hashlib
import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import psutil

ROOT = Path(__file__).resolve().parents[2]


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--judgment", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    judgment = load(args.judgment)
    identity = judgment.get("identity", {})
    evidence = judgment.get("evidence", {})
    lifecycle = judgment.get("lifecycle", {})
    perf_path = ROOT / evidence.get("perf_cal_path", "")
    perf_audit_path = ROOT / evidence.get("perf_cal_audit_path", "")
    prereg_path = ROOT / identity.get("preregistration_path", "")
    lock_path = ROOT / identity.get("design_lock_path", "")
    preflight_path = ROOT / identity.get("preflight_path", "")
    perf = load(perf_path)
    perf_audit = load(perf_audit_path)
    prereg = load(prereg_path)
    lock = load(lock_path)
    preflight = load(preflight_path)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("judgment_identity", judgment.get("verdict") == "FAIL" and judgment.get("classification") == "H15_FAIL_PREARM_PERF_CAL_NO_LAUNCH")
    check("route_review_required", judgment.get("route_review_required") is True and judgment.get("interpretation", {}).get("next") == "ROUTE_REVIEW_013")
    check("prereg_hash", prereg_path.is_file() and sha(prereg_path) == identity.get("preregistration_sha256"))
    check("lock_hash", lock_path.is_file() and sha(lock_path) == identity.get("design_lock_sha256"))
    check("preflight_hash", preflight_path.is_file() and sha(preflight_path) == identity.get("preflight_sha256"))
    check("prereg_status", prereg.get("status") == "REGISTERED_NO_LAUNCH")
    check("lock_status", lock.get("status") == "LOCKED" and lock.get("schema_version") == "v5.hybrid.h15.design_lock.v3")
    check("preflight_status", preflight.get("overall") == "PASS_READY_H15_CONTROL_LAUNCH")
    check("perf_hash", perf_path.is_file() and sha(perf_path) == evidence.get("perf_cal_sha256"))
    check("perf_audit_hash", perf_audit_path.is_file() and sha(perf_audit_path) == evidence.get("perf_cal_audit_sha256"))
    check("perf_identity", perf.get("arm") == "control" and perf.get("classification") == "H15_PERF_CAL_FAIL" and perf.get("overall") == "FAIL_CLOSED")
    mse = [float(value) for value in perf.get("timing", {}).get("mse_seconds_per_step_samples", [])]
    smooth = [float(value) for value in perf.get("timing", {}).get("smooth_l1_seconds_per_step_samples", [])]
    ratio = statistics.median(mse) / statistics.median(smooth) if mse and smooth else -1.0
    check("ratio_recomputed", abs(ratio - float(judgment["registered_gate"]["observed"])) <= 1e-12)
    check("registered_threshold", judgment["registered_gate"].get("minimum") == 0.95 and ratio < 0.95)
    check("loss_gate_failed", perf.get("gates", {}).get("loss_throughput_ratio_pass") is False)
    check("common_gate_passed", perf.get("gates", {}).get("common_mse_baseline_ratio_pass") is True)
    check("fixed_samples", len(mse) == 3 and len(smooth) == 3 and perf.get("benchmark", {}).get("timed_steps") == 40 and perf.get("benchmark", {}).get("warmup_steps") == 10)
    check("audit_expected_failures", sorted(perf_audit.get("failed", [])) == ["loss_gate", "overall_pass"] and perf_audit.get("checks_passed") == 17 and perf_audit.get("checks_total") == 19)
    check("source_identity", perf.get("source", {}).get("sha256") == identity.get("source_checkpoint_sha256") and perf.get("source", {}).get("iteration") == 35051 and perf.get("source", {}).get("hands") == 576021901)
    check("no_behavior", perf.get("behavior_change") is False and perf.get("checkpoint_changed") is False)
    check("path1_unchanged", perf.get("path1", {}).get("coordinator_pid") == 23720 and perf.get("path1", {}).get("worker_count") == 6 and perf.get("path1", {}).get("priority") == "BelowNormal" and perf.get("path1", {}).get("changed") is False)
    check("no_forbidden_processes", perf.get("forbidden_processes") == [])
    check("lifecycle_no_launch", lifecycle.get("active_window_activated") is False and lifecycle.get("trainer_started") is False and lifecycle.get("endpoint_created") is False)
    control_dir = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h15_control_catchmse_same35051_20m_r1_20260719"
    treatment_dir = ROOT / "models/alpha_holdem_v5_hybrid/v5_hybrid_h15_treatment_catchsmoothl1b1_same35051_20m_r1_20260719"
    check("arm_dirs_absent", not control_dir.exists() and not treatment_dir.exists())
    sentinel_path = ROOT / "reports/v5_active_window.json"
    sentinel = load(sentinel_path)
    check("sentinel_not_h15", sentinel.get("terminal") is True and "H15" not in json.dumps(sentinel))
    trainers = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command:
                trainers.append(process.pid)
        except Exception:
            pass
    check("no_trainer", not trainers)
    check("no_official", perf.get("official_hands") == 0 and lifecycle.get("official_hands") == 0)
    check("no_method_inference", judgment.get("interpretation", {}).get("method_effect") == "NONE_NO_ARM_LAUNCHED")
    check("rerun_forbidden", judgment.get("interpretation", {}).get("rerun_same_gate") == "FORBIDDEN")
    failed = sorted(name for name, passed in checks.items() if not passed)
    result = {
        "schema_version": "v5.hybrid.h15.prearm_terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "judgment_sha256": sha(args.judgment),
        "classification": judgment.get("classification"),
        "trainer_pids": trainers,
        "official_hands": 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
