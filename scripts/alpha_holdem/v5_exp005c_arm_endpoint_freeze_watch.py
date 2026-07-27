#!/usr/bin/env python3
"""Freeze and fail-closed audit the first completed EXP005-C arm endpoint."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil
import torch

from v5_assignment_provenance_audit import audit as audit_provenance


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def same_path(left: str | os.PathLike[str], right: str | os.PathLike[str]) -> bool:
    return os.path.normcase(os.path.abspath(left)) == os.path.normcase(os.path.abspath(right))


def config_errors(actual: dict[str, Any], expected: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    skip = {'assignment_provenance_schema'}
    for key, value in expected.items():
        if key in skip:
            continue
        if key not in actual:
            errors.append(f'manifest config missing {key}')
            continue
        got = actual[key]
        if isinstance(value, float) and isinstance(got, (int, float)):
            if abs(float(got) - value) > 1e-12:
                errors.append(f'manifest config {key} mismatch')
        elif got != value:
            errors.append(f'manifest config {key} mismatch')
    return errors


def endpoint_errors(*, manifest: dict[str, Any], checkpoint: dict[str, Any],
                    expected_run_id: str, expected_config: dict[str, Any],
                    expected_source: Path, minimum_hands: int,
                    maximum_overshoot: int) -> list[str]:
    errors: list[str] = []
    if manifest.get('run_id') != expected_run_id:
        errors.append('manifest run_id mismatch')
    if manifest.get('status') != 'finished':
        errors.append('manifest status is not finished')
    errors.extend(config_errors(manifest.get('config') or {}, expected_config))
    if not same_path(str(manifest.get('lineage_parent_checkpoint') or ''), expected_source):
        errors.append('lineage parent mismatch')
    manifest_iteration = int(manifest.get('iteration') or -1)
    manifest_hands = int(manifest.get('total_hands') or -1)
    checkpoint_iteration = int(checkpoint.get('iteration') or -1)
    checkpoint_hands = int(checkpoint.get('total_hands') or -1)
    if manifest_iteration != checkpoint_iteration:
        errors.append('manifest/checkpoint iteration mismatch')
    if manifest_hands != checkpoint_hands:
        errors.append('manifest/checkpoint hands mismatch')
    if manifest_hands < minimum_hands:
        errors.append('endpoint below fixed actual-hand minimum')
    if manifest_hands > minimum_hands + maximum_overshoot:
        errors.append('endpoint exceeds locked overshoot')
    if checkpoint.get('env_version') != 'v55' or checkpoint.get('obs_version') != 'v55':
        errors.append('checkpoint env/obs mismatch')
    if checkpoint.get('action_space_version') != '9slot_v5':
        errors.append('checkpoint action-space mismatch')
    return errors


def write_status(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--arm', choices=('control', 'treatment'), required=True)
    parser.add_argument('--design-lock', required=True)
    parser.add_argument('--expected-lock-sha256', required=True)
    parser.add_argument('--poll-seconds', type=int, default=30)
    parser.add_argument('--status-json', required=True)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    os.chdir(repo)
    lock_path = Path(args.design_lock).resolve()
    lock_sha = sha256_path(lock_path)
    lock = read_json(lock_path)
    arm = lock.get('arms', {}).get(args.arm, {})
    expected_config = arm.get('expected_config') or {}
    run_id = str(arm.get('run_id') or '')
    run_dir = Path(str(arm.get('run_dir') or '')).resolve()
    status_path = Path(args.status_json).resolve()
    source = Path(str(lock.get('source_checkpoint', {}).get('path') or '')).resolve()
    minimum_hands = int(lock.get('arm_budget', {}).get('minimum_endpoint_hands') or -1)
    max_overshoot = int(lock.get('arm_budget', {}).get('maximum_single_arm_overshoot_hands') or -1)
    provenance_path = Path(str(arm.get('provenance_path') or '')).resolve()

    static_errors: list[str] = []
    if lock_sha != args.expected_lock_sha256.lower():
        static_errors.append('design lock SHA mismatch')
    if lock.get('status') != 'LOCKED' or int(lock.get('lock_revision') or -1) != 2:
        static_errors.append('design lock status/revision mismatch')
    if not run_id or not expected_config or minimum_hands != 535989661 or max_overshoot != 50000:
        static_errors.append('arm or budget lock incomplete')
    locked_auditor = next(
        (item for item in lock.get('tool_sha256', [])
         if str(item.get('path', '')).replace('\\', '/').endswith('v5_assignment_provenance_audit.py')),
        {},
    )
    auditor_path = repo / 'scripts/alpha_holdem/v5_assignment_provenance_audit.py'
    if sha256_path(auditor_path) != locked_auditor.get('sha256'):
        static_errors.append('locked provenance auditor SHA mismatch')
    if static_errors:
        write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                   'state': 'STATIC_CONTRACT_FAILURE', 'errors': static_errors})
        return 1
    if args.validate_only:
        write_status(status_path, {'checked_at': now_iso(), 'overall': 'PASS',
                                   'state': 'VALIDATE_ONLY_STATIC_CONTRACT_PASS', 'arm': args.arm})
        return 0

    while True:
        manifest_path = run_dir / 'run_manifest.json'
        if not manifest_path.exists():
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'PENDING',
                                       'state': 'WAITING_FOR_ARM_RUN_DIR', 'arm': args.arm})
            time.sleep(max(1, args.poll_seconds))
            continue
        manifest = read_json(manifest_path)
        if not manifest:
            # Trainer manifests are replaced non-atomically; an empty/partial read is transient.
            time.sleep(max(1, args.poll_seconds))
            continue
        if manifest.get('run_id') != run_id:
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'ARM_IDENTITY_FAILURE', 'errors': ['run_id mismatch']})
            return 1
        status = str(manifest.get('status') or '')
        if status in {'initialized', 'running'}:
            pid = int(manifest.get('process_id') or -1)
            try:
                proc = psutil.Process(pid)
                command = ' '.join(proc.cmdline())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                command = ''
            if run_id not in command or 'train_v5.py' not in command:
                write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                           'state': 'ARM_PROCESS_IDENTITY_FAILURE', 'pid': pid})
                return 1
            live_config_errors = config_errors(manifest.get('config') or {}, expected_config)
            if live_config_errors:
                write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                           'state': 'ARM_CONFIG_FAILURE', 'errors': live_config_errors})
                return 1
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'PENDING',
                                       'state': 'ARM_RUNNING', 'arm': args.arm, 'pid': pid,
                                       'iteration': manifest.get('iteration'),
                                       'hands': manifest.get('total_hands')})
            time.sleep(max(1, args.poll_seconds))
            continue
        if status != 'finished':
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'UNEXPECTED_MANIFEST_STATUS', 'manifest_status': status})
            return 1

        pid = int(manifest.get('process_id') or -1)
        if pid > 0 and psutil.pid_exists(pid):
            time.sleep(max(1, args.poll_seconds))
            continue
        checkpoint_path = run_dir / 'latest.pt'
        if not checkpoint_path.exists():
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'ENDPOINT_CHECKPOINT_MISSING'})
            return 1
        checkpoint = torch.load(checkpoint_path, map_location='cpu', weights_only=False)
        errors = endpoint_errors(
            manifest=manifest,
            checkpoint=checkpoint,
            expected_run_id=run_id,
            expected_config=expected_config,
            expected_source=source,
            minimum_hands=minimum_hands,
            maximum_overshoot=max_overshoot,
        )
        endpoint_iteration = int(checkpoint.get('iteration') or -1)
        endpoint_hands = int(checkpoint.get('total_hands') or -1)
        health_path = run_dir / 'health_status.json'
        health = read_json(health_path)
        health_iteration = int((health.get('latest') or {}).get('iteration') or -1)
        health_hands = int((health.get('latest') or {}).get('hands') or -1)
        if health_iteration < endpoint_iteration or health_hands < endpoint_hands:
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'PENDING',
                                       'state': 'WAITING_FOR_EXACT_ENDPOINT_HEALTH',
                                       'endpoint_iteration': endpoint_iteration,
                                       'health_iteration': health_iteration})
            time.sleep(max(1, args.poll_seconds))
            continue
        if (
            health.get('overall') != 'PASS'
            or health.get('run_id') != run_id
            or health_iteration != endpoint_iteration
            or health_hands != endpoint_hands
        ):
            errors.append('exact endpoint health identity/PASS failure')
        stderr_path = run_dir / 'console.err.log'
        if not stderr_path.exists() or stderr_path.stat().st_size != 0:
            errors.append('trainer stderr is missing or nonempty')
        provenance = audit_provenance(
            provenance_path,
            expected_run_id=run_id,
            expected_mode=str(expected_config.get('opponent_assignment')),
            expected_workers=int(expected_config.get('workers')),
            expected_groups=int(expected_config.get('opponent_groups')),
            expected_worker_seed_base=int(expected_config.get('worker_seed_base')),
            expected_first_iteration=31401,
            expected_last_iteration=endpoint_iteration,
        )
        if provenance.get('overall') != 'PASS':
            errors.append('assignment provenance audit failed')
        provenance_out = run_dir / f'exp005c_{args.arm}_assignment_provenance_audit.json'
        write_status(provenance_out, provenance)
        if errors:
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'ENDPOINT_AUDIT_FAILURE', 'errors': errors,
                                       'provenance_audit': str(provenance_out)})
            return 1

        frozen = run_dir / f'v5_exp005c_{args.arm}_endpoint.pt'
        if frozen.exists():
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'FROZEN_ENDPOINT_ALREADY_EXISTS'})
            return 1
        shutil.copy2(checkpoint_path, frozen)
        source_sha = sha256_path(checkpoint_path)
        frozen_sha = sha256_path(frozen)
        if source_sha != frozen_sha:
            frozen.unlink(missing_ok=True)
            write_status(status_path, {'checked_at': now_iso(), 'overall': 'FAIL',
                                       'state': 'FROZEN_ENDPOINT_COPY_HASH_MISMATCH'})
            return 1
        payload = {
            'checked_at': now_iso(), 'overall': 'PASS', 'state': 'ARM_ENDPOINT_FROZEN',
            'arm': args.arm, 'run_id': run_id, 'iteration': endpoint_iteration,
            'hands': int(checkpoint.get('total_hands')), 'checkpoint_path': str(frozen),
            'checkpoint_sha256': frozen_sha, 'source_checkpoint': str(source),
            'design_lock_sha256': lock_sha, 'provenance_audit': str(provenance_out),
            'health_path': str(health_path), 'health_overall': health.get('overall'),
            'trainer_stderr_path': str(stderr_path), 'trainer_stderr_empty': True,
            'method_judgment': 'PENDING_BOTH_ARMS_AND_PRIMARY_100K',
            'slumbot_authority': 'NONE',
        }
        write_status(status_path, payload)
        ledger = repo / 'reports/v5_experiment_ledger.md'
        local_time = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')
        row = (
            f"\n| {local_time} | EXP005-C {args.arm} endpoint frozen and audited | "
            f"Run {run_id} naturally finished its locked fixed20M budget at iter{endpoint_iteration} / "
            f"{payload['hands']:,} hands. Exact config/lineage/checkpoint identity, max50k overshoot, "
            f"and locked assignment-provenance audit PASS; frozen SHA256 {frozen_sha}. "
            "This is endpoint validity only, not method PASS/FAIL and no MEAS/Slumbot/strength authority. "
            f"[event_id=v5-exp005c-{args.arm}-endpoint-frozen] |\n"
        )
        with ledger.open('ab') as handle:
            handle.write(row.encode('utf-8'))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
