#!/usr/bin/env python3
"""Independent fail-closed audit of terminal H12 resource-isolation incident."""
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
    run = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h12_control_catchmse_same35051_20m_r1_20260716"
    incident_path = repo / "reports/v5_hybrid_h12_resource_isolation_incident_20260716.json"
    judgment_path = repo / "reports/v5_hybrid_h12_judgment_20260716.json"
    sentinel_path = repo / "reports/v5_active_window.json"
    incident = load(incident_path)
    judgment = load(judgment_path)
    sentinel = load(sentinel_path)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("incident_identity", incident.get("overall") == "H12_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION")
    check("judgment_identity", judgment.get("design_id") == "H12" and judgment.get("overall") == "INCONCLUSIVE" and judgment.get("classification") == incident.get("overall"))
    check("incident_binding", judgment.get("incident_sha256") == sha(incident_path))
    check("prereg_binding", judgment.get("preregistration_sha256") == sha(repo / "reports/v5_hybrid_h12_preregistration_v3_20260716.json"))
    check("lock_binding", judgment.get("design_lock_sha256") == sha(repo / "reports/v5_hybrid_h12_design_lock_v2_20260716.json"))
    check("sentinel_terminal", sentinel.get("terminal") is True and sentinel.get("active") is False and sentinel.get("state") == "H12_TERMINAL_INCONCLUSIVE")
    check("sentinel_judgment", sentinel.get("judgment_sha256") == sha(judgment_path) and sentinel.get("verdict") == "INCONCLUSIVE")
    artifacts = incident.get("artifacts", {})
    paths = {
        "run_manifest": run / "run_manifest.json",
        "console_stderr": run / "console.err.log",
        "watcher_rearm_status": run / "watcher_rearm_status.json",
        "health_status": run / "h12_control_health_status.json",
        "protocol_status": run / "h12_control_protocol_status.json",
        "ordered_rearm_status": run / "h12_ordered_rearm_status.json",
        "control_perf_cal": repo / "reports/v5_hybrid_h12_control_perf_cal_20260716.json",
        "control_perf_cal_audit": repo / "reports/v5_hybrid_h12_control_perf_cal_audit_20260716.json",
    }
    for label, path in paths.items():
        check(f"artifact_{label}", path.is_file() and artifacts.get(f"{label}_sha256") == sha(path))
    manifest = load(paths["run_manifest"])
    check("zero_training_progress", manifest.get("iteration") == 35051 and manifest.get("total_hands") == 576021901 and manifest.get("status") == "initialized")
    health = load(paths["health_status"])
    check("health_fail_closed", health.get("overall") == "FAIL_CLOSED" and health.get("state") == "H12_HEALTH_PRODUCER_FAILURE" and "latest_train.log" in health.get("error", ""))
    protocol = load(paths["protocol_status"])
    violations = protocol.get("resource_isolation_violations") or []
    check("protocol_incident", protocol.get("state") == "H12_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION" and len(violations) == 1)
    check("trigger_full_provenance", bool(violations) and violations[0].get("pid") == 41212 and violations[0].get("command_line_sha256") == incident.get("trigger", {}).get("command_line_sha256") and protocol.get("trigger_provenance_complete") is True)
    ordered = load(paths["ordered_rearm_status"])
    check("ordered_rearm_fail_closed", ordered.get("overall") == "FAIL_CLOSED" and ordered.get("state") == "ORDERED_REARM_FAILURE")
    check("trainer_stop_evidence", ordered.get("trainer_stop_actions") == [{"action": "TERMINATED", "pid": 29392}])
    rearm = load(paths["watcher_rearm_status"])
    check("canonical_survival_failed", rearm.get("survival_pass") is False and rearm.get("failed_watchers") == ["v5_hybrid_h12_ordered_rearm.py:control"])
    perf = load(paths["control_perf_cal"])
    perf_audit = load(paths["control_perf_cal_audit"])
    check("perf_supporting_only", perf.get("overall") == "PASS" and float(perf.get("timing", {}).get("smooth_l1_over_mse_throughput_ratio", 0)) >= 0.95 and judgment.get("measurements", {}).get("production_control_perf_cal", "").startswith("PASS_RATIO"))
    check("perf_audit", perf_audit.get("overall") == "PASS" and perf_audit.get("artifact_sha256") == sha(paths["control_perf_cal"]))
    check("no_endpoint", not (run / "h12_control_endpoint.pt").exists())
    treatment = repo / "models/alpha_holdem_v5_hybrid/v5_hybrid_h12_treatment_catchsmoothl1b1_same35051_20m_r1_20260716"
    check("no_treatment", not treatment.exists() and judgment.get("treatment", {}).get("launched") is False)
    mirror = repo / "reports/h12_mirror_001_v3_20260716"
    check("no_mirror_outputs", all(not (mirror / name).exists() for name in ("control.jsonl", "treatment.jsonl", "anchor.jsonl", "audit.json", "judgment.json")))
    active = []
    forbidden = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        lowered = command.lower()
        if "train_v5.py" in lowered and "v5_hybrid_h12" in lowered:
            active.append(process.pid)
        if any(token in lowered for token in ("play_slumbot", "v5_slumbot_benchmark")):
            forbidden.append(process.pid)
    check("no_h12_trainer", not active)
    check("no_slumbot", not forbidden)
    path1 = psutil.Process(37656) if psutil.pid_exists(37656) else None
    check("path1_exact", path1 is not None and path1.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS)
    check("official_zero", incident.get("official_hands") == judgment.get("official_hands") == 0)
    check("no_method_strength", judgment.get("scientific_disposition", {}).get("smoothl1_method_effect") == "NO_ESTIMATE" and judgment.get("strength_claim") == "FORBIDDEN")
    check("terminal_disposition", incident.get("disposition", {}).get("resume_extend_reclassify") == "FORBIDDEN" and judgment.get("next_transition") == "CAL_EXT_002_BEFORE_H13_THEN_ROUTE_REVIEW_009")
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.hybrid.h12.terminal_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_COMPLETE_H12_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "incident_sha256": sha(incident_path),
        "judgment_sha256": sha(judgment_path),
        "sentinel_sha256": sha(sentinel_path),
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
