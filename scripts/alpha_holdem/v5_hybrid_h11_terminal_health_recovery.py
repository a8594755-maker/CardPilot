#!/usr/bin/env python3
"""Recover the missing exact-endpoint H11 health artifact, fail closed.

H11's strict rearm intentionally disabled the generic health watcher while the
locked endpoint watcher still required ``health_status.json``.  This utility is
reporting-only: after a trainer has finished, it builds a compatibility view of
the immutable log, runs the design-lock-pinned V5 monitor, and publishes the
result with complete provenance.  It never starts or stops a trainer and never
changes a checkpoint, experiment gate, or verdict.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import torch


VHCATCH_TOKEN = re.compile(r"\s+vhcatch=\d+(?=\s)")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} root is not an object")
    return value


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    temporary.replace(path)


def active_h11_trainers() -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "ppid", "create_time", "exe", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            if "train_v5.py" in command and "v5_hybrid_h11_" in command:
                result.append(
                    {
                        "pid": process.info.get("pid"),
                        "parent_pid": process.info.get("ppid"),
                        "creation_time": process.info.get("create_time"),
                        "executable": process.info.get("exe"),
                        "command_line_sha256": hashlib.sha256(
                            command.encode("utf-8")
                        ).hexdigest(),
                    }
                )
        except (psutil.Error, OSError):
            continue
    return result


def compatible_log(source_text: str) -> tuple[str, int]:
    return VHCATCH_TOKEN.subn("", source_text)


def preserve(paths: list[Path], destination: Path) -> list[dict[str, Any]]:
    destination.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, Any]] = []
    for source in paths:
        if not source.is_file():
            records.append({"path": str(source.resolve()), "present": False})
            continue
        target = destination / source.name
        if target.exists() and sha256(target) != sha256(source):
            raise ValueError(f"preserved snapshot conflict: {target}")
        if not target.exists():
            shutil.copy2(source, target)
        records.append(
            {
                "path": str(source.resolve()),
                "present": True,
                "sha256": sha256(source),
                "snapshot_path": str(target.resolve()),
                "snapshot_sha256": sha256(target),
            }
        )
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=["control", "treatment"], required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--preserve-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    repo = args.repo.resolve()
    run_dir = args.run_dir.resolve()
    lock_path = args.design_lock.resolve()
    out = args.out.resolve()
    try:
        if not lock_path.is_file() or sha256(lock_path) != args.expected_lock_sha256.lower():
            raise ValueError("design lock SHA mismatch")
        lock = load(lock_path)
        if lock.get("design_id") != "H11" or lock.get("status") != "LOCKED":
            raise ValueError("design lock identity/status")
        arm = lock.get("arms", {}).get(args.arm)
        if not isinstance(arm, dict) or Path(arm["run_dir"]).resolve() != run_dir:
            raise ValueError("run directory is not the locked arm")
        monitor = repo / "scripts/alpha_holdem/v5_monitor.py"
        monitor_expected = lock.get("tools", {}).get("scripts/alpha_holdem/v5_monitor.py")
        if not monitor.is_file() or sha256(monitor) != monitor_expected:
            raise ValueError("frozen monitor SHA mismatch")
        trainers = active_h11_trainers()
        if trainers:
            raise ValueError(f"active H11 trainer(s): {trainers}")

        manifest_path = run_dir / "run_manifest.json"
        log_path = run_dir / "latest_train.log"
        checkpoint_path = run_dir / "latest.pt"
        stderr_path = run_dir / "console.err.log"
        for required in (manifest_path, log_path, checkpoint_path, stderr_path):
            if not required.is_file():
                raise FileNotFoundError(required)
        manifest = load(manifest_path)
        if manifest.get("status") != "finished" or manifest.get("run_id") != arm["run_id"]:
            raise ValueError("manifest is not the exact finished locked arm")
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=False)
        iteration = int(checkpoint.get("iteration", -1))
        hands = int(checkpoint.get("total_hands", -1))
        if int(manifest.get("iteration", -2)) != iteration or int(manifest.get("total_hands", -2)) != hands:
            raise ValueError("manifest/checkpoint endpoint mismatch")
        low = int(lock["arm_budget"]["minimum_endpoint_hands"])
        high = low + int(lock["arm_budget"]["maximum_overshoot_hands"])
        if not low <= hands <= high:
            raise ValueError("endpoint hands outside locked range")
        if stderr_path.stat().st_size != 0:
            raise ValueError("endpoint stderr is nonempty")

        if args.validate_only:
            print(json.dumps({"overall": "PASS", "state": "VALIDATE_ONLY_PASS", "iteration": iteration, "hands": hands}))
            return 0

        failed_statuses = [
            run_dir / f"h11_{args.arm}_endpoint_status.json",
            run_dir / f"h11_{args.arm}_protocol_status.json",
            run_dir / f"h11_{args.arm}_assignment_provenance_audit.json",
            run_dir / "h11_treatment_launch_watch_status.json",
            run_dir / "h11_completion_watch_status.json",
            run_dir / "watcher_rearm_status.json",
        ]
        preserved = preserve(failed_statuses, args.preserve_dir.resolve())

        source_text = log_path.read_text(encoding="utf-8", errors="replace")
        transformed, replacements = compatible_log(source_text)
        metric_rows = sum(1 for line in (run_dir / "h1_training_metrics.jsonl").open("rb") if line.strip())
        if replacements != metric_rows:
            raise ValueError(
                f"vhcatch replacement count {replacements} != structured metric rows {metric_rows}"
            )
        compatibility_dir = run_dir / ".h11_terminal_health_recovery"
        compatibility_dir.mkdir(parents=True, exist_ok=True)
        compatibility_log = compatibility_dir / "latest_train.log"
        compatibility_log.write_text(transformed, encoding="utf-8")
        shutil.copy2(manifest_path, compatibility_dir / "run_manifest.json")
        shutil.copy2(stderr_path, compatibility_dir / "console.err.log")

        age_minutes = max(
            0.0,
            (datetime.now(timezone.utc).timestamp() - log_path.stat().st_mtime) / 60.0,
        )
        stale_minutes = float(max(30, math.ceil(age_minutes) + 5))
        command = [
            sys.executable,
            str(monitor),
            "--run-dir",
            str(compatibility_dir),
            "--stale-minutes",
            str(stale_minutes),
        ]
        completed = subprocess.run(command, cwd=repo, text=True, capture_output=True)
        if completed.returncode != 0:
            raise RuntimeError(f"monitor exit {completed.returncode}: {completed.stderr}")
        health = load(compatibility_dir / "health_status.json")
        latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
        if health.get("overall") != "PASS":
            raise ValueError(f"reconstructed health is not PASS: {health.get('overall')}")
        if int(latest.get("iteration", -1)) != iteration or int(latest.get("hands", -1)) != hands:
            raise ValueError("reconstructed health is not exact endpoint")
        if any(item.get("status") != "PASS" for item in health.get("checks", [])):
            raise ValueError("one or more reconstructed health checks are not PASS")

        provenance = {
            "schema_version": "v5.hybrid.h11.terminal_health_recovery.v1",
            "classification": "CENSURE_REPORTING_ONLY_MISSING_EXACT_ENDPOINT_HEALTH_RECOVERED",
            "recovered_at": datetime.now(timezone.utc).isoformat(),
            "arm": args.arm,
            "run_id": arm["run_id"],
            "iteration": iteration,
            "hands": hands,
            "design_lock_path": str(lock_path),
            "design_lock_sha256": sha256(lock_path),
            "monitor_path": str(monitor),
            "monitor_sha256": sha256(monitor),
            "source_manifest_sha256": sha256(manifest_path),
            "source_log_sha256": sha256(log_path),
            "source_checkpoint_sha256": sha256(checkpoint_path),
            "source_stderr_sha256": sha256(stderr_path),
            "compatibility_log_sha256": sha256(compatibility_log),
            "compatibility_transform": "remove only whitespace-delimited vhcatch=<integer> reporting token",
            "replacement_count": replacements,
            "structured_metric_rows": metric_rows,
            "terminal_staleness_policy": "wall-clock delay after manifest=finished is reporting delay, not trainer health; threshold recorded and no other monitor threshold changed",
            "source_log_age_minutes_at_recovery": age_minutes,
            "monitor_stale_minutes": stale_minutes,
            "active_h11_trainers": trainers,
            "preserved_failed_artifacts": preserved,
            "behavior_change": False,
            "checkpoint_changed": False,
            "gate_changed": False,
            "verdict_forced": False,
            "next_action": "rerun unchanged locked endpoint watcher via canonical rearm",
        }
        health["run_dir"] = str(run_dir)
        health["reporting_recovery"] = provenance
        atomic_json(run_dir / "health_status.json", health)
        health_md = compatibility_dir / "health_status.md"
        if health_md.is_file():
            (run_dir / "health_status.md").write_text(
                health_md.read_text(encoding="utf-8").replace(
                    str(compatibility_dir), str(run_dir)
                ),
                encoding="utf-8",
            )
        provenance["published_health_status_sha256"] = sha256(run_dir / "health_status.json")
        provenance["recovery_tool_sha256"] = sha256(Path(__file__).resolve())
        atomic_json(out, provenance)
        print(json.dumps({"overall": "PASS", "state": "EXACT_ENDPOINT_HEALTH_RECOVERED", "artifact": str(out), "health_sha256": provenance["published_health_status_sha256"]}))
        return 0
    except Exception as exc:
        failure = {
            "schema_version": "v5.hybrid.h11.terminal_health_recovery.v1",
            "classification": "FAIL_CLOSED_H11_TERMINAL_HEALTH_RECOVERY",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
            "behavior_change": False,
            "verdict_forced": False,
        }
        if not args.validate_only:
            atomic_json(out, failure)
        print(json.dumps(failure), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
