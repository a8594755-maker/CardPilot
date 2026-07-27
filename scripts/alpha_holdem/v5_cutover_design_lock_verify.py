#!/usr/bin/env python3
"""Machine fail-closed verifier for V5 trainer cutover design locks."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def normalized_path(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(os.fspath(path)))


def is_read_only(path: Path) -> bool:
    info = path.stat()
    attributes = getattr(info, 'st_file_attributes', 0)
    windows_flag = getattr(stat, 'FILE_ATTRIBUTE_READONLY', 0)
    if windows_flag:
        return bool(attributes & windows_flag)
    return not bool(info.st_mode & stat.S_IWUSR)


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise ValueError(f'{path} root is not an object')
    return payload


def verify(*, lock_path: Path, expected_lock_sha256: str, ledger_path: Path,
           source_checkpoint: Path, trainer_script: Path, new_run_id: str,
           design_arm: str, provenance_path: Path, planned_config: dict[str, Any],
           require_read_only: bool = True) -> dict[str, Any]:
    checks: list[dict[str, str]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({'name': name, 'status': 'PASS' if condition else 'FAIL', 'detail': detail})

    try:
        lock = load_json(lock_path)
    except Exception as exc:  # noqa: BLE001
        return {'overall': 'FAIL', 'checks': [{'name': 'lock_load', 'status': 'FAIL', 'detail': str(exc)}]}

    actual_lock_sha = sha256_path(lock_path)
    check('lock_sha256', actual_lock_sha == expected_lock_sha256.lower(),
          f'actual={actual_lock_sha} expected={expected_lock_sha256.lower()}')
    check('lock_status', lock.get('status') == 'LOCKED', f"status={lock.get('status')}")
    check('lock_schema', lock.get('schema_version') == 'v5.cutover_design_lock.v1',
          f"schema={lock.get('schema_version')}")
    check('lock_read_only', (not require_read_only) or is_read_only(lock_path),
          f'require_read_only={require_read_only} read_only={is_read_only(lock_path)}')
    try:
        locked_at = datetime.fromisoformat(str(lock.get('locked_at')).replace('Z', '+00:00'))
        check('locked_before_cutover', locked_at < datetime.now(timezone.utc), f'locked_at={locked_at.isoformat()}')
    except Exception as exc:  # noqa: BLE001
        check('locked_before_cutover', False, f'invalid locked_at: {exc}')

    source = lock.get('source_checkpoint') if isinstance(lock.get('source_checkpoint'), dict) else {}
    check('source_path', normalized_path(source.get('path', '')) == normalized_path(source_checkpoint),
          f"lock={source.get('path')} planned={source_checkpoint}")
    checkpoint_sha = sha256_path(source_checkpoint) if source_checkpoint.exists() else None
    check('source_sha256', checkpoint_sha == source.get('sha256'),
          f"actual={checkpoint_sha} lock={source.get('sha256')}")
    check('source_identity', source.get('iteration') == 31400 and source.get('hands') == 515989661,
          f"iteration={source.get('iteration')} hands={source.get('hands')}")

    trainer_sha = sha256_path(trainer_script) if trainer_script.exists() else None
    check('trainer_sha256', trainer_sha == lock.get('trainer_sha256'),
          f"actual={trainer_sha} lock={lock.get('trainer_sha256')}")
    locked_tools = lock.get('tool_sha256') if isinstance(lock.get('tool_sha256'), list) else []
    tool_errors = []
    for item in locked_tools:
        if not isinstance(item, dict) or not item.get('path') or not item.get('sha256'):
            tool_errors.append('invalid tool entry')
            continue
        tool_path = Path(str(item['path']))
        actual = sha256_path(tool_path) if tool_path.exists() else None
        if actual != item.get('sha256'):
            tool_errors.append(f"{tool_path}: actual={actual} lock={item.get('sha256')}")
    check('tool_sha256', len(locked_tools) >= 3 and not tool_errors,
          f'locked_tools={len(locked_tools)} errors={tool_errors}')

    arms = lock.get('arms') if isinstance(lock.get('arms'), dict) else {}
    arm = arms.get(design_arm) if isinstance(arms.get(design_arm), dict) else {}
    check('design_arm', design_arm in ('control', 'treatment') and bool(arm), f'arm={design_arm}')
    check('run_id', arm.get('run_id') == new_run_id, f"lock={arm.get('run_id')} planned={new_run_id}")
    check('planned_config', arm.get('expected_config') == planned_config,
          'planned config must exactly equal the immutable arm config')
    check('provenance_required', lock.get('assignment_provenance', {}).get('required') is True,
          f"required={lock.get('assignment_provenance', {}).get('required')}")
    check('provenance_path', normalized_path(arm.get('provenance_path', '')) == normalized_path(provenance_path),
          f"lock={arm.get('provenance_path')} planned={provenance_path}")

    if lock.get('design_id') == 'EXP-W1':
        control_config = (arms.get('control') or {}).get('expected_config')
        treatment_config = (arms.get('treatment') or {}).get('expected_config')
        if isinstance(control_config, dict) and isinstance(treatment_config, dict):
            config_keys = set(control_config) | set(treatment_config)
            config_differences = sorted(
                key for key in config_keys if control_config.get(key) != treatment_config.get(key)
            )
        else:
            config_differences = ['INVALID_CONFIG']
        check(
            'exp_w1_single_behavior_variable',
            config_differences == ['exp_w1_value_warmup_epochs']
            and control_config.get('exp_w1_value_warmup_epochs') == 0
            and treatment_config.get('exp_w1_value_warmup_epochs') == 8,
            f'differences={config_differences}',
        )
        method = lock.get('method') if isinstance(lock.get('method'), dict) else {}
        method_ok = (
            method.get('treatment') == 'VALUE_HEAD_ONLY_FIRST_ROLLOUT_WARMUP'
            and method.get('warmup_at_iteration') == 31401
            and method.get('treatment_epochs') == 8
            and method.get('control_epochs') == 0
            and method.get('whole_hand_heldout_fraction') == 0.20
            and method.get('minimum_relative_mse_reduction') == 0.02
            and method.get('reward_semantics') == 'UNCHANGED'
            and method.get('policy_and_trunk_update') == 'FORBIDDEN'
            and method.get('optimizer_state') == 'SOURCE_PRESERVED_VALUE_HEAD_EXTRA_STEPS_ONLY'
        )
        check('exp_w1_method', method_ok, f'method={method}')
        route = lock.get('route_evidence') if isinstance(lock.get('route_evidence'), dict) else {}
        check(
            'exp_w1_route_evidence',
            route.get('review_overall') == 'ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION'
            and route.get('exp_w1_eligible') is True
            and route.get('exp_w2_eligible') is False
            and route.get('new_behavior_authorized_by_review') is False
            and isinstance(route.get('researcher_review_sha256'), str)
            and isinstance(route.get('preregistration_review_sha256'), str),
            f'route={route}',
        )

    gates = lock.get('numerical_gates') if isinstance(lock.get('numerical_gates'), dict) else {}
    primary = gates.get('primary_100k_paired') if isinstance(gates.get('primary_100k_paired'), dict) else {}
    required_numeric = (
        primary.get('pairs') == 100000
        and primary.get('alpha') == 0.05
        and isinstance(primary.get('ci_formula'), str)
        and primary.get('pass_ci_lower_gt_bb100') == 0.0
        and isinstance(primary.get('max_ci_halfwidth_bb100'), (int, float))
        and isinstance(gates.get('abort'), dict)
        and isinstance(lock.get('rollback'), dict)
        and isinstance(lock.get('program_stop_rule'), dict)
    )
    check('numerical_gates', required_numeric, '100k/alpha/CI/pass/precision/abort/rollback/stop must be locked')

    tests = lock.get('tests') if isinstance(lock.get('tests'), dict) else {}
    test_results = tests.get('results') if isinstance(tests.get('results'), list) else []
    tests_pass = tests.get('overall') == 'PASS' and bool(test_results) and all(
        isinstance(item, dict) and item.get('status') == 'PASS' for item in test_results
    )
    check('tests', tests_pass, f"overall={tests.get('overall')} results={len(test_results)}")

    binding = lock.get('ledger_binding') if isinstance(lock.get('ledger_binding'), dict) else {}
    ledger_bytes = ledger_path.read_bytes() if ledger_path.exists() else b''
    prefix_bytes = int(binding.get('prefix_bytes') or 0)
    prefix_sha = hashlib.sha256(ledger_bytes[:prefix_bytes]).hexdigest() if prefix_bytes > 0 else None
    check('ledger_prefix_sha256', prefix_bytes <= len(ledger_bytes) and prefix_sha == binding.get('prefix_sha256'),
          f"prefix_bytes={prefix_bytes} actual={prefix_sha} lock={binding.get('prefix_sha256')}")
    ledger_text = ledger_bytes.decode('utf-8', errors='replace')
    marker = f"[event_id={binding.get('event_id')}]"
    check('ledger_event', marker in ledger_text and expected_lock_sha256.lower() in ledger_text.lower(),
          f'marker={marker} lock_sha_present={expected_lock_sha256.lower() in ledger_text.lower()}')

    overall = 'PASS' if all(item['status'] == 'PASS' for item in checks) else 'FAIL'
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'overall': overall,
        'design_id': lock.get('design_id'),
        'design_arm': design_arm,
        'new_run_id': new_run_id,
        'lock_sha256': actual_lock_sha,
        'checks': checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--design-lock', required=True)
    parser.add_argument('--expected-lock-sha256', required=True)
    parser.add_argument('--ledger', required=True)
    parser.add_argument('--source-checkpoint', required=True)
    parser.add_argument('--trainer-script', required=True)
    parser.add_argument('--new-run-id', required=True)
    parser.add_argument('--design-arm', choices=('control', 'treatment'), required=True)
    parser.add_argument('--provenance-path', required=True)
    parser.add_argument('--planned-config-base64', required=True)
    parser.add_argument('--out-json', required=True)
    args = parser.parse_args()
    try:
        planned = json.loads(base64.b64decode(args.planned_config_base64).decode('utf-8'))
    except Exception as exc:  # noqa: BLE001
        payload = {'overall': 'FAIL', 'checks': [{'name': 'planned_config_decode', 'status': 'FAIL', 'detail': str(exc)}]}
    else:
        payload = verify(
            lock_path=Path(args.design_lock),
            expected_lock_sha256=args.expected_lock_sha256.lower(),
            ledger_path=Path(args.ledger),
            source_checkpoint=Path(args.source_checkpoint),
            trainer_script=Path(args.trainer_script),
            new_run_id=args.new_run_id,
            design_arm=args.design_arm,
            provenance_path=Path(args.provenance_path),
            planned_config=planned,
        )
    out = Path(args.out_json)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if payload['overall'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
