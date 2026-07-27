#!/usr/bin/env python3
"""Disposable supervisor used only by CPV003."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

import psutil

from v5_lifecycle_guard_v2 import atomic_json, capture_process, sha_file, terminate_identity_tree


ROLES = ["health", "protocol", "endpoint", "treatment_launch", "completion"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--cycle", type=int, required=True)
    parser.add_argument("--design-lock-sha256", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--suppress-ready", action="store_true")
    args = parser.parse_args()
    args.workspace.mkdir(parents=True, exist_ok=True)
    child_script = Path(__file__).with_name("v5_cpv003_dummy_child.py").resolve()
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
    children: list[tuple[subprocess.Popen[bytes], dict]] = []
    for role in ROLES:
        command = [sys.executable, "-u", str(child_script), "--role", role, "--token", args.token]
        if role == "health":
            command.append("--spawn-grandchild")
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
        deadline = time.monotonic() + 5.0
        identity = capture_process(process.pid)
        while identity is None and time.monotonic() < deadline:
            time.sleep(0.01)
            identity = capture_process(process.pid)
        if identity is None:
            raise RuntimeError(f"child identity unavailable: {role}")
        entry = {
            **identity,
            "role": role,
            "script_sha256": sha_file(child_script),
            "design_lock_sha256": args.design_lock_sha256,
        }
        children.append((process, entry))
    supervisor = capture_process(psutil.Process().pid)
    if supervisor is None:
        raise RuntimeError("supervisor identity unavailable")
    registry = {
        "schema_version": "v5.cpv003.registry.v1",
        "cycle": args.cycle,
        "token": args.token,
        "design_lock_sha256": args.design_lock_sha256,
        "supervisor": supervisor,
        "entries": {entry["role"]: entry for _, entry in children},
    }
    atomic_json(args.workspace / "registry.json", registry)
    ready_at = time.time()
    if not args.suppress_ready:
        atomic_json(
            args.workspace / "ready.json",
            {
                "state": "INITIAL_READY",
                "cycle": args.cycle,
                "ready_at_epoch": ready_at,
                "scan_started_at_epoch": None,
            },
        )
    scan_started = time.time()
    process_count = sum(1 for _ in psutil.process_iter(["pid"]))
    scan_finished = time.time()
    atomic_json(
        args.workspace / "scan.json",
        {
            "cycle": args.cycle,
            "ready_at_epoch": ready_at if not args.suppress_ready else None,
            "scan_started_at_epoch": scan_started,
            "scan_finished_at_epoch": scan_finished,
            "process_count": process_count,
            "ready_before_scan": (not args.suppress_ready) and ready_at <= scan_started,
        },
    )
    stop = args.workspace / "stop"
    while not stop.exists():
        time.sleep(0.02)
    cleanup_started = time.monotonic()
    cleanup = []
    for _, entry in children:
        cleanup.append(terminate_identity_tree(entry, args.token, 15.0))
    cleanup_elapsed = time.monotonic() - cleanup_started
    atomic_json(
        args.workspace / "shutdown.json",
        {
            "cycle": args.cycle,
            "cleanup": cleanup,
            "cleanup_elapsed_seconds": cleanup_elapsed,
            "exit_code": 3 if args.suppress_ready else 0,
        },
    )
    return 3 if args.suppress_ready else 0


if __name__ == "__main__":
    raise SystemExit(main())
