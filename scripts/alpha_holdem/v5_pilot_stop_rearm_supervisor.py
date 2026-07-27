#!/usr/bin/env python3
"""Canonically rearm only a proven transient pilot stop-watcher manifest-read failure."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

import psutil


TRANSIENT_ERRORS = {
    'manifest process_id mismatch',
    'manifest status is not running',
    'gate overall is not PASS',
    'gate target mismatch',
    'checkpoint iteration is not exact target',
    'checkpoint hands below pilot endpoint',
}


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--expected-pid', type=int, required=True)
    parser.add_argument('--status-json', required=True)
    parser.add_argument('--poll-seconds', type=int, default=2)
    args = parser.parse_args()
    repo = Path(args.repo).resolve()
    os.chdir(repo)
    run_dir = Path(args.run_dir).resolve()
    stop_status = run_dir / 'pilot_endpoint_stop_status.json'
    manifest_path = run_dir / 'run_manifest.json'
    supervisor_status = Path(args.status_json).resolve()
    recoveries = 0
    while True:
        stop = read_json(stop_status)
        if stop.get('overall') == 'PASS' and stop.get('state') == 'PILOT_STOPPED_AT_ENDPOINT':
            write_json(supervisor_status, {'checked_at': now(), 'overall': 'PASS', 'state': 'PILOT_STOPPED', 'recoveries': recoveries})
            return 0
        if stop.get('overall') != 'FAIL':
            write_json(supervisor_status, {'checked_at': now(), 'overall': 'PENDING', 'state': 'MONITORING', 'recoveries': recoveries})
            time.sleep(max(1, args.poll_seconds))
            continue
        errors = set(stop.get('errors') or [])
        if stop.get('state') != 'IDENTITY_OR_PROTOCOL_FAILURE' or not errors or not errors.issubset(TRANSIENT_ERRORS):
            write_json(supervisor_status, {'checked_at': now(), 'overall': 'FAIL', 'state': 'NONTRANSIENT_STOP_WATCHER_FAILURE', 'errors': sorted(errors)})
            return 1
        manifest = read_json(manifest_path)
        try:
            proc = psutil.Process(args.expected_pid)
            command = ' '.join(proc.cmdline())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            command = ''
        valid_live = (
            manifest.get('process_id') == args.expected_pid
            and manifest.get('status') == 'running'
            and bool(manifest.get('run_id'))
            and os.path.normcase(str(run_dir)) in os.path.normcase(command)
            and 'train_v5.py' in command
        )
        if not valid_live:
            write_json(supervisor_status, {'checked_at': now(), 'overall': 'FAIL', 'state': 'LIVE_IDENTITY_NOT_RECOVERED'})
            return 1
        result = subprocess.run([
            'powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
            'scripts/alpha_holdem/v5_rearm_watchers.ps1', '-RunDir', str(run_dir),
        ], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if result.returncode != 0:
            write_json(supervisor_status, {'checked_at': now(), 'overall': 'FAIL', 'state': 'CANONICAL_REARM_FAILED', 'exit_code': result.returncode})
            return 1
        recoveries += 1
        write_json(supervisor_status, {'checked_at': now(), 'overall': 'PENDING', 'state': 'CANONICAL_REARM_RECOVERED', 'recoveries': recoveries})
        ledger = repo / 'reports/v5_experiment_ledger.md'
        local = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')
        row = (
            f"\n| {local} | Pilot endpoint watcher transient manifest-read failure canonically rearmed | "
            f"Supervisor proved trainer PID{args.expected_pid}/run-dir/manifest identity had recovered and stop-watcher errors were a strict subset of the transient manifest plus pending-endpoint set, then invoked only v5_rearm_watchers.ps1. Recovery count {recoveries}; no trainer behavior change. "
            "[event_id=v5-pilot-stop-supervised-canonical-rearm] |\n"
        )
        with ledger.open('ab') as handle:
            handle.write(row.encode('utf-8'))
        time.sleep(max(1, args.poll_seconds))


if __name__ == '__main__':
    raise SystemExit(main())
