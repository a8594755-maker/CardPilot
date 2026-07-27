#!/usr/bin/env python3
"""Run immutable CPV004 with final post-sequence cleanup observation."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil

from v5_lifecycle_guard_v2 import (
    atomic_json,
    capture_process,
    sha_file,
    supervisor_state,
    tagged_survivors,
    terminate_identity_tree,
    validate_registered_child,
)

ROOT = Path(__file__).resolve().parents[2]
ROLES = ["health", "protocol", "endpoint", "treatment_launch", "completion"]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wait_json(path: Path, deadline: float) -> dict | None:
    while time.monotonic() < deadline:
        if path.is_file():
            try:
                return json.loads(path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                pass
        time.sleep(0.01)
    return None


def forbidden_processes() -> list[dict]:
    found: list[dict] = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
        except (psutil.Error, OSError):
            continue
        lowered = command.lower()
        if any(token in lowered for token in (
            "train_v5.py",
            "play_slumbot",
            "v5_slumbot_benchmark",
            "v5_mirror_eval",
        )):
            found.append({"pid": process.pid, "command": command})
    return found


def start_supervisor(
    workspace: Path,
    cycle: int,
    design_sha: str,
    token: str,
    *,
    suppress_ready: bool = False,
) -> subprocess.Popen[bytes]:
    script = Path(__file__).with_name("v5_cpv003_dummy_supervisor.py").resolve()
    command = [
        sys.executable,
        "-u",
        str(script),
        "--workspace",
        str(workspace),
        "--cycle",
        str(cycle),
        "--design-lock-sha256",
        design_sha,
        "--token",
        token,
    ]
    if suppress_ready:
        command.append("--suppress-ready")
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(
        subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0
    )
    return subprocess.Popen(
        command,
        cwd=ROOT,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--expected-preregistration-sha256", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists() or args.out_dir.exists():
        raise SystemExit("refusing to overwrite CPV004 artifacts")
    prereg = json.loads(args.preregistration.read_text(encoding="utf-8"))
    expected_sha = args.expected_preregistration_sha256.lower()
    if sha(args.preregistration) != expected_sha:
        raise SystemExit("preregistration hash mismatch")
    if prereg.get("design_id") != "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE":
        raise SystemExit("preregistration identity")
    initial_forbidden = forbidden_processes()
    if initial_forbidden:
        raise SystemExit(f"forbidden live process: {initial_forbidden}")

    args.out_dir.mkdir(parents=True)
    supervisor_script = Path(__file__).with_name("v5_cpv003_dummy_supervisor.py")
    child_script = Path(__file__).with_name("v5_cpv003_dummy_child.py")
    guard_script = Path(__file__).with_name("v5_lifecycle_guard_v2.py")
    tool_hashes = {
        str(path.relative_to(ROOT)).replace("\\", "/"): sha_file(path)
        for path in (Path(__file__), supervisor_script, child_script, guard_script)
    }
    child_sha = sha_file(child_script)
    deadline_seconds = float(prereg["gates"]["initial_ready_deadline_seconds"])
    cleanup_deadline = float(prereg["gates"]["cleanup_deadline_seconds"])
    cycles: list[dict] = []
    deterministic_failures: list[str] = []
    fixture_errors: list[str] = []

    for cycle in range(int(prereg["fixture"]["stress_cycles"])):
        workspace = args.out_dir / f"cycle_{cycle:02d}"
        workspace.mkdir()
        token = f"cpv004-{prereg['fixture']['seed']}-{cycle}"
        started = time.monotonic()
        process = start_supervisor(workspace, cycle, expected_sha, token)
        supervisor_expected: dict | None = None
        try:
            ready = wait_json(workspace / "ready.json", time.monotonic() + deadline_seconds)
            ready_elapsed = time.monotonic() - started
            registry = wait_json(workspace / "registry.json", time.monotonic() + 2.0)
            scan = wait_json(workspace / "scan.json", time.monotonic() + 2.0)
            if registry is None:
                raise RuntimeError("registry missing")
            supervisor_expected = registry["supervisor"]
            role_results = {
                role: validate_registered_child(
                    registry["entries"][role],
                    capture_process(registry["entries"][role]["pid"]),
                    allowed_roles=ROLES,
                    expected_design_lock_sha256=expected_sha,
                    expected_script_sha256=child_sha,
                )
                for role in ROLES
            }
            sample = registry["entries"]["health"]
            actual = capture_process(sample["pid"])
            mutations = {
                "unregistered_sibling": {"role": "intruder"},
                "wrong_parent": {"parent_pid": int(sample["parent_pid"]) + 999999},
                "wrong_script_sha256": {"script_sha256": "0" * 64},
                "wrong_command_line_sha256": {"command_line_sha256": "f" * 64},
            }
            adversarial: dict[str, dict] = {}
            for expected_token, mutation in mutations.items():
                modified = copy.deepcopy(sample)
                modified.update(mutation)
                checked = validate_registered_child(
                    modified,
                    actual,
                    allowed_roles=ROLES,
                    expected_design_lock_sha256=expected_sha,
                    expected_script_sha256=child_sha,
                )
                adversarial[expected_token] = {
                    "pass": (
                        checked["overall"] == "FAIL_CLOSED"
                        and expected_token in checked["tokens"]
                        and checked["trigger_provenance_complete"] is True
                    ),
                    "result": checked,
                }
            live_state = supervisor_state(supervisor_expected, capture_process(process.pid))
            (workspace / "stop").write_text("stop\n", encoding="utf-8")
            process.wait(timeout=cleanup_deadline)
            shutdown = wait_json(workspace / "shutdown.json", time.monotonic() + 1.0)
            shutdown_state = supervisor_state(supervisor_expected, capture_process(process.pid))
            reused = copy.deepcopy(supervisor_expected)
            reused["creation_time_epoch"] = float(reused["creation_time_epoch"]) + 100.0
            reused["command_line_sha256"] = "a" * 64
            pid_reuse_state = supervisor_state(supervisor_expected, reused)
            final_survivors = tagged_survivors(token)
            cycle_checks = {
                "ready": ready is not None and ready.get("state") == "INITIAL_READY" and ready_elapsed <= deadline_seconds,
                "ready_before_scan": scan is not None and scan.get("ready_before_scan") is True and scan.get("ready_at_epoch") <= scan.get("scan_started_at_epoch"),
                "all_roles": len(role_results) == 5 and all(item["overall"] == "PASS" for item in role_results.values()),
                "adversarial": all(item["pass"] for item in adversarial.values()),
                "supervisor_live": live_state == "LIVE",
                "normal_exit_zero": process.returncode == 0,
                "shutdown_state": shutdown_state == "LIFECYCLE_SHUTDOWN",
                "pid_reuse_state": pid_reuse_state == "LIFECYCLE_SHUTDOWN_PID_REUSED_NOT_RESOURCE_VIOLATION",
                "cleanup": shutdown is not None and shutdown.get("cleanup_elapsed_seconds", cleanup_deadline + 1) <= cleanup_deadline and not final_survivors,
            }
            passed = all(cycle_checks.values())
            if not passed:
                deterministic_failures.append(f"cycle_{cycle:02d}")
            cycles.append({
                "cycle": cycle,
                "token": token,
                "ready_elapsed_seconds": ready_elapsed,
                "supervisor_pid": supervisor_expected["pid"],
                "role_results": role_results,
                "adversarial": adversarial,
                "live_state": live_state,
                "shutdown_state": shutdown_state,
                "pid_reuse_state": pid_reuse_state,
                "shutdown": shutdown,
                "per_child_survivor_snapshots_interpretation": "DIAGNOSTIC_ONLY_NOT_GATE",
                "final_survivors": final_survivors,
                "checks": cycle_checks,
                "overall": "PASS" if passed else "FAIL",
            })
        except Exception as exc:
            fixture_errors.append(f"cycle_{cycle:02d}:{type(exc).__name__}:{exc}")
        finally:
            if process.poll() is None:
                expected = supervisor_expected or capture_process(process.pid)
                if expected:
                    terminate_identity_tree(expected, token, cleanup_deadline)
                try:
                    process.wait(timeout=2.0)
                except subprocess.TimeoutExpired:
                    process.kill()

    failure_workspace = args.out_dir / "injected_readiness_failure"
    failure_workspace.mkdir()
    failure_token = f"cpv004-{prereg['fixture']['seed']}-readiness-failure"
    failure_process = start_supervisor(
        failure_workspace,
        999,
        expected_sha,
        failure_token,
        suppress_ready=True,
    )
    failure_registry = wait_json(failure_workspace / "registry.json", time.monotonic() + 5.0)
    time.sleep(0.25)
    ready_absent = not (failure_workspace / "ready.json").exists()
    (failure_workspace / "stop").write_text("stop\n", encoding="utf-8")
    try:
        failure_process.wait(timeout=cleanup_deadline)
    except subprocess.TimeoutExpired:
        if failure_registry:
            terminate_identity_tree(failure_registry["supervisor"], failure_token, cleanup_deadline)
        failure_process.wait(timeout=2.0)
    failure_survivors = tagged_survivors(failure_token)
    injected = {
        "ready_absent": ready_absent,
        "exit_code": failure_process.returncode,
        "nonzero": failure_process.returncode not in (None, 0),
        "final_survivors": failure_survivors,
        "pass": ready_absent and failure_process.returncode not in (None, 0) and not failure_survivors,
    }
    if not injected["pass"]:
        deterministic_failures.append("injected_readiness_failure")
    final_forbidden = forbidden_processes()
    if final_forbidden:
        deterministic_failures.append("forbidden_process_appeared")

    aggregate = {
        "cycles_required": 20,
        "cycles_passed": sum(cycle["overall"] == "PASS" for cycle in cycles),
        "max_ready_elapsed_seconds": max((cycle["ready_elapsed_seconds"] for cycle in cycles), default=None),
        "max_cleanup_elapsed_seconds": max((cycle["shutdown"]["cleanup_elapsed_seconds"] for cycle in cycles if cycle.get("shutdown")), default=None),
        "all_roles_pass": len(cycles) == 20 and all(cycle["checks"]["all_roles"] for cycle in cycles),
        "all_adversarial_pass": len(cycles) == 20 and all(cycle["checks"]["adversarial"] for cycle in cycles),
        "all_final_cleanup_pass": len(cycles) == 20 and all(cycle["checks"]["cleanup"] for cycle in cycles),
        "all_normal_exit_zero": len(cycles) == 20 and all(cycle["checks"]["normal_exit_zero"] for cycle in cycles),
        "all_pid_reuse_safe": len(cycles) == 20 and all(cycle["checks"]["pid_reuse_state"] for cycle in cycles),
        "injected_readiness_failure_pass": injected["pass"],
    }
    if fixture_errors:
        overall = "INCONCLUSIVE"
        classification = "CPV004_INCONCLUSIVE_FIXTURE_OR_PLATFORM"
    elif deterministic_failures or aggregate["cycles_passed"] != 20:
        overall = "FAIL_CLOSED"
        classification = "CPV004_FAIL_REGISTERED_GATE"
    else:
        overall = "PASS"
        classification = "CPV004_PASS_CORRECTED_FINAL_CLEANUP_OBSERVATION"
    result = {
        "schema_version": "v5.cpv004.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "design_id": prereg["design_id"],
        "overall": overall,
        "classification": classification,
        "preregistration_sha256": sha(args.preregistration),
        "tool_hashes": tool_hashes,
        "single_engineering_change": prereg["single_engineering_change"],
        "initial_forbidden_processes": initial_forbidden,
        "final_forbidden_processes": final_forbidden,
        "cycles": cycles,
        "injected_readiness_failure": injected,
        "aggregate": aggregate,
        "deterministic_failures": deterministic_failures,
        "fixture_errors": fixture_errors,
        "trainer_launched": False,
        "gpu_used": False,
        "official_hands": 0,
        "terminal_effect": prereg["terminal_effect"]["PASS"] if overall == "PASS" else prereg["terminal_effect"]["FAIL_OR_INCONCLUSIVE"],
        "strength_claim": "FORBIDDEN",
    }
    atomic_json(args.out, result)
    print(json.dumps({key: result[key] for key in ("overall", "classification", "aggregate", "deterministic_failures", "fixture_errors", "terminal_effect")}, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else (2 if overall == "FAIL_CLOSED" else 3)


if __name__ == "__main__":
    raise SystemExit(main())
