#!/usr/bin/env python3
"""Independent fail-closed audit of terminal H14 control-plane incident."""
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
    run = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h14_control_catchmse_same35051_20m_r1_20260717"
    incident_path = repo / "reports/v5_hybrid_h14_resource_isolation_incident_20260719.json"
    judgment_path = repo / "reports/v5_hybrid_h14_judgment_20260719.json"
    sentinel_path = repo / "reports/v5_active_window.json"
    recovery_path = repo / "reports/v5_h14_orphan_recovery_20260719.json"
    incident = load(incident_path)
    judgment = load(judgment_path)
    sentinel = load(sentinel_path)
    recovery = load(recovery_path)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("incident_identity", incident.get("overall") == "H14_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION")
    check("judgment_identity", judgment.get("design_id") == "H14" and judgment.get("overall") == "INCONCLUSIVE" and judgment.get("classification") == incident.get("overall"))
    check("prereg_binding", incident.get("preregistration_sha256") == sha(repo / "reports/v5_hybrid_h14_preregistration_20260717.json"))
    lock_path = repo / "reports/v5_hybrid_h14_design_lock_v6_20260717.json"
    check("lock_binding", judgment.get("design_lock_sha256") == incident.get("design_lock_sha256") == sha(lock_path))
    check("judgment_binding", incident.get("artifacts", {}).get("judgment_sha256") == sha(judgment_path))
    check("sentinel_terminal", sentinel.get("terminal") is True and sentinel.get("active") is False and sentinel.get("state") == "H14_TERMINAL_INCONCLUSIVE")
    check("sentinel_judgment", sentinel.get("judgment_sha256") == sha(judgment_path) and sentinel.get("verdict") == "INCONCLUSIVE")
    artifacts = incident.get("artifacts", {})
    paths = {
        "run_manifest": run / "run_manifest.json",
        "console_stderr": run / "console.err.log",
        "watcher_rearm_status": run / "watcher_rearm_status.json",
        "health_status": run / "h14_control_health_status.json",
        "protocol_status": run / "h14_control_protocol_status.json",
        "ordered_rearm_status": run / "h14_ordered_rearm_status.json",
        "control_perf_cal": repo / "reports/v5_hybrid_h14_control_perf_cal_20260717.json",
        "control_perf_cal_audit": repo / "reports/v5_hybrid_h14_control_perf_cal_audit_20260717.json",
        "partial_checkpoint": run / "latest.pt",
        "latest_train_log": run / "latest_train.log",
    }
    for label, path in paths.items():
        check(f"artifact_{label}", path.is_file() and artifacts.get(f"{label}_sha256") == sha(path))
    check("terminal_sentinel_binding", artifacts.get("terminal_sentinel_sha256") == sha(sentinel_path))
    check("recovery_binding", artifacts.get("recovery_sha256") == sha(recovery_path))
    manifest = load(paths["run_manifest"])
    check("partial_progress_exact", manifest.get("iteration") == 35062 and manifest.get("total_hands") == 576202673 and manifest.get("status") == "running")
    check("partial_progress_accounting", judgment.get("partial_control", {}).get("training_progress_hands") == 180772)
    health = load(paths["health_status"])
    check("health_fail_closed", health.get("overall") == "FAIL_CLOSED" and health.get("state") == "H14_HEALTH_PRODUCER_FAILURE")
    protocol = load(paths["protocol_status"])
    violations = protocol.get("resource_isolation_violations") or []
    trigger = incident.get("trigger", {})
    check("protocol_incident", protocol.get("state") == "H14_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION" and len(violations) == 1 and protocol.get("stop_action") == "ALREADY_EXITED")
    check("trigger_full_provenance", bool(violations) and violations[0].get("pid") == trigger.get("secondary_pid") and violations[0].get("command_line_sha256") == trigger.get("secondary_command_line_sha256") and protocol.get("trigger_provenance_complete") is True)
    check("trigger_pid_reuse_classified", bool(violations) and violations[0].get("token") == "allowed_supervisor_identity_mismatch" and trigger.get("classification") == "FALSE_POSITIVE_STALE_PID_ONLY_SUPERVISOR_BINDING")
    ordered = load(paths["ordered_rearm_status"])
    check("ordered_rearm_fail_closed", ordered.get("overall") == "FAIL_CLOSED" and ordered.get("state") == "ORDERED_REARM_FAILURE" and "protocol_status" in ordered.get("error", ""))
    rearm = load(paths["watcher_rearm_status"])
    check("canonical_launcher_rearm_survived_initially", rearm.get("survival_pass") is True and not rearm.get("failed_watchers"))
    perf = load(paths["control_perf_cal"])
    perf_audit = load(paths["control_perf_cal_audit"])
    check("perf_supporting_only", perf.get("overall") == "PASS")
    check("perf_audit", perf_audit.get("overall") == "PASS" and perf_audit.get("artifact_sha256") == sha(paths["control_perf_cal"]))
    check("no_endpoint", not (run / "h14_control_endpoint.pt").exists())
    treatment = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h14_treatment_catchsmoothl1b1_same35051_20m_r1_20260717"
    check("no_treatment", not treatment.exists())
    mirror = repo / "reports/h14_mirror_001_v3_20260717"
    check("no_mirror_outputs", all(not (mirror / name).exists() for name in ("control.jsonl", "treatment.jsonl", "anchor.jsonl", "audit.json", "judgment.json")))
    active_h14: list[int] = []
    forbidden_eval: list[int] = []
    orphan_children: list[int] = []
    for process in psutil.process_iter(["pid", "ppid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        lowered = command.lower()
        if "train_v5.py" in lowered and "v5_hybrid_h14" in lowered:
            active_h14.append(process.pid)
        if any(token in lowered for token in ("play_slumbot", "v5_slumbot_benchmark", "v5_hybrid_h14_mirror")):
            forbidden_eval.append(process.pid)
        if process.info.get("ppid") == 16544 and "multiprocessing.spawn" in lowered:
            orphan_children.append(process.pid)
    check("no_h14_trainer", not active_h14)
    check("no_evaluator_or_slumbot", not forbidden_eval)
    check("orphan_cleanup", recovery.get("orphan_cleanup", {}).get("terminated_count") == 21 and recovery.get("orphan_cleanup", {}).get("python_process_count_after") == 0 and not orphan_children)
    check("path1_not_restarted", recovery.get("path1", {}).get("alive_at_recovery_check") is False and recovery.get("path1", {}).get("action") == "NONE")
    check("official_zero", incident.get("official_hands") == judgment.get("official_hands") == 0)
    check("no_method_strength", incident.get("method_effect_evidence") == "NONE" and judgment.get("strength_claim") == "FORBIDDEN")
    check("terminal_disposition", incident.get("disposition", {}).get("resume_extend_reclassify") == "FORBIDDEN" and incident.get("disposition", {}).get("next").startswith("ROUTE_REVIEW_011"))
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.hybrid.h14.terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_COMPLETE_H14_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION" if not failed else "FAIL_CLOSED",
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
