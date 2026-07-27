#!/usr/bin/env python3
"""Independent fail-closed audit of terminal H13 resource-isolation incident."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psutil


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    run = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h13_control_catchmse_same35051_20m_r1_20260716"
    incident_path = repo / "reports/v5_hybrid_h13_resource_isolation_incident_20260717.json"
    judgment_path = repo / "reports/v5_hybrid_h13_judgment_20260717.json"
    sentinel_path = repo / "reports/v5_active_window.json"
    recovery_path = repo / "reports/v5_h13_orphan_path1_recovery_20260717.json"
    incident = load(incident_path)
    judgment = load(judgment_path)
    sentinel = load(sentinel_path)
    recovery = load(recovery_path)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("incident_identity", incident.get("overall") == "H13_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION")
    check("judgment_identity", judgment.get("design_id") == "H13" and judgment.get("overall") == "INCONCLUSIVE" and judgment.get("classification") == incident.get("overall"))
    check("prereg_binding", incident.get("preregistration_sha256") == sha(repo / "reports/v5_hybrid_h13_preregistration_20260716.json"))
    check("lock_binding", judgment.get("design_lock_sha256") == incident.get("design_lock_sha256") == sha(repo / "reports/v5_hybrid_h13_design_lock_v2_20260716.json"))
    check("judgment_binding", incident.get("artifacts", {}).get("judgment_sha256") == sha(judgment_path))
    check("sentinel_terminal", sentinel.get("terminal") is True and sentinel.get("active") is False and sentinel.get("state") == "H13_TERMINAL_INCONCLUSIVE")
    check("sentinel_judgment", sentinel.get("judgment_sha256") == sha(judgment_path) and sentinel.get("verdict") == "INCONCLUSIVE")
    artifacts = incident.get("artifacts", {})
    paths = {
        "run_manifest": run / "run_manifest.json",
        "console_stderr": run / "console.err.log",
        "watcher_rearm_status": run / "watcher_rearm_status.json",
        "health_status": run / "h13_control_health_status.json",
        "protocol_status": run / "h13_control_protocol_status.json",
        "ordered_rearm_status": run / "h13_ordered_rearm_status.json",
        "control_perf_cal": repo / "reports/v5_hybrid_h13_control_perf_cal_20260716.json",
        "control_perf_cal_audit": repo / "reports/v5_hybrid_h13_control_perf_cal_audit_20260716.json",
    }
    for label, path in paths.items():
        check(f"artifact_{label}", path.is_file() and artifacts.get(f"{label}_sha256") == sha(path))
    manifest = load(paths["run_manifest"])
    check("zero_training_progress", manifest.get("iteration") == 35051 and manifest.get("total_hands") == 576021901 and manifest.get("status") == "initialized")
    health = load(paths["health_status"])
    check("health_fail_closed", health.get("overall") == "FAIL_CLOSED" and health.get("state") == "H13_HEALTH_PRODUCER_FAILURE" and "latest_train.log" in health.get("error", ""))
    protocol = load(paths["protocol_status"])
    violations = protocol.get("resource_isolation_violations") or []
    trigger = incident.get("trigger", {})
    check("protocol_incident", protocol.get("state") == "H13_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION" and len(violations) == 1 and protocol.get("stop_action") == "TERMINATED")
    check("trigger_full_provenance", bool(violations) and violations[0].get("pid") == trigger.get("pid") and violations[0].get("command_line_sha256") == trigger.get("command_line_sha256") and protocol.get("trigger_provenance_complete") is True)
    check("trigger_is_locked_health", bool(violations) and "v5_hybrid_h13_health_watch.py" in violations[0].get("command_line", "") and trigger.get("classification") == "FALSE_POSITIVE_REGISTERED_LIFECYCLE_PROCESS")
    ordered = load(paths["ordered_rearm_status"])
    check("ordered_rearm_fail_closed", ordered.get("overall") == "FAIL_CLOSED" and ordered.get("state") == "ORDERED_REARM_FAILURE")
    rearm = load(paths["watcher_rearm_status"])
    check("canonical_rearm_survived_initially", rearm.get("survival_pass") is True and not rearm.get("failed_watchers"))
    perf = load(paths["control_perf_cal"])
    perf_audit = load(paths["control_perf_cal_audit"])
    check("perf_supporting_only", perf.get("overall") == "PASS")
    check("perf_audit", perf_audit.get("overall") == "PASS" and perf_audit.get("artifact_sha256") == sha(paths["control_perf_cal"]))
    check("no_endpoint", not (run / "h13_control_endpoint.pt").exists())
    treatment = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h13_treatment_catchsmoothl1b1_same35051_20m_r1_20260716"
    check("no_treatment", not treatment.exists())
    mirror = repo / "reports/h13_mirror_001_v3_20260716"
    check("no_mirror_outputs", all(not (mirror / name).exists() for name in ("control.jsonl", "treatment.jsonl", "anchor.jsonl", "audit.json", "judgment.json")))
    active_h13 = []
    forbidden_eval = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        lowered = command.lower()
        if "train_v5.py" in lowered and "v5_hybrid_h13" in lowered:
            active_h13.append(process.pid)
        if any(token in lowered for token in ("play_slumbot", "v5_slumbot_benchmark", "v5_hybrid_h13_mirror")):
            forbidden_eval.append(process.pid)
    check("no_h13_trainer", not active_h13)
    check("no_evaluator_or_slumbot", not forbidden_eval)
    path1_pid = int(recovery.get("path1_restart", {}).get("coordinator_pid", -1))
    path1 = psutil.Process(path1_pid) if psutil.pid_exists(path1_pid) else None
    check("path1_recovered", path1 is not None and path1.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS and recovery.get("path1_restart", {}).get("overwrite") is False)
    check("orphan_cleanup", recovery.get("orphan_cleanup", {}).get("terminated_count") == 61 and recovery.get("orphan_cleanup", {}).get("python_process_count_after") == 0)
    check("official_zero", incident.get("official_hands") == judgment.get("official_hands") == 0)
    check("no_method_strength", incident.get("method_effect_evidence") == "NONE" and judgment.get("strength_claim") == "FORBIDDEN")
    check("terminal_disposition", incident.get("disposition", {}).get("resume_extend_reclassify") == "FORBIDDEN" and incident.get("disposition", {}).get("next").startswith("ROUTE_REVIEW_010"))
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.hybrid.h13.terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_COMPLETE_H13_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "incident_sha256": sha(incident_path),
        "judgment_sha256": sha(judgment_path),
        "sentinel_sha256": sha(sentinel_path),
        "recovery_sha256": sha(recovery_path),
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
