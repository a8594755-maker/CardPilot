#!/usr/bin/env python3
"""Launch and audit the locked EXP005-C 100k common-deal primary after both arms."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n', encoding='utf-8')


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def locked_classification(summary: dict[str, Any], audit: dict[str, Any]) -> tuple[str, str]:
    if audit.get('status') != 'PASS':
        return 'FAIL', 'BUNDLE_AUDIT_FAILED'
    effects = summary.get('primary_effects') or {}
    names = ('paired_native_axis_delta', 'post_vs_pre_direct')
    if any(name not in effects for name in names):
        return 'FAIL', 'PRIMARY_EFFECT_MISSING'
    halfwidths = [float(effects[name]['ci95_halfwidth_bb100']) for name in names]
    lowers = [float(effects[name]['ci95_lower_bb100']) for name in names]
    uppers = [float(effects[name]['ci95_upper_bb100']) for name in names]
    if any(width > 20.0 for width in halfwidths):
        return 'INCONCLUSIVE', 'LOCKED_PRECISION_GATE_FAILED'
    if all(lower > 0.0 for lower in lowers):
        return 'PASS', 'BOTH_LOCKED_PRIMARY_LOWER_BOUNDS_POSITIVE'
    if any(upper <= 0.0 for upper in uppers):
        return 'FAIL', 'LOCKED_PRIMARY_NONPOSITIVE_UPPER_BOUND'
    return 'INCONCLUSIVE', 'LOCKED_PRIMARY_OVERLAPS_ZERO'


def active_trainers() -> list[int]:
    pids: list[int] = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            command = ' '.join(proc.info.get('cmdline') or [])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        if 'scripts\\alpha_holdem\\train_v5.py' in command or 'scripts/alpha_holdem/train_v5.py' in command:
            pids.append(int(proc.info['pid']))
    return pids


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--design-lock', required=True)
    parser.add_argument('--expected-lock-sha256', required=True)
    parser.add_argument('--control-status', required=True)
    parser.add_argument('--treatment-status', required=True)
    parser.add_argument('--status-json', required=True)
    parser.add_argument('--poll-seconds', type=int, default=30)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    os.chdir(repo)
    lock_path = Path(args.design_lock).resolve()
    lock = read_json(lock_path)
    lock_sha = sha256_path(lock_path)
    status_path = Path(args.status_json).resolve()
    measurement = lock.get('measurement') or {}
    native = Path(str((measurement.get('native_anchor') or {}).get('path') or '')).resolve()
    tools = {str(item.get('path')).replace('\\', '/'): item.get('sha256') for item in lock.get('tool_sha256', [])}
    evaluator = repo / 'scripts/alpha_holdem/v5_meas001_common_deal_eval.py'
    auditor = repo / 'scripts/alpha_holdem/v5_meas001_bundle_audit.py'
    static_errors: list[str] = []
    if lock_sha != args.expected_lock_sha256.lower() or lock.get('status') != 'LOCKED' or int(lock.get('lock_revision') or -1) != 2:
        static_errors.append('design lock identity mismatch')
    if int(measurement.get('pairs') or -1) != 100000 or int(measurement.get('seed') or -1) != 2026071051:
        static_errors.append('measurement pair/seed lock mismatch')
    if measurement.get('pre_role') != 'control endpoint' or measurement.get('post_role') != 'treatment endpoint':
        static_errors.append('measurement role lock mismatch')
    if sha256_path(evaluator) != tools.get('scripts/alpha_holdem/v5_meas001_common_deal_eval.py'):
        static_errors.append('locked evaluator SHA mismatch')
    if sha256_path(auditor) != tools.get('scripts/alpha_holdem/v5_meas001_bundle_audit.py'):
        static_errors.append('locked auditor SHA mismatch')
    if not native.exists() or sha256_path(native) != (measurement.get('native_anchor') or {}).get('sha256'):
        static_errors.append('native anchor SHA mismatch')
    if static_errors:
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'STATIC_CONTRACT_FAILURE', 'errors': static_errors})
        return 1
    if args.validate_only:
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'VALIDATE_ONLY_STATIC_CONTRACT_PASS'})
        return 0

    while True:
        control = read_json(Path(args.control_status))
        treatment = read_json(Path(args.treatment_status))
        if control.get('overall') == 'FAIL' or treatment.get('overall') == 'FAIL':
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'ARM_ENDPOINT_FAILURE'})
            return 1
        ready = all(item.get('overall') == 'PASS' and item.get('state') == 'ARM_ENDPOINT_FROZEN' for item in (control, treatment))
        if not ready:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'PENDING', 'state': 'WAITING_FOR_BOTH_FROZEN_ENDPOINTS'})
            time.sleep(max(1, args.poll_seconds))
            continue
        errors: list[str] = []
        for expected_arm, item in (('control', control), ('treatment', treatment)):
            endpoint = Path(str(item.get('checkpoint_path') or ''))
            if item.get('arm') != expected_arm or item.get('design_lock_sha256') != lock_sha:
                errors.append(f'{expected_arm} endpoint identity mismatch')
            elif not endpoint.exists() or sha256_path(endpoint) != item.get('checkpoint_sha256'):
                errors.append(f'{expected_arm} endpoint hash mismatch')
        if abs(int(control.get('hands') or -1) - int(treatment.get('hands') or -1)) > 50000:
            errors.append('between-arm endpoint hand difference exceeds lock')
        trainers = active_trainers()
        if trainers:
            errors.append(f'trainer still alive: {trainers}')
        out_dir = repo / 'reports/exp005c_primary_100k'
        outputs = {
            'manifest': out_dir / 'manifest.json',
            'source_bundle': out_dir / 'source_bundle.json',
            'pairs': out_dir / 'aligned_pairs.jsonl',
            'summary': out_dir / 'summary.json',
            'summary_md': out_dir / 'summary.md',
            'execution': out_dir / 'execution.json',
            'audit': out_dir / 'bundle_audit.json',
            'audit_md': out_dir / 'bundle_audit.md',
        }
        if out_dir.exists() or any(path.exists() for path in outputs.values()):
            errors.append('primary output already exists; refusing duplicate/adaptive run')
        if errors:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'PRIMARY_PRECONDITION_FAILURE', 'errors': errors})
            return 1
        out_dir.mkdir(parents=True, exist_ok=False)
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PENDING', 'state': 'PRIMARY_100K_RUNNING',
                                 'pairs': 100000, 'seed': 2026071051, 'priority': 'below-normal'})
        command = [
            sys.executable, str(evaluator), '--pre', str(control['checkpoint_path']), '--post', str(treatment['checkpoint_path']),
            '--native', str(native), '--pre-label', 'EXP005-C control endpoint', '--post-label', 'EXP005-C treatment endpoint',
            '--native-label', 'v55 75M native anchor', '--expected-pre-iteration', str(control['iteration']),
            '--expected-pre-hands', str(control['hands']), '--expected-post-iteration', str(treatment['iteration']),
            '--expected-post-hands', str(treatment['hands']), '--expected-native-iteration', str(measurement['native_anchor']['iteration']),
            '--expected-native-hands', str(measurement['native_anchor']['hands']), '--pairs', '100000', '--seed', '2026071051',
            '--starting-stack', '200', '--anchor-ood-max', '0.15', '--device', 'cpu', '--priority', 'below-normal',
            '--out-manifest', str(outputs['manifest']), '--out-source-bundle', str(outputs['source_bundle']),
            '--out-pairs-jsonl', str(outputs['pairs']), '--out-json', str(outputs['summary']), '--out-md', str(outputs['summary_md']),
            '--execution-json', str(outputs['execution']),
        ]
        eval_log = (out_dir / 'evaluator.out.log').open('w', encoding='utf-8')
        eval_err = (out_dir / 'evaluator.err.log').open('w', encoding='utf-8')
        result = subprocess.run(command, stdout=eval_log, stderr=eval_err, check=False)
        eval_log.close(); eval_err.close()
        if result.returncode != 0:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'PRIMARY_EVALUATOR_FAILED', 'exit_code': result.returncode})
            return 1
        audit_cmd = [sys.executable, str(auditor), '--summary', str(outputs['summary']), '--manifest', str(outputs['manifest']),
                     '--source-bundle', str(outputs['source_bundle']), '--pairs-jsonl', str(outputs['pairs']),
                     '--execution', str(outputs['execution']), '--out-json', str(outputs['audit']), '--out-md', str(outputs['audit_md'])]
        audit_result = subprocess.run(audit_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=False)
        if audit_result.returncode != 0:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'PRIMARY_BUNDLE_AUDIT_FAILED',
                                     'exit_code': audit_result.returncode, 'stderr': audit_result.stderr[-2000:]})
            return 1
        summary = read_json(outputs['summary']); audit = read_json(outputs['audit'])
        decision, reason = locked_classification(summary, audit)
        if summary.get('measurement', {}).get('status') != decision:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'LOCKED_CLASSIFICATION_MISMATCH',
                                     'evaluator': summary.get('measurement', {}).get('status'), 'locked': decision, 'reason': reason})
            return 1
        action = 'ALLOW_EXACT_TREATMENT_ENDPOINT_PROMOTION20K_ONLY' if decision == 'PASS' else 'FREEZE_TIER2_NO_2_7B_INERTIA'
        payload = {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'PRIMARY_100K_TERMINAL',
                   'decision': decision, 'reason': reason, 'program_action': action,
                   'summary': str(outputs['summary']), 'bundle_audit': str(outputs['audit']),
                   'control_checkpoint_sha256': control['checkpoint_sha256'],
                   'treatment_checkpoint_sha256': treatment['checkpoint_sha256'],
                   'slumbot_strength_claim': 'NONE'}
        write_json(status_path, payload)
        ledger = repo / 'reports/v5_experiment_ledger.md'
        local = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')
        row = (f"\n| {local} | EXP005-C exactly100k common-deal primary terminal {decision} | "
               f"Immutable endpoint identities and locked evaluator/auditor bundle PASS; reason {reason}; program action {action}. "
               "This is method evidence only, not Slumbot/V4/L5/L6 strength. "
               "[event_id=v5-exp005c-primary-100k-terminal] |\n")
        with ledger.open('ab') as handle: handle.write(row.encode('utf-8'))
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
