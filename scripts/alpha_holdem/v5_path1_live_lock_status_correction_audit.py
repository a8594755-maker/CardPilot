#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import psutil


ROOT = Path(__file__).resolve().parents[2]
ARTIFACT = ROOT / "reports/v5_path1_live_lock_status_correction_20260719.json"
OUT = ROOT / "reports/v5_path1_live_lock_status_correction_audit_v2_20260719.json"
ASSET = ROOT / "data/cfr/pipeline_v3_hu_srp_200bb_legalallin_v2"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    value = json.loads(ARTIFACT.read_text(encoding="utf-8"))
    progress_path = ROOT / value["authoritative_progress"]["artifact"]
    progress = json.loads(progress_path.read_text(encoding="utf-8"))
    status_path = ASSET / "path1-solver-status.json"
    status = json.loads(status_path.read_text(encoding="utf-8"))
    identity = value["live_identity"]
    checks = {
        "schema": value.get("schema_version") == "v5.path1.live_lock_status_correction.v1",
        "classification": value.get("overall") == "PASS_REPORTING_CORRECTION_LIVE_JOB_UNTOUCHED",
        "failed_status_hash": sha(status_path) == value["failed_status"]["sha256"],
        "failed_status_payload": status.get("status") == "FAIL_CLOSED_PREFLIGHT" and status.get("pid") == 11228 and "live lock" in status.get("error", ""),
        "progress_hash": sha(progress_path) == value["authoritative_progress"]["sha256"],
        "progress_pass": progress.get("overall") == "PASS" and progress.get("complete_gzip_meta_pairs") == 553 and progress.get("qa_pass_zero_illegal_postallin_latest_unique") == 553,
        "asset_lock": progress.get("asset_lock_sha256") == "ddc57ea13d9bd02cdc41f40832aa08b07b82b03267d1540b4745abb3b60174d4",
        "coordinator_identity": progress.get("coordinator_alive") is True and progress.get("coordinator_pid") == identity["coordinator_pid"] and "pipeline_srp_v3_200bb" in identity.get("command_contract", ""),
        "coordinator_priority": progress.get("priority") == identity.get("priority") == "BelowNormal",
        "six_workers": progress.get("solver_worker_count") == 6 and progress.get("solver_worker_pids") == identity["worker_pids"],
        "workers_priority_snapshot": identity.get("workers_priority") == "BelowNormal",
        "no_restart": identity.get("restart_performed") is False and identity.get("process_touched") is False,
        "stale_operation": value.get("operational_classification") == "STALE_OPERATIONAL_STATE_NO_RESTART_EXACT_JOB_ALREADY_RUNNING",
        "no_behavior": value.get("asset_behavior_change") is False and value.get("training_ingestion") == "FORBIDDEN",
        "official_zero": value.get("official_hands") == 0 and value.get("strength_claim") == "FORBIDDEN",
    }
    failed = [name for name, passed in checks.items() if not passed]
    result = {
        "schema_version": "v5.path1.live_lock_status_correction_audit.v2",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha(ARTIFACT),
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "official_hands": 0,
    }
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
