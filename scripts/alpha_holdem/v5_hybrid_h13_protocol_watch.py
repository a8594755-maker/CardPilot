#!/usr/bin/env python3
"""H13 throughput, entropy and full-provenance resource-isolation watcher."""
from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


FORBIDDEN_PROCESS_TOKENS = (
    "v5_hybrid_h13_mirror.py", "v5_h1_calibration.py", "v5_slumbot",
    "play_slumbot", "slumbot_match", "v5_mirror_eval.py",
)
ALLOWED_ACTIVE_WINDOW_TOKENS = (
    "scripts/alpha_holdem/train_v5.py",
    "scripts/alpha_holdem/v5_hybrid_h13_endpoint_watch.py",
    "scripts/alpha_holdem/v5_hybrid_h13_protocol_watch.py",
    "scripts/alpha_holdem/v5_hybrid_h13_treatment_launch_watch.py",
    "scripts/alpha_holdem/v5_hybrid_h13_completion_watch.py",
    "scripts/alpha_holdem/v5_hybrid_h13_active_window.py",
    "scripts/alpha_holdem/v5_hybrid_h13_launch_control.ps1",
    "scripts/alpha_holdem/v5_hybrid_h13_launch_treatment.ps1",
    "scripts/alpha_holdem/v5_rearm_watchers.ps1",
    "packages/cfr-solver/src/scripts/solve-v3-parallel.ts",
    "packages/cfr-solver/src/orchestration/solve-worker.ts",
    "scripts/qa-200bb-board.mjs",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_sha(command: str) -> str:
    return hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()


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
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for attempt in range(5):
        try:
            temporary.replace(path)
            return
        except PermissionError:
            if attempt == 4:
                raise
            time.sleep(0.05 * (attempt + 1))


def effective(values: list[dict], first60: bool = True) -> float | None:
    sample = values[1:61] if first60 else values[1:]
    if len(sample) < (60 if first60 else 2):
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


def process_provenance(process: psutil.Process, command: str) -> dict:
    try:
        executable = process.exe()
    except Exception:
        executable = ""
    try:
        parent_pid = process.ppid()
    except Exception:
        parent_pid = -1
    try:
        created_epoch = process.create_time()
        created_at = datetime.fromtimestamp(created_epoch, timezone.utc).isoformat()
    except Exception:
        created_epoch = None
        created_at = None
    return {
        "pid": process.pid,
        "parent_pid": parent_pid,
        "creation_time_epoch": created_epoch,
        "creation_time_utc": created_at,
        "executable": executable,
        "command_line": command,
        "command_line_sha256": command_sha(command),
    }


def forbidden_processes(
    trainer_pid: int,
    allowed_supervisor_pid: int | None = None,
    allowed_supervisor_command_sha256: str | None = None,
) -> list[dict]:
    found: list[dict] = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            if process.pid == trainer_pid:
                continue
            command = " ".join(process.info.get("cmdline") or [])
            normalized = command.replace("\\", "/").lower()
            if process.pid == allowed_supervisor_pid:
                if allowed_supervisor_command_sha256 and command_sha(command) == allowed_supervisor_command_sha256:
                    continue
                found.append({**process_provenance(process, command), "token": "allowed_supervisor_identity_mismatch"})
                continue
            direct = next((token for token in FORBIDDEN_PROCESS_TOKENS if token in normalized), None)
            if direct:
                found.append({**process_provenance(process, command), "token": direct})
                continue
            is_cardpilot_project_process = (
                "/cardpilot/" in normalized
                and any(name in normalized for name in ("python", "node", "powershell"))
            )
            allowed = any(token in normalized for token in ALLOWED_ACTIVE_WINDOW_TOKENS)
            if is_cardpilot_project_process and not allowed:
                found.append({**process_provenance(process, command), "token": "unregistered_cardpilot_project_process"})
        except Exception:
            continue
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=["control", "treatment"], required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--allowed-supervisor-pid", type=int)
    parser.add_argument("--allowed-supervisor-command-sha256")
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    lock_path = args.design_lock.resolve()
    lock = load(lock_path)
    status_path = args.status_json.resolve()
    arm = lock.get("arms", {}).get(args.arm, {})
    errors = []
    if not lock_path.is_file() or sha(lock_path) != args.expected_lock_sha256.lower():
        errors.append("lock SHA mismatch")
    if lock.get("design_id") != "H13" or lock.get("status") != "LOCKED":
        errors.append("lock identity/status")
    if not arm:
        errors.append("arm missing")
    if lock.get("resource_isolation", {}).get("full_trigger_provenance") != [
        "pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"
    ]:
        errors.append("full trigger provenance contract missing")
    if errors:
        write(status_path, {"overall": "FAIL", "state": "STATIC_CONTRACT_FAILURE", "errors": errors})
        return 2
    if args.validate_only:
        write(status_path, {"overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS", "arm": args.arm})
        return 0
    if args.allowed_supervisor_pid is None or not args.allowed_supervisor_command_sha256:
        write(status_path, {"overall": "FAIL", "state": "STATIC_CONTRACT_FAILURE", "errors": ["exact ordered supervisor identity required"]})
        return 2
    run_dir = Path(arm["run_dir"])
    control_dir = Path(lock["arms"]["control"]["run_dir"])
    while True:
        manifest = load(run_dir / "run_manifest.json")
        values = rows(run_dir / "h1_training_metrics.jsonl")
        if not manifest:
            write(status_path, {"overall": "PENDING", "state": "WAITING_FOR_ARM", "arm": args.arm})
            time.sleep(max(1, args.poll_seconds))
            continue
        pid = int(manifest.get("process_id", -1))
        violations = forbidden_processes(pid, args.allowed_supervisor_pid, args.allowed_supervisor_command_sha256)
        if violations:
            action = stop(pid)
            write(status_path, {
                "schema_version": "v5.hybrid.h13.protocol_status.v1",
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": "FAIL",
                "state": "H13_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION",
                "arm": args.arm,
                "pid": pid,
                "stop_action": action,
                "resource_isolation_violations": violations,
                "trigger_provenance_complete": all(all(key in item for key in (
                    "pid", "parent_pid", "creation_time_utc", "executable", "command_line", "command_line_sha256"
                )) for item in violations),
                "official_hands": 0,
            })
            return 3
        if len(values) >= 20 and all(float(item.get("entropy", 99)) < 0.3 for item in values[-20:]):
            action = stop(pid)
            write(status_path, {"overall": "FAIL", "state": "H13_FAIL_PROTOCOL_ABORT_ENTROPY20", "arm": args.arm, "pid": pid, "stop_action": action, "resource_isolation_violations": []})
            return 3
        first = {"status": "PENDING", "rows": len(values)}
        first_done = False
        if len(values) >= 61:
            own = effective(values)
            if args.arm == "control":
                first = {"status": "PASS_CONTROL_BASELINE_FROZEN", "effective_hps": own, "rows_used": [2, 61]}
                first_done = True
            else:
                baseline = effective(rows(control_dir / "h1_training_metrics.jsonl"))
                ratio = own / baseline if own and baseline else None
                first = {"status": "PASS" if ratio is not None and ratio >= 0.85 else "FAIL", "control_effective_hps": baseline, "treatment_effective_hps": own, "ratio": ratio, "minimum": 0.85, "rows_used": [2, 61]}
                first_done = True
                if first["status"] == "FAIL":
                    action = stop(pid)
                    write(status_path, {"overall": "FAIL", "state": "H13_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT", "arm": args.arm, "pid": pid, "stop_action": action, "first60": first, "resource_isolation_violations": []})
                    return 3
        state = "ARM_RUNNING_GUARDS_PASS" if manifest.get("status") in {"initialized", "running"} else "ARM_FINISHED_GUARDS_PASS"
        write(status_path, {
            "schema_version": "v5.hybrid.h13.protocol_status.v1",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS" if manifest.get("status") == "finished" and first_done else "PENDING",
            "state": state,
            "arm": args.arm,
            "pid": pid,
            "rows": len(values),
            "first60": first,
            "entropy20_abort": False,
            "resource_isolation_violations": [],
            "trigger_provenance_complete": True,
            "official_hands": 0,
        })
        if manifest.get("status") == "finished":
            return 0 if first_done else 2
        time.sleep(max(1, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
