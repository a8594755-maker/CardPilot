#!/usr/bin/env python3
"""H6 registered first60-throughput and sustained-entropy abort watcher."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}


def rows(path: Path) -> list[dict]:
    try:
        with path.open(encoding="utf-8") as stream:
            return [json.loads(line) for line in stream if line.strip()]
    except Exception:
        return []


def write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp.replace(path)


def effective(values: list[dict]) -> float | None:
    sample = values[1:61]
    if len(sample) < 60:
        return None
    elapsed = (datetime.fromisoformat(sample[-1]["recorded_at"]) - datetime.fromisoformat(sample[0]["recorded_at"])).total_seconds()
    return (int(sample[-1]["hands"]) - int(sample[0]["hands"])) / elapsed if elapsed > 0 else None


def stop(pid: int) -> str:
    try:
        process = psutil.Process(pid)
        process.terminate()
        process.wait(20)
        return "TERMINATED"
    except psutil.TimeoutExpired:
        process.kill()
        process.wait(10)
        return "KILLED_AFTER_TIMEOUT"
    except psutil.NoSuchProcess:
        return "ALREADY_EXITED"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    lock_path = args.design_lock.resolve()
    status_path = args.status_json.resolve()
    lock = load(lock_path)
    errors = []
    if not lock_path.is_file() or sha256(lock_path) != args.expected_lock_sha256.lower():
        errors.append("lock SHA mismatch")
    if lock.get("design_id") != "H6" or lock.get("status") != "LOCKED":
        errors.append("lock identity/status")
    treatment = lock.get("arms", {}).get("treatment", {})
    if not treatment:
        errors.append("treatment missing")
    if errors:
        write(status_path, {"overall": "FAIL", "state": "STATIC_CONTRACT_FAILURE", "errors": errors})
        return 2
    if args.validate_only:
        write(status_path, {"overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS"})
        return 0

    run_dir = Path(treatment["run_dir"])
    control_metrics = Path(lock["arms"]["control"]["metrics_path"])
    while True:
        manifest = load(run_dir / "run_manifest.json")
        treatment_rows = rows(run_dir / "h1_training_metrics.jsonl")
        if not manifest:
            write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_TREATMENT"})
            time.sleep(max(1, args.poll_seconds))
            continue
        pid = int(manifest.get("process_id", -1))
        if len(treatment_rows) >= 20 and all(float(item.get("entropy", 99)) < 0.3 for item in treatment_rows[-20:]):
            action = stop(pid)
            write(status_path, {"overall": "FAIL", "state": "H6_FAIL_PROTOCOL_ABORT_ENTROPY20", "pid": pid, "stop_action": action, "rows": len(treatment_rows)})
            return 3

        first60 = {"status": "PENDING", "rows": len(treatment_rows)}
        first_done = False
        if len(treatment_rows) >= 61:
            treatment_hps = effective(treatment_rows)
            control_hps = effective(rows(control_metrics))
            if control_hps is None:
                write(status_path, {"overall": "FAIL", "state": "CONTROL_FIRST60_INVALID"})
                return 2
            ratio = treatment_hps / control_hps if treatment_hps and control_hps else None
            first60 = {
                "status": "PASS" if ratio is not None and ratio >= 0.85 else "FAIL",
                "control_effective_hps": control_hps,
                "treatment_effective_hps": treatment_hps,
                "ratio": ratio,
                "minimum": 0.85,
                "rows_used": [2, 61],
            }
            first_done = True
            if first60["status"] == "FAIL":
                action = stop(pid)
                write(status_path, {
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "overall": "FAIL",
                    "state": "H6_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT",
                    "pid": pid,
                    "stop_action": action,
                    "first60": first60,
                    "official_hands": 0,
                })
                return 3
        state = "TREATMENT_RUNNING_GUARDS_PASS" if manifest.get("status") in {"initialized", "running"} else "TREATMENT_FINISHED_GUARDS_PASS"
        overall = "PASS" if manifest.get("status") == "finished" and first_done else "PENDING"
        write(status_path, {
            "schema_version": "v5.hybrid.h6.protocol_status.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": overall,
            "state": state,
            "pid": pid,
            "rows": len(treatment_rows),
            "first60": first60,
            "entropy20_abort": False,
            "official_hands": 0,
        })
        if manifest.get("status") == "finished":
            return 0 if first_done else 2
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
