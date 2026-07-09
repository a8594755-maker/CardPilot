#!/usr/bin/env python3
"""
Periodically refresh v5_monitor.py for a V5 training run.

The gate watcher reads health_status.json but does not generate it. This helper
keeps health_status.json fresh for long-running continuation runs without
starting or stopping training.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


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
    cmd = [
        python,
        "scripts/alpha_holdem/v5_monitor.py",
        "--run-dir",
        str(run_dir),
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
