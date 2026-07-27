#!/usr/bin/env python3
"""Lock-bound dependency-ordered watcher supervisor for H12."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


SCHEMA = "v5.hybrid.h12.ordered_rearm_status.v1"
STAGES = {
    "control": (("health", "protocol"), ("endpoint",), ("treatment_launch", "completion")),
    "treatment": (("health", "protocol"), ("endpoint",), ("completion",)),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def current_command_identity() -> tuple[int, str]:
    process = psutil.Process(os.getpid())
    command = " ".join(process.cmdline())
    return process.pid, hashlib.sha256(command.encode("utf-8", errors="replace")).hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def stage_plan(arm: str) -> tuple[tuple[str, ...], ...]:
    return STAGES[arm]


def fresh_status(value: dict[str, Any], lock_sha: str, allowed_states: set[str]) -> bool:
    return (
        value.get("design_lock_sha256") == lock_sha
        and value.get("state") in allowed_states
        and value.get("overall") in {"PASS", "PENDING"}
    )


def preserve_status(path: Path, preserve_dir: Path, label: str) -> dict[str, Any]:
    if not path.is_file():
        return {"path": str(path), "present": False}
    preserve_dir.mkdir(parents=True, exist_ok=True)
    target = preserve_dir / f"{label}-{path.name}"
    if target.exists():
        raise FileExistsError(target)
    shutil.copy2(path, target)
    original_hash = sha256(path)
    path.unlink()
    return {
        "path": str(path.resolve()),
        "present": True,
        "sha256": original_hash,
        "preserved_path": str(target.resolve()),
        "preserved_sha256": sha256(target),
    }


def active_h12_trainers() -> list[int]:
    result = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command and "v5_hybrid_h12_" in command:
                result.append(process.pid)
        except psutil.Error:
            continue
    return result


def terminate_trainers() -> list[dict[str, Any]]:
    actions = []
    for pid in active_h12_trainers():
        try:
            process = psutil.Process(pid)
            process.terminate()
            process.wait(20)
            actions.append({"pid": pid, "action": "TERMINATED"})
        except psutil.TimeoutExpired:
            process.kill()
            process.wait(10)
            actions.append({"pid": pid, "action": "KILLED_AFTER_TIMEOUT"})
        except psutil.NoSuchProcess:
            actions.append({"pid": pid, "action": "ALREADY_EXITED"})
    return actions


def command_map(repo: Path, run_dir: Path, arm: str, lock_path: Path, lock_sha: str) -> dict[str, tuple[list[str], Path, Path, Path]]:
    python = sys.executable
    control_dir = Path(load(lock_path)["arms"]["control"]["run_dir"])
    treatment_dir = Path(load(lock_path)["arms"]["treatment"]["run_dir"])
    common = ["--design-lock", str(lock_path), "--expected-lock-sha256", lock_sha]
    supervisor_pid, supervisor_command_sha = current_command_identity()
    return {
        "health": (
            [python, "-u", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_health_watch.py"), "--run-dir", str(run_dir), "--arm", arm, *common, "--status-json", str(run_dir / f"h12_{arm}_health_status.json"), "--poll-seconds", "15"],
            run_dir / f"h12_{arm}_health_status.json", run_dir / f"h12_{arm}_health_watch.out.log", run_dir / f"h12_{arm}_health_watch.err.log",
        ),
        "protocol": (
            [python, "-u", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_protocol_watch.py"), "--arm", arm, *common, "--status-json", str(run_dir / f"h12_{arm}_protocol_status.json"), "--poll-seconds", "15", "--allowed-supervisor-pid", str(supervisor_pid), "--allowed-supervisor-command-sha256", supervisor_command_sha],
            run_dir / f"h12_{arm}_protocol_status.json", run_dir / f"h12_{arm}_protocol_watch.out.log", run_dir / f"h12_{arm}_protocol_watch.err.log",
        ),
        "endpoint": (
            [python, "-u", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_endpoint_watch.py"), "--arm", arm, *common, "--status-json", str(run_dir / f"h12_{arm}_endpoint_status.json"), "--poll-seconds", "15"],
            run_dir / f"h12_{arm}_endpoint_status.json", run_dir / f"h12_{arm}_endpoint_watch.out.log", run_dir / f"h12_{arm}_endpoint_watch.err.log",
        ),
        "treatment_launch": (
            [python, "-u", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_treatment_launch_watch.py"), "--control-dir", str(control_dir), "--treatment-dir", str(treatment_dir), "--launcher", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_launch_treatment.ps1"), "--design-lock", str(lock_path), "--expected-lock-sha256", lock_sha, "--status-json", str(control_dir / "h12_treatment_launch_watch_status.json"), "--poll-seconds", "15"],
            control_dir / "h12_treatment_launch_watch_status.json", control_dir / "h12_treatment_launch_watch.out.log", control_dir / "h12_treatment_launch_watch.err.log",
        ),
        "completion": (
            [python, "-u", str(repo / "scripts/alpha_holdem/v5_hybrid_h12_completion_watch.py"), "--repo", str(repo), *common, "--status-json", str(run_dir / "h12_completion_watch_status.json"), "--poll-seconds", "15"],
            run_dir / "h12_completion_watch_status.json", run_dir / "h12_completion_watch.out.log", run_dir / "h12_completion_watch.err.log",
        ),
    }


def wait_for_status(path: Path, lock_sha: str, states: set[str], timeout_seconds: float, child: subprocess.Popen[Any]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if child.poll() is not None:
            raise RuntimeError(f"watcher exited before readiness: {path.name} exit={child.returncode}")
        value = load(path)
        if fresh_status(value, lock_sha, states):
            return value
        if value.get("overall") in {"FAIL", "FAIL_CLOSED"}:
            raise RuntimeError(f"watcher failed before readiness: {path.name} {value}")
        time.sleep(0.25)
    raise TimeoutError(f"watcher readiness timeout: {path.name}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "treatment"), required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--readiness-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    repo = args.repo.resolve()
    run_dir = args.run_dir.resolve()
    lock_path = args.design_lock.resolve()
    status_path = args.status_json.resolve()
    children: dict[str, subprocess.Popen[Any]] = {}
    logs: list[Any] = []
    try:
        if not lock_path.is_file() or sha256(lock_path) != args.expected_lock_sha256.lower():
            raise ValueError("design lock SHA mismatch")
        lock = load(lock_path)
        if lock.get("design_id") != "H12" or lock.get("status") != "LOCKED":
            raise ValueError("design lock identity/status")
        arm = lock.get("arms", {}).get(args.arm, {})
        if Path(arm.get("run_dir", "")).resolve() != run_dir:
            raise ValueError("run directory is not the locked arm")
        expected_plan = [list(stage) for stage in stage_plan(args.arm)]
        if lock.get("control_plane", {}).get("ordered_rearm_stages", {}).get(args.arm) != expected_plan:
            raise ValueError("ordered rearm stages missing from lock")
        commands = command_map(repo, run_dir, args.arm, lock_path, sha256(lock_path))
        tool_keys = {
            "health": "scripts/alpha_holdem/v5_hybrid_h12_health_watch.py",
            "protocol": "scripts/alpha_holdem/v5_hybrid_h12_protocol_watch.py",
            "endpoint": "scripts/alpha_holdem/v5_hybrid_h12_endpoint_watch.py",
            "treatment_launch": "scripts/alpha_holdem/v5_hybrid_h12_treatment_launch_watch.py",
            "completion": "scripts/alpha_holdem/v5_hybrid_h12_completion_watch.py",
        }
        for label in {item for stage in stage_plan(args.arm) for item in stage}:
            tool = repo / tool_keys[label]
            if not tool.is_file() or sha256(tool) != lock.get("tools", {}).get(tool_keys[label]):
                raise ValueError(f"{label} tool hash mismatch")
        if sha256(Path(__file__).resolve()) != lock.get("tools", {}).get("scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py"):
            raise ValueError("ordered rearm self hash mismatch")
        if args.validate_only:
            atomic_json(status_path, {"schema_version": SCHEMA, "overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS", "arm": args.arm, "design_lock_sha256": sha256(lock_path), "stages": expected_plan})
            return 0

        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        preserve_dir = run_dir / f"h12_ordered_rearm_preserved_{stamp}"
        preserved = []
        started_at = datetime.now(timezone.utc).isoformat()

        def launch(label: str) -> subprocess.Popen[Any]:
            command, mutable_status, out_path, err_path = commands[label]
            preserved.append(preserve_status(mutable_status, preserve_dir, label))
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_handle = out_path.open("ab")
            err_handle = err_path.open("ab")
            logs.extend((out_handle, err_handle))
            creationflags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
            process = subprocess.Popen(command, cwd=repo, stdout=out_handle, stderr=err_handle, creationflags=creationflags)
            children[label] = process
            return process

        health = launch("health")
        protocol = launch("protocol")
        wait_for_status(commands["health"][1], sha256(lock_path), {"HEALTH_STREAM_READY"}, args.readiness_timeout_seconds, health)
        wait_for_status(commands["protocol"][1], sha256(lock_path), {"ARM_RUNNING_GUARDS_PASS", "ARM_FINISHED_GUARDS_PASS"}, args.readiness_timeout_seconds, protocol)
        endpoint = launch("endpoint")
        wait_for_status(commands["endpoint"][1], sha256(lock_path), {"ARM_RUNNING", "WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS", "ARM_ENDPOINT_FROZEN"}, args.readiness_timeout_seconds, endpoint)
        for label in stage_plan(args.arm)[2]:
            launch(label)
        time.sleep(3.0)
        early_exits = {label: process.returncode for label, process in children.items() if process.poll() is not None and label in stage_plan(args.arm)[2]}
        if early_exits:
            raise RuntimeError(f"downstream watcher early exit: {early_exits}")
        atomic_json(status_path, {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "PASS",
            "state": "ORDERED_REARM_PASS_SUPERVISING",
            "arm": args.arm,
            "run_id": arm.get("run_id"),
            "design_lock_sha256": sha256(lock_path),
            "started_at": started_at,
            "stages": expected_plan,
            "children": {label: process.pid for label, process in children.items()},
            "preserved_statuses": preserved,
            "official_hands": 0,
        })
        sentinel_path = Path(lock.get("resource_isolation", {}).get("active_window_sentinel", repo / "reports/v5_active_window.json"))
        while True:
            sentinel = load(sentinel_path)
            if sentinel.get("terminal") is True and str(sentinel.get("state", "")).startswith("H12_TERMINAL"):
                return 0
            manifest = load(run_dir / "run_manifest.json")
            active = active_h12_trainers()
            for label, process in children.items():
                if process.poll() is None:
                    continue
                child_status = load(commands[label][1])
                expected_terminal = (
                    child_status.get("overall") == "PASS"
                    and child_status.get("state") in {
                        "HEALTH_STREAM_READY", "ARM_FINISHED_GUARDS_PASS", "ARM_ENDPOINT_FROZEN",
                        "TREATMENT_LAUNCHED", "TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED",
                    }
                )
                if active and not expected_terminal:
                    raise RuntimeError(f"{label} exited while H12 trainer active: {child_status}")
            if manifest.get("status") == "finished" and not active:
                completion = load(commands["completion"][1])
                if completion.get("state") == "TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED":
                    return 0
            time.sleep(2.0)
    except Exception as exc:
        actions = terminate_trainers()
        atomic_json(status_path, {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "state": "ORDERED_REARM_FAILURE",
            "arm": args.arm,
            "error": f"{type(exc).__name__}: {exc}",
            "child_pids": {label: process.pid for label, process in children.items()},
            "trainer_stop_actions": actions,
            "official_hands": 0,
        })
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    finally:
        for handle in logs:
            handle.close()


if __name__ == "__main__":
    raise SystemExit(main())
