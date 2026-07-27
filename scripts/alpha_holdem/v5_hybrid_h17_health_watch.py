#!/usr/bin/env python3
"""Exact lock-bound H17 endpoint-health producer.

The frozen V5 monitor predates the ``vhcatch=<integer>`` reporting token.  This
watcher produces an atomic compatibility view, invokes the lock-pinned monitor,
and atomically publishes exact health into the immutable arm directory.  Source
logs, manifests, checkpoints and trainer behavior are never modified.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TOKEN = re.compile(r"\s+vhcatch=\d+(?=\s)")
SCHEMA = "v5.hybrid.h17.health_watch_status.v1"


def startup_log_gate(run_dir: Path, first_manifest_seen: float, now: float, timeout_seconds: float) -> str:
    """Return READY/PENDING/TIMEOUT without treating normal startup as corruption."""
    if (run_dir / "latest_train.log").is_file():
        return "READY"
    return "PENDING" if now - first_manifest_seen < timeout_seconds else "TIMEOUT"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
        return value if isinstance(value, dict) else {}
    except Exception:
        return {}


def read_json_snapshot(path: Path, attempts: int = 8) -> tuple[str, dict[str, Any], int]:
    for attempt in range(1, attempts + 1):
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("manifest root")
            return raw, value, attempt
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if attempt < attempts:
                time.sleep(0.025 * attempt)
    raise ValueError("unable to read a consistent manifest snapshot")


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def transform_log(text: str) -> tuple[str, int]:
    return TOKEN.subn("", text)


def prepare_view(run_dir: Path, manifest_raw: str, manifest: dict[str, Any]) -> tuple[Path, dict[str, Any]]:
    source_log = run_dir / "latest_train.log"
    if not source_log.is_file():
        raise FileNotFoundError(source_log)
    source_text = source_log.read_text(encoding="utf-8", errors="replace")
    transformed, replacements = transform_log(source_text)
    view = run_dir / ".h17_health_compat"
    view.mkdir(parents=True, exist_ok=True)
    log_tmp = view / "latest_train.log.tmp"
    log_tmp.write_text(transformed, encoding="utf-8")
    source_stat = source_log.stat()
    os.utime(log_tmp, (source_stat.st_atime, source_stat.st_mtime))
    log_tmp.replace(view / "latest_train.log")
    manifest_tmp = view / "run_manifest.json.tmp"
    manifest_tmp.write_text(manifest_raw, encoding="utf-8")
    manifest_tmp.replace(view / "run_manifest.json")
    stderr = run_dir / "console.err.log"
    if stderr.is_file():
        shutil.copy2(stderr, view / "console.err.log")
    else:
        (view / "console.err.log").write_bytes(b"")
    metrics = run_dir / "h1_training_metrics.jsonl"
    rows = sum(1 for line in metrics.open("rb") if line.strip()) if metrics.is_file() else 0
    if replacements != rows:
        raise ValueError(f"vhcatch replacements {replacements} != metric rows {rows}")
    provenance = {
        "schema_version": "v5.hybrid.h17.health_log_adapter.v1",
        "run_id": manifest.get("run_id"),
        "source_log_sha256": sha256(source_log),
        "compatibility_log_sha256": sha256(view / "latest_train.log"),
        "manifest_snapshot_sha256": sha256(view / "run_manifest.json"),
        "removed_token": "vhcatch=<nonnegative integer>",
        "replacement_count": replacements,
        "structured_metric_rows": rows,
        "source_changed": False,
    }
    atomic_json(view / "adapter_provenance.json", provenance)
    return view, provenance


def publish(run_dir: Path, view: Path, provenance: dict[str, Any]) -> dict[str, Any]:
    health = load(view / "health_status.json")
    if not health:
        raise ValueError("monitor did not produce health_status.json")
    health["run_dir"] = str(run_dir.resolve())
    health["h17_health_producer"] = provenance
    atomic_json(run_dir / "health_status.json", health)
    source_md = view / "health_status.md"
    if source_md.is_file():
        text = source_md.read_text(encoding="utf-8").replace(str(view.resolve()), str(run_dir.resolve()))
        temporary = run_dir / "health_status.md.tmp"
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(run_dir / "health_status.md")
    return health


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--arm", choices=("control", "treatment"), required=True)
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--status-json", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=15.0)
    parser.add_argument("--startup-log-timeout-seconds", type=float, default=180.0)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    run_dir = args.run_dir.resolve()
    lock_path = args.design_lock.resolve()
    status_path = args.status_json.resolve()
    try:
        if not lock_path.is_file() or sha256(lock_path) != args.expected_lock_sha256.lower():
            raise ValueError("design lock SHA mismatch")
        lock = load(lock_path)
        if lock.get("design_id") != "H17" or lock.get("status") != "LOCKED":
            raise ValueError("design lock identity/status")
        arm = lock.get("arms", {}).get(args.arm, {})
        if Path(arm.get("run_dir", "")).resolve() != run_dir:
            raise ValueError("run directory is not the locked arm")
        monitor = Path(__file__).resolve().parents[2] / "scripts/alpha_holdem/v5_monitor.py"
        expected_monitor = lock.get("tools", {}).get("scripts/alpha_holdem/v5_monitor.py")
        expected_self = lock.get("tools", {}).get("scripts/alpha_holdem/v5_hybrid_h17_health_watch.py")
        if sha256(monitor) != expected_monitor or sha256(Path(__file__).resolve()) != expected_self:
            raise ValueError("health/monitor tool hash mismatch")
        if args.validate_only:
            atomic_json(status_path, {"schema_version": SCHEMA, "overall": "PASS", "state": "VALIDATE_ONLY_STATIC_CONTRACT_PASS", "arm": args.arm, "design_lock_sha256": args.expected_lock_sha256.lower()})
            return 0
        first_manifest_seen: float | None = None
        while True:
            manifest_path = run_dir / "run_manifest.json"
            if not manifest_path.is_file():
                atomic_json(status_path, {"schema_version": SCHEMA, "overall": "PENDING", "state": "WAITING_FOR_ARM", "arm": args.arm, "design_lock_sha256": args.expected_lock_sha256.lower()})
                time.sleep(max(0.1, args.poll_seconds))
                continue
            raw, manifest, attempts = read_json_snapshot(manifest_path)
            if first_manifest_seen is None:
                first_manifest_seen = time.monotonic()
            config = manifest.get("config") or {}
            if manifest.get("run_id") != arm.get("run_id") or config.get("h17_window_arm") != args.arm:
                raise ValueError("H17 manifest identity mismatch")
            startup_state = startup_log_gate(run_dir, first_manifest_seen, time.monotonic(), args.startup_log_timeout_seconds)
            if startup_state == "PENDING":
                atomic_json(status_path, {
                    "schema_version": SCHEMA,
                    "checked_at": datetime.now(timezone.utc).isoformat(),
                    "overall": "PENDING",
                    "state": "WAITING_FOR_STARTUP_LOG",
                    "arm": args.arm,
                    "design_lock_sha256": args.expected_lock_sha256.lower(),
                    "run_id": arm.get("run_id"),
                    "startup_log_timeout_seconds": args.startup_log_timeout_seconds,
                    "official_hands": 0,
                })
                time.sleep(max(0.1, args.poll_seconds))
                continue
            if startup_state == "TIMEOUT":
                raise TimeoutError(f"latest_train.log missing after {args.startup_log_timeout_seconds}s")
            view, provenance = prepare_view(run_dir, raw, manifest)
            completed = subprocess.run(
                [sys.executable, str(monitor), "--run-dir", str(view)],
                cwd=Path(__file__).resolve().parents[2],
                text=True,
                capture_output=True,
            )
            health = publish(run_dir, view, {**provenance, "manifest_read_attempts": attempts, "monitor_sha256": sha256(monitor)})
            latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
            exact = int(latest.get("iteration", -1)) == int(manifest.get("iteration", -2)) and int(latest.get("hands", -1)) == int(manifest.get("total_hands", -2))
            if completed.returncode != 0 or health.get("overall") == "FAIL":
                raise RuntimeError(f"monitor health failure exit={completed.returncode} overall={health.get('overall')}")
            state = "HEALTH_STREAM_READY" if exact and health.get("overall") == "PASS" else "HEALTH_STREAM_PENDING"
            atomic_json(status_path, {
                "schema_version": SCHEMA,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "overall": "PASS" if state == "HEALTH_STREAM_READY" else "PENDING",
                "state": state,
                "arm": args.arm,
                "design_lock_sha256": args.expected_lock_sha256.lower(),
                "run_id": arm.get("run_id"),
                "iteration": manifest.get("iteration"),
                "hands": manifest.get("total_hands"),
                "manifest_status": manifest.get("status"),
                "health_sha256": sha256(run_dir / "health_status.json"),
                "official_hands": 0,
            })
            if manifest.get("status") == "finished":
                if state != "HEALTH_STREAM_READY":
                    raise ValueError("finished endpoint lacks exact health PASS")
                return 0
            time.sleep(max(0.1, args.poll_seconds))
    except Exception as exc:
        atomic_json(status_path, {
            "schema_version": SCHEMA,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "overall": "FAIL_CLOSED",
            "state": "H17_HEALTH_PRODUCER_FAILURE",
            "arm": args.arm,
            "design_lock_sha256": args.expected_lock_sha256.lower(),
            "error": f"{type(exc).__name__}: {exc}",
            "official_hands": 0,
        })
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
