#!/usr/bin/env python3
"""Fail-closed stop watcher for the exploratory EXP-005 pilot endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def preconditions(*, run_dir: Path, expected_pid: int, target_iteration: int,
                  min_hands: int, gate: dict[str, Any], manifest: dict[str, Any],
                  process_cmdline: list[str] | None) -> list[str]:
    errors: list[str] = []
    run_id = str(manifest.get('run_id') or '')
    if int(manifest.get('process_id') or -1) != expected_pid:
        errors.append('manifest process_id mismatch')
    if str(manifest.get('status')) != 'running':
        errors.append('manifest status is not running')
    command = ' '.join(process_cmdline or [])
    if 'train_v5.py' not in command or os.path.normcase(str(run_dir.resolve())) not in os.path.normcase(command):
        errors.append('trainer process command identity mismatch')
    if gate.get('overall') != 'PASS':
        errors.append('gate overall is not PASS')
    if int(gate.get('target_iteration') or -1) != target_iteration:
        errors.append('gate target mismatch')
    checkpoint_iteration = gate.get('checkpoint_iteration')
    checkpoint_hands = gate.get('checkpoint_hands')
    if checkpoint_iteration is None and isinstance(gate.get('checkpoint'), dict):
        checkpoint_iteration = gate['checkpoint'].get('iteration')
    if checkpoint_hands is None and isinstance(gate.get('checkpoint'), dict):
        checkpoint_hands = gate['checkpoint'].get('total_hands')
    if int(checkpoint_iteration or -1) != target_iteration:
        errors.append('checkpoint iteration is not exact target')
    if int(checkpoint_hands or -1) < min_hands:
        errors.append('checkpoint hands below pilot endpoint')
    gate_run_id = gate.get('run_id')
    if gate_run_id and str(gate_run_id) != run_id:
        errors.append('gate run_id mismatch')
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', required=True)
    parser.add_argument('--expected-pid', type=int, required=True)
    parser.add_argument('--target-iteration', type=int, required=True)
    parser.add_argument('--min-hands', type=int, required=True)
    parser.add_argument('--poll-seconds', type=int, default=30)
    parser.add_argument('--status-json', required=True)
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    status_path = Path(args.status_json)
    gate_path = run_dir / f'gate_{args.target_iteration}_status.json'
    manifest_path = run_dir / 'run_manifest.json'
    previous = load_json(status_path)
    if previous.get('overall') == 'PASS' and previous.get('state') == 'PILOT_STOPPED_AT_ENDPOINT':
        print('pilot endpoint already stopped')
        return 0

    while True:
        gate = load_json(gate_path)
        manifest = load_json(manifest_path)
        try:
            process = psutil.Process(args.expected_pid)
            cmdline = process.cmdline()
        except (psutil.NoSuchProcess, psutil.AccessDenied) as exc:
            payload = {
                'checked_at': now_iso(),
                'overall': 'FAIL',
                'state': 'TRAINER_IDENTITY_UNAVAILABLE_BEFORE_ENDPOINT_STOP',
                'detail': str(exc),
                'expected_pid': args.expected_pid,
            }
            write_json(status_path, payload)
            print(json.dumps(payload))
            return 1
        errors = preconditions(
            run_dir=run_dir,
            expected_pid=args.expected_pid,
            target_iteration=args.target_iteration,
            min_hands=args.min_hands,
            gate=gate,
            manifest=manifest,
            process_cmdline=cmdline,
        )
        endpoint_pending_only = all(
            message in {
                'gate overall is not PASS',
                'gate target mismatch',
                'checkpoint iteration is not exact target',
                'checkpoint hands below pilot endpoint',
            }
            for message in errors
        )
        if errors and not endpoint_pending_only:
            payload = {
                'checked_at': now_iso(),
                'overall': 'FAIL',
                'state': 'IDENTITY_OR_PROTOCOL_FAILURE',
                'errors': errors,
                'expected_pid': args.expected_pid,
            }
            write_json(status_path, payload)
            print(json.dumps(payload))
            return 1
        if errors:
            payload = {
                'checked_at': now_iso(),
                'overall': 'PENDING',
                'state': 'WAITING_FOR_EXACT_PILOT_ENDPOINT',
                'errors': errors,
                'expected_pid': args.expected_pid,
                'target_iteration': args.target_iteration,
                'min_hands': args.min_hands,
            }
            write_json(status_path, payload)
            time.sleep(max(1, args.poll_seconds))
            continue

        checkpoint_path = run_dir / 'latest.pt'
        checkpoint_sha = sha256_path(checkpoint_path)
        children = process.children(recursive=True)
        for child in children:
            try:
                child.terminate()
            except psutil.Error:
                pass
        try:
            process.terminate()
        except psutil.Error:
            pass
        _, alive = psutil.wait_procs(children + [process], timeout=15)
        for item in alive:
            try:
                item.kill()
            except psutil.Error:
                pass
        time.sleep(1)
        still_alive = psutil.pid_exists(args.expected_pid)
        payload = {
            'checked_at': now_iso(),
            'overall': 'FAIL' if still_alive else 'PASS',
            'state': 'STOP_FAILED' if still_alive else 'PILOT_STOPPED_AT_ENDPOINT',
            'run_id': manifest.get('run_id'),
            'stopped_pid': args.expected_pid,
            'target_iteration': args.target_iteration,
            'checkpoint_iteration': gate.get('checkpoint_iteration'),
            'checkpoint_hands': gate.get('checkpoint_hands'),
            'checkpoint_path': str(checkpoint_path),
            'checkpoint_sha256': checkpoint_sha,
            'method_judgment': 'FORBIDDEN_EXPLORATORY_PILOT',
            'meas001': 'FORBIDDEN',
            'promotion20k': 'FORBIDDEN',
            'formal100k': 'FORBIDDEN',
            'program_stop_reason': 'pilot endpoint reached; no 2.7B inertia',
        }
        write_json(status_path, payload)
        print(json.dumps(payload, indent=2))
        return 1 if still_alive else 0


if __name__ == '__main__':
    raise SystemExit(main())
