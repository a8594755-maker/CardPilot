#!/usr/bin/env python3
"""
Periodically refresh v5_monitor.py for a V5 training run.

The gate watcher reads health_status.json but does not generate it. This helper
keeps health_status.json fresh for long-running continuation runs without
starting or stopping training.
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
from datetime import datetime
from pathlib import Path


H8_LOG_ONLY_TOKEN = re.compile(r"\s+vhcatch=[01](?=\s)")


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json_snapshot(
    path: Path, attempts: int = 5, delay_seconds: float = 0.02
) -> tuple[str | None, dict | None, int]:
    """Read one internally consistent JSON snapshot across non-atomic producer writes."""
    for attempt in range(1, max(1, attempts) + 1):
        try:
            raw = path.read_text(encoding="utf-8")
            value = json.loads(raw)
            if not isinstance(value, dict):
                raise ValueError("JSON root is not an object")
            return raw, value, attempt
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            if attempt < max(1, attempts):
                time.sleep(max(0.0, delay_seconds))
    return None, None, max(1, attempts)


def prepare_monitor_run_dir(run_dir: Path) -> tuple[Path, dict | None]:
    """Build a hybrid-window reporting-only log view for the frozen V5 monitor.

    H8/H9 add ``vhcatch=0/1`` to the human-readable training line.  The frozen
    monitor predates that token, so it otherwise reports zero parsed rows even
    though the canonical structured metrics are healthy.  Only that token is
    removed; the source log, manifest, stderr, and model artifacts are untouched.
    """
    manifest_path = run_dir / "run_manifest.json"
    manifest_text, manifest, manifest_read_attempts = read_json_snapshot(manifest_path)
    if manifest_text is None or manifest is None:
        return run_dir, None
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    window = None
    if config.get("h8_window_arm") in {"control", "treatment"}:
        window = "H8"
    elif config.get("h9_window_arm") in {"control", "treatment"}:
        window = "H9"
    if window is None:
        return run_dir, None
    source_log = run_dir / "latest_train.log"
    if not source_log.is_file():
        return run_dir, None
    source_text = source_log.read_text(encoding="utf-8", errors="replace")
    transformed_text, replacements = H8_LOG_ONLY_TOKEN.subn("", source_text)
    compatibility_dir = run_dir / ".h8_health_compat"
    compatibility_dir.mkdir(parents=True, exist_ok=True)
    compatibility_log = compatibility_dir / "latest_train.log"
    temporary_log = compatibility_log.with_suffix(".log.tmp")
    temporary_log.write_text(transformed_text, encoding="utf-8")
    source_stat = source_log.stat()
    os.utime(temporary_log, (source_stat.st_atime, source_stat.st_mtime))
    temporary_log.replace(compatibility_log)
    compatibility_manifest = compatibility_dir / "run_manifest.json"
    temporary_manifest = compatibility_manifest.with_suffix(".json.tmp")
    temporary_manifest.write_text(manifest_text, encoding="utf-8")
    temporary_manifest.replace(compatibility_manifest)
    stderr = run_dir / "console.err.log"
    if stderr.is_file():
        shutil.copy2(stderr, compatibility_dir / "console.err.log")
    else:
        (compatibility_dir / "console.err.log").write_bytes(b"")
    provenance = {
        "schema_version": "v5.hybrid.health_log_adapter.v2",
        "window": window,
        "source_run_dir": str(run_dir.resolve()),
        "source_log": str(source_log.resolve()),
        "source_log_sha256": file_sha256(source_log),
        "compatibility_log_sha256": file_sha256(compatibility_log),
        "manifest_snapshot_sha256": file_sha256(compatibility_manifest),
        "manifest_read_attempts": manifest_read_attempts,
        "removed_token": "vhcatch=[01]",
        "replacement_count": replacements,
        "source_line_count": len(source_text.splitlines()),
        "transformed_line_count": len(transformed_text.splitlines()),
        "frozen_monitor_sha256": file_sha256(Path("scripts/alpha_holdem/v5_monitor.py")),
    }
    (compatibility_dir / "adapter_provenance.json").write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return compatibility_dir, provenance


def publish_h8_health(run_dir: Path, monitor_dir: Path, provenance: dict) -> None:
    source = monitor_dir / "health_status.json"
    if not source.is_file():
        raise FileNotFoundError(source)
    health = json.loads(source.read_text(encoding="utf-8"))
    health["run_dir"] = str(run_dir.resolve())
    health["reporting_adapter"] = provenance
    destination = run_dir / "health_status.json"
    temporary = destination.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(health, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(destination)
    monitor_md = monitor_dir / "health_status.md"
    if monitor_md.is_file():
        text = monitor_md.read_text(encoding="utf-8").replace(
            str(monitor_dir.resolve()), str(run_dir.resolve())
        )
        destination_md = run_dir / "health_status.md"
        temporary_md = destination_md.with_suffix(".md.tmp")
        temporary_md.write_text(text, encoding="utf-8")
        temporary_md.replace(destination_md)


def log(message: str, path: Path | None) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def load_health(run_dir: Path) -> dict:
    path = run_dir / "health_status.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"overall": "WARN", "_load_error": str(exc)}


def run_monitor(python: str, run_dir: Path, args: argparse.Namespace) -> tuple[int, str]:
    monitor_dir, adapter = prepare_monitor_run_dir(run_dir)
    cmd = [
        python,
        "scripts/alpha_holdem/v5_monitor.py",
        "--run-dir",
        str(monitor_dir),
        "--preflop-call-warn-after-iter",
        str(args.preflop_call_warn_after_iter),
        "--preflop-call-warn",
        str(args.preflop_call_warn),
        "--preflop-call-fail",
        str(args.preflop_call_fail),
        "--preflop-dominance-warn",
        str(args.preflop_dominance_warn),
        "--preflop-dominance-fail",
        str(args.preflop_dominance_fail),
        "--preflop-allin-warn",
        str(args.preflop_allin_warn),
        "--preflop-allin-fail",
        str(args.preflop_allin_fail),
        "--stderr-recent-minutes",
        str(args.stderr_recent_minutes),
    ]
    proc = subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    if adapter is not None and (monitor_dir / "health_status.json").is_file():
        publish_h8_health(run_dir, monitor_dir, adapter)
    return proc.returncode, proc.stdout.strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=0.0)
    parser.add_argument("--exit-on-warn", action="store_true")
    parser.add_argument("--log-path")
    parser.add_argument("--preflop-call-warn-after-iter", type=int, default=200)
    parser.add_argument("--preflop-call-warn", type=float, default=0.03)
    parser.add_argument("--preflop-call-fail", type=float, default=0.005)
    parser.add_argument("--preflop-dominance-warn", type=float, default=0.90)
    parser.add_argument("--preflop-dominance-fail", type=float, default=0.97)
    parser.add_argument("--preflop-allin-warn", type=float, default=0.12)
    parser.add_argument("--preflop-allin-fail", type=float, default=0.25)
    parser.add_argument("--stderr-recent-minutes", type=float, default=5.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    log_path = Path(args.log_path) if args.log_path else None
    log(f"health watcher started run_dir={run_dir}", log_path)
    start = time.time()

    while True:
        code, output = run_monitor(args.python, run_dir, args)
        if output:
            for line in output.splitlines():
                log(f"monitor: {line}", log_path)
        if code != 0:
            log(f"monitor exited with code {code}", log_path)
            return code

        health = load_health(run_dir)
        overall = str(health.get("overall") or "UNKNOWN")
        latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
        iter_text = latest.get("iteration")
        hands_text = latest.get("hands")
        log(f"health={overall} iteration={iter_text} hands={hands_text}", log_path)

        if overall == "FAIL":
            return 1
        if args.exit_on_warn and overall == "WARN":
            return 1

        if args.timeout_seconds > 0 and (time.time() - start) >= args.timeout_seconds:
            log(f"timeout after {args.timeout_seconds:.1f}s", log_path)
            return 2

        time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
