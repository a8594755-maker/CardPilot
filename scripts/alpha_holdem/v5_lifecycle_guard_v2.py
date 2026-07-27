#!/usr/bin/env python3
"""Exact process-identity helpers for trainerless lifecycle validation."""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any

import psutil


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command_sha256(command_line: list[str]) -> str:
    return hashlib.sha256(" ".join(command_line).encode("utf-8", errors="replace")).hexdigest()


def capture_process(pid: int) -> dict[str, Any] | None:
    try:
        process = psutil.Process(int(pid))
        command = process.cmdline()
        return {
            "pid": process.pid,
            "parent_pid": process.ppid(),
            "creation_time_epoch": process.create_time(),
            "executable": process.exe(),
            "command_line": command,
            "command_line_sha256": command_sha256(command),
        }
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return None


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def supervisor_state(expected: dict[str, Any], actual: dict[str, Any] | None) -> str:
    if actual is None:
        return "LIFECYCLE_SHUTDOWN"
    identity_fields = ("pid", "creation_time_epoch", "executable", "command_line_sha256")
    if any(actual.get(field) != expected.get(field) for field in identity_fields):
        return "LIFECYCLE_SHUTDOWN_PID_REUSED_NOT_RESOURCE_VIOLATION"
    return "LIVE"


def validate_registered_child(
    entry: dict[str, Any],
    actual: dict[str, Any] | None,
    *,
    allowed_roles: list[str],
    expected_design_lock_sha256: str,
    expected_script_sha256: str,
) -> dict[str, Any]:
    tokens: list[str] = []
    if entry.get("role") not in allowed_roles:
        tokens.append("unregistered_sibling")
    if entry.get("design_lock_sha256") != expected_design_lock_sha256:
        tokens.append("wrong_design_lock_sha256")
    if entry.get("script_sha256") != expected_script_sha256:
        tokens.append("wrong_script_sha256")
    if actual is None:
        tokens.append("missing_process")
    else:
        if entry.get("pid") != actual.get("pid"):
            tokens.append("wrong_pid")
        if entry.get("parent_pid") != actual.get("parent_pid"):
            tokens.append("wrong_parent")
        if entry.get("creation_time_epoch") != actual.get("creation_time_epoch"):
            tokens.append("wrong_creation_time")
        if entry.get("executable") != actual.get("executable"):
            tokens.append("wrong_executable")
        if entry.get("command_line_sha256") != actual.get("command_line_sha256"):
            tokens.append("wrong_command_line_sha256")
    provenance = {
        **(actual or {
            "pid": entry.get("pid"),
            "parent_pid": entry.get("parent_pid"),
            "creation_time_epoch": entry.get("creation_time_epoch"),
            "executable": entry.get("executable"),
            "command_line_sha256": entry.get("command_line_sha256"),
        }),
        "role": entry.get("role"),
        "script_sha256": entry.get("script_sha256"),
        "design_lock_sha256": entry.get("design_lock_sha256"),
    }
    return {
        "overall": "PASS" if not tokens else "FAIL_CLOSED",
        "tokens": tokens,
        "trigger_provenance": provenance,
        "trigger_provenance_complete": all(
            provenance.get(field) is not None
            for field in (
                "pid",
                "parent_pid",
                "creation_time_epoch",
                "executable",
                "command_line_sha256",
                "role",
                "script_sha256",
                "design_lock_sha256",
            )
        ),
    }


def tagged_survivors(token: str) -> list[int]:
    survivors: list[int] = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            if token in " ".join(process.info.get("cmdline") or []):
                survivors.append(process.pid)
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass
    return sorted(survivors)


def terminate_identity_tree(
    expected_root: dict[str, Any], token: str, timeout_seconds: float = 15.0
) -> dict[str, Any]:
    started = time.monotonic()
    actual = capture_process(int(expected_root["pid"]))
    state = supervisor_state(expected_root, actual)
    if state != "LIVE":
        return {
            "state": state,
            "terminated": [],
            "killed": [],
            "survivors": tagged_survivors(token),
            "elapsed_seconds": time.monotonic() - started,
        }
    root = psutil.Process(int(expected_root["pid"]))
    descendants = root.children(recursive=True)
    targets = descendants + [root]
    verified: list[psutil.Process] = []
    for process in targets:
        try:
            if token in " ".join(process.cmdline()):
                verified.append(process)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    terminated: list[int] = []
    for process in reversed(verified):
        try:
            process.terminate()
            terminated.append(process.pid)
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(verified, timeout=max(0.1, timeout_seconds / 2))
    killed: list[int] = []
    for process in alive:
        try:
            process.kill()
            killed.append(process.pid)
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=max(0.1, timeout_seconds / 2))
    return {
        "state": "TERMINATED",
        "terminated": sorted(set(terminated)),
        "killed": sorted(set(killed)),
        "survivors": tagged_survivors(token),
        "elapsed_seconds": time.monotonic() - started,
    }
