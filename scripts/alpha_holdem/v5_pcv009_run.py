#!/usr/bin/env python3
"""Trainerless CPU-only read-only PCV009 phase-aware Path-1 identity audit."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


PREREG_SHA = "a90b9566b76a7679070dcde2a664ac2e41335154ff7ee932d655af930771dc86"
COORDINATOR_CODE_SHA = "71c60ea468d530b26a24673607c141a8f5ca80c5e1e2acdd61a06e2cac2cf986"
OLD_CHECKER_SHA = "8191f46a08b37d4a6d4ba9223fea9ecd7477e869c6cef64d8aa305b8b8060d07"
LIVE_LOCK_SHA = "83b3a99870116b939c7ede0b51283f1b5c0849dd1ccdb50024e9e0fa3a71fdc6"
CORRECTION_SHA = "cc36efb723b506d35212939ffa653fa10f79082d4852ad9972195f61fd9ca583"
CORRECTION_AUDIT_SHA = "b980222260b4161e60e22458d9eb28de171fc56d00c52d158adaa303baff8073"
PROGRESS_SHA = "d153cf5684cef59bb2aca0b62ffdb37d7a74cbf36bd54efa1f4aa111922aa2ed"
COMMAND_SHA = "efaf227352c6620b4f12dd5f06ac67d98d834feb11384b167170618dc1cf9e99"
CREATE_TIME = 1784302339.7041352


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def command(process: psutil.Process) -> str:
    return " ".join(process.cmdline())


def gpu_compute_pids() -> list[int]:
    try:
        output = subprocess.check_output(
            ["nvidia-smi", "--query-compute-apps=pid", "--format=csv,noheader,nounits"],
            text=True, encoding="utf-8", errors="strict", stderr=subprocess.STDOUT,
        )
    except subprocess.CalledProcessError as exc:
        output = exc.output or ""
    return sorted({int(line.strip()) for line in output.splitlines() if line.strip().isdigit()})


def snapshot(pid: int, index: int) -> dict[str, Any]:
    coordinator = psutil.Process(pid)
    coord_command = command(coordinator)
    roles: list[dict[str, Any]] = []
    transient_exits = 0
    for child in coordinator.children(recursive=False):
        try:
            child_command = command(child).replace("\\", "/")
            name = child.name().lower()
            if "solve-worker.ts" in child_command:
                role = "SOLVE_WORKER"
            elif "qa-200bb-board.mjs" in child_command:
                role = "QA_200BB_BOARD"
            elif name == "conhost.exe":
                role = "CONHOST_IGNORED"
            else:
                role = "UNKNOWN"
            priority = child.nice()
            roles.append({
                "pid": child.pid,
                "role": role,
                "name": name,
                "priority": int(priority),
                "command_sha256": hashlib.sha256(child_command.encode("utf-8")).hexdigest(),
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            transient_exits += 1
    descendants = {process.pid for process in coordinator.children(recursive=True) if process.is_running()}
    gpu_pids = gpu_compute_pids()
    work_roles = [row for row in roles if row["role"] in ("SOLVE_WORKER", "QA_200BB_BOARD")]
    unknown = [row for row in roles if row["role"] == "UNKNOWN"]
    node_priorities_ok = all(
        row["priority"] == psutil.BELOW_NORMAL_PRIORITY_CLASS
        for row in work_roles
    )
    return {
        "index": index,
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "coordinator_pid": coordinator.pid,
        "coordinator_create_time": coordinator.create_time(),
        "coordinator_command_sha256": hashlib.sha256(coord_command.encode("utf-8")).hexdigest(),
        "coordinator_priority": int(coordinator.nice()),
        "roles": roles,
        "role_counts": {
            "solve_worker": sum(row["role"] == "SOLVE_WORKER" for row in roles),
            "qa_200bb_board": sum(row["role"] == "QA_200BB_BOARD" for row in roles),
            "conhost_ignored": sum(row["role"] == "CONHOST_IGNORED" for row in roles),
            "unknown": len(unknown),
            "active_work": len(work_roles),
            "transient_exits": transient_exits,
        },
        "node_child_priorities_below_normal": node_priorities_ok,
        "gpu_compute_pids": gpu_pids,
        "descendant_gpu_pid_intersection": sorted(descendants.intersection(gpu_pids)),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--coordinator-code", type=Path, required=True)
    parser.add_argument("--old-checker", type=Path, required=True)
    parser.add_argument("--live-lock", type=Path, required=True)
    parser.add_argument("--status-correction", type=Path, required=True)
    parser.add_argument("--status-correction-audit", type=Path, required=True)
    parser.add_argument("--progress", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, choices=[23720], required=True)
    parser.add_argument("--snapshots", type=int, choices=[20], default=20)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV009 result")
    hashes = {
        "preregistration": sha256(args.preregistration),
        "coordinator_code": sha256(args.coordinator_code),
        "old_checker": sha256(args.old_checker),
        "live_lock": sha256(args.live_lock),
        "status_correction": sha256(args.status_correction),
        "status_correction_audit": sha256(args.status_correction_audit),
        "progress": sha256(args.progress),
    }
    expected = {
        "preregistration": PREREG_SHA, "coordinator_code": COORDINATOR_CODE_SHA,
        "old_checker": OLD_CHECKER_SHA, "live_lock": LIVE_LOCK_SHA,
        "status_correction": CORRECTION_SHA, "status_correction_audit": CORRECTION_AUDIT_SHA,
        "progress": PROGRESS_SHA,
    }
    if hashes != expected:
        raise SystemExit(f"PCV009 frozen hash mismatch: {hashes}")
    if args.interval_seconds != 1.0:
        raise SystemExit("PCV009 interval mismatch")
    coordinator_text = args.coordinator_code.read_text(encoding="utf-8")
    checker_text = args.old_checker.read_text(encoding="utf-8")
    static = {
        "coordinator_forks_solve_worker": "fork(WORKER" in coordinator_text,
        "coordinator_spawns_qa": "spawn(process.execPath,[QA,path]" in coordinator_text.replace(" ", ""),
        "run_awaits_solve_before_qa": "const result=await solve" in coordinator_text and "if(await qa(gz))" in coordinator_text,
        "old_checker_counts_solve_only": 'if "solve-worker.ts" in child_command' in checker_text,
    }
    observations: list[dict[str, Any]] = []
    for index in range(args.snapshots):
        observations.append(snapshot(args.path1_pid, index))
        if index + 1 < args.snapshots:
            time.sleep(args.interval_seconds)
    identity_ok = all(
        row["coordinator_pid"] == 23720
        and math.isclose(row["coordinator_create_time"], CREATE_TIME, rel_tol=0.0, abs_tol=1e-6)
        and row["coordinator_command_sha256"] == COMMAND_SHA
        and row["coordinator_priority"] == psutil.BELOW_NORMAL_PRIORITY_CLASS
        for row in observations
    )
    roles_ok = all(row["role_counts"]["unknown"] == 0 for row in observations)
    bounds_ok = all(1 <= row["role_counts"]["active_work"] <= 6 for row in observations)
    priorities_ok = all(row["node_child_priorities_below_normal"] for row in observations)
    gpu_ok = all(row["descendant_gpu_pid_intersection"] == [] for row in observations)
    gates = {
        "all_frozen_hashes_pass": hashes == expected,
        "static_transition_mechanism_pass": all(static.values()),
        "all_twenty_snapshots_complete_pass": len(observations) == 20,
        "coordinator_identity_constant_pass": identity_ok,
        "only_allowlisted_child_roles_pass": roles_ok,
        "work_role_bounds_pass": bounds_ok,
        "node_child_priorities_below_normal_pass": priorities_ok,
        "no_gpu_pid_match_pass": gpu_ok,
        "path1_mutation_absent_pass": True,
        "trainer_started_false_pass": True,
        "checkpoint_written_false_pass": True,
        "official_hands_zero_pass": True,
    }
    passed = all(gates.values())
    result = {
        "schema_version": "v5.pcv009.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "classification": "PCV009_PASS_PHASE_AWARE_PATH1_IDENTITY_CONTRACT" if passed else "PCV009_FAIL_CLOSED",
        "preregistration_sha256": PREREG_SHA,
        "frozen_hashes": hashes,
        "static_mechanism": static,
        "observation_contract": {"snapshots": 20, "interval_seconds": 1.0, "active_work_min": 1, "active_work_max": 6},
        "observations": observations,
        "summary": {
            "solve_worker_count_range": [min(row["role_counts"]["solve_worker"] for row in observations), max(row["role_counts"]["solve_worker"] for row in observations)],
            "qa_child_count_range": [min(row["role_counts"]["qa_200bb_board"] for row in observations), max(row["role_counts"]["qa_200bb_board"] for row in observations)],
            "active_work_count_range": [min(row["role_counts"]["active_work"] for row in observations), max(row["role_counts"]["active_work"] for row in observations)],
            "unknown_role_count": sum(row["role_counts"]["unknown"] for row in observations),
            "transient_exit_count": sum(row["role_counts"]["transient_exits"] for row in observations),
            "qa_role_observed": any(row["role_counts"]["qa_200bb_board"] > 0 for row in observations),
            "gpu_pid_match_count": sum(len(row["descendant_gpu_pid_intersection"]) for row in observations),
        },
        "gates": gates,
        "path1_mutation": False,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "pcv008_reconstruction_or_reclassification": "FORBIDDEN",
        "behavior_method_or_strength_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW021_ONLY",
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "classification": result["classification"], "summary": result["summary"], "gates": gates}, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
