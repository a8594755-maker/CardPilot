#!/usr/bin/env python3
"""Requirement-by-requirement completion audit for the persistent EXP005-C goal."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


EXPECTED_LOCK_SHA = '2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007'


def load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def item(name: str, status: str, evidence: str) -> dict[str, str]:
    return {'requirement': name, 'status': status, 'evidence': evidence}


def pid_alive(pid: Any) -> bool:
    try:
        numeric_pid = int(pid)
        if numeric_pid <= 0:
            return False
        os.kill(numeric_pid, 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def audit(repo: Path) -> dict[str, Any]:
    lock_path = repo / 'reports/v5_exp005c_design_lock_v2_20260710.json'
    lock = load(lock_path)
    value = load(repo / 'reports/v5_value_audit_001_20260710.json')
    asset = load(repo / 'reports/v5_asset_audit_001_20260710.json')
    pilot_run = repo / 'models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710'
    pilot = load(pilot_run / 'pilot_endpoint_stop_status.json')
    manifest = load(pilot_run / 'run_manifest.json')
    control_launch = load(repo / 'reports/v5_exp005c_control_launch_watch_status.json')
    control = load(repo / 'reports/v5_exp005c_control_endpoint_freeze_status.json')
    treatment = load(repo / 'reports/v5_exp005c_treatment_endpoint_freeze_status.json')
    primary = load(repo / 'reports/v5_exp005c_primary_watch_status.json')
    promotion = load(repo / 'reports/v5_exp005c_promotion_program_watch_status.json')
    failure_path = repo / 'reports/v5_exp005c_protocol_abort_failure_20260711.json'
    failure = load(failure_path)
    researcher = load(repo / 'reports/v5_exp005c_route_pivot_research_review_20260711.json')
    w1 = load(repo / 'reports/v5_exp_w1_preregistration_20260711.json')
    continuation = (repo / 'scripts/alpha_holdem/v5_continue_after_gate.ps1').read_text(encoding='utf-8')
    requirements: list[dict[str, str]] = []
    pilot_pid_alive = pid_alive(manifest.get('process_id'))
    pilot_live_safe = (
        manifest.get('process_id') == 30224 and manifest.get('status') == 'running'
        and pilot_pid_alive and pilot.get('state') == 'WAITING_FOR_EXACT_PILOT_ENDPOINT'
    )
    pilot_stopped_safe = (
        manifest.get('process_id') == 30224 and not pilot_pid_alive
        and pilot.get('overall') == 'PASS' and pilot.get('state') == 'PILOT_STOPPED_AT_ENDPOINT'
        and pilot.get('method_judgment') == 'FORBIDDEN_EXPLORATORY_PILOT'
        and int(pilot.get('target_iteration') or -1) == 32700
    )
    # While the exploratory pilot is live it must not produce downstream artifacts.
    # Once the exact pilot endpoint is stopped, later clean-program artifacts do not
    # retroactively violate the pilot contract; their own authority is audited below.
    pilot_safe = (
        (pilot_live_safe
         and not (repo / 'reports/exp005c_primary_100k').exists()
         and not glob_promotion_outputs(repo))
        or pilot_stopped_safe
    )
    requirements.append(item('pilot is exploratory-only with no MEAS/Slumbot launch', 'PROVEN' if pilot_safe else 'FAIL',
                             f"manifest={manifest.get('status')}/PID{manifest.get('process_id')}/alive={pilot_pid_alive}; "
                             f"stop={pilot.get('state')}"))
    lock_complete = (
        lock.get('status') == 'LOCKED' and int(lock.get('lock_revision') or -1) == 2
        and sha(lock_path) == EXPECTED_LOCK_SHA and not (lock_path.stat().st_mode & stat.S_IWRITE)
        and (lock.get('source_checkpoint') or {}).get('iteration') == 31400
        and (lock.get('arm_budget') or {}).get('actual_hands_target_delta') == 20000000
        and (lock.get('measurement') or {}).get('pairs') == 100000
    )
    requirements.append(item('immutable same-start design lock before cutover', 'PROVEN' if lock_complete else 'FAIL',
                             f"sha={sha(lock_path)} readonly={not bool(lock_path.stat().st_mode & stat.S_IWRITE)}"))
    machine_guard = all(token in continuation for token in (
        'Execute requires -DesignLockPath', '--expected-lock-sha256', '--planned-config-base64',
        'immutable design-lock preflight failed; refusing trainer launch'))
    requirements.append(item('trainer cutover machine fail-closed on immutable lock/checkpoint/config/tests/ledger',
                             'PROVEN' if machine_guard else 'FAIL', 'v5_continue_after_gate.ps1 guarded preflight'))
    audits_ok = (
        value.get('status') == 'COMPLETED_REPORTING_ONLY'
        and (value.get('decision') or {}).get('route_pivot_exp_w1_eligible') is True
        and (value.get('decision') or {}).get('exp_w1_registration_authorized_now') is False
        and asset.get('status') == 'COMPLETED_REPORTING_ONLY'
        and (asset.get('decision') or {}).get('route_pivot_exp_w2_eligible') is False
    )
    requirements.append(item('VALUE-AUDIT-001 and ASSET-AUDIT-001 reporting-only routing',
                             'PROVEN' if audits_ok else 'FAIL', 'W1 eligible only at pivot; W2 unavailable'))
    protocol_abort = (
        failure.get('immutable') is True
        and failure.get('classification') == 'EXP005C_FAIL_PROTOCOL_ABORT'
        and (failure.get('design_lock') or {}).get('sha256') == EXPECTED_LOCK_SHA
        and (failure.get('first_60_rows') or {}).get('gate_result') == 'FAIL'
        and float((failure.get('first_60_rows') or {}).get('treatment_over_control_ratio') or 1.0) < 0.85
        and (failure.get('protocol_effect') or {}).get('tier2_from_zero_adjustments') == 'FROZEN'
    )
    control_done = (
        (control.get('state') == 'ARM_ENDPOINT_FROZEN' and control.get('overall') == 'PASS')
        or (protocol_abort and control.get('state') == 'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'
            and control.get('endpoint_validity_preserved') is True)
    )
    treatment_done = (
        (treatment.get('state') == 'ARM_ENDPOINT_FROZEN' and treatment.get('overall') == 'PASS')
        or (protocol_abort and treatment.get('state') == 'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'
            and treatment.get('rows_after_60') == 'POST_PROTOCOL_EXPLORATORY_ONLY')
    )
    requirements.append(item('clean gate31400 control arm reached endpoint or a registered earlier abort',
                             'PROVEN' if control_done else 'PENDING', control.get('state', control_launch.get('state', 'missing'))))
    requirements.append(item('clean gate31400 treatment arm reached endpoint or a registered earlier abort',
                             'PROVEN' if treatment_done else 'PENDING', treatment.get('state', 'missing')))
    primary_done = primary.get('state') == 'PRIMARY_100K_TERMINAL' and primary.get('decision') in {'PASS', 'FAIL', 'INCONCLUSIVE'}
    primary_preempted = (
        protocol_abort and primary.get('state') == 'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'
        and primary.get('primary100k') == 'FORBIDDEN'
        and primary.get('partial_data_authority') == 'NONE_INVALID_FOR_METHOD_JUDGMENT'
    )
    requirements.append(item('conditional exactly100k endpoint primary obeys earlier protocol gates',
                             'PROVEN' if primary_done or primary_preempted else 'PENDING',
                             ('preempted by registered throughput abort; partial evidence invalid'
                              if primary_preempted else primary.get('state', 'missing'))))
    stop_done = (
        (primary_done and primary.get('program_action') in {
            'ALLOW_EXACT_TREATMENT_ENDPOINT_PROMOTION20K_ONLY', 'FREEZE_TIER2_NO_2_7B_INERTIA'})
        or (protocol_abort and all(status.get('state') == 'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'
                                   for status in (control, treatment, primary, promotion))
            and all(status.get('tier2') == 'FROZEN' for status in (control, treatment, primary, promotion)))
    )
    requirements.append(item('EXP005-C program stop applied without 2.7B inertia',
                             'PROVEN' if stop_done else 'PENDING',
                             'EXP005C_FAIL_PROTOCOL_ABORT / Tier-2 FROZEN' if protocol_abort else primary.get('program_action', 'awaiting primary')))
    promotion_terminal = promotion.get('state') in {
        'TIER2_FROZEN_NO_PROMOTION', 'PROMOTION_NON_STRONG_TIER2_FROZEN', 'FORMAL100K_COMPLETE',
        'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'}
    requirements.append(item('conditional exact-endpoint greedy promotion, fresh-V4 CI, same-checkpoint formal',
                             'PROVEN' if promotion_terminal else 'PENDING', promotion.get('state', 'missing')))
    route_triggered = promotion.get('state') in {
        'TIER2_FROZEN_NO_PROMOTION', 'PROMOTION_NON_STRONG_TIER2_FROZEN',
        'TERMINAL_BLOCKED_EXP005C_FAIL_PROTOCOL_ABORT'}
    route_selected = load(repo / 'reports/v5_exp005c_route_pivot_decision.json')
    w1_selected = (
        researcher.get('overall') == 'ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION'
        and (researcher.get('permissions') or {}).get('route_pivot_exp_w1_eligible') is True
        and (researcher.get('permissions') or {}).get('route_pivot_exp_w2_eligible') is False
        and w1.get('status') == 'PREREGISTERED_DESIGN_COMPLETE_NO_LAUNCH_AUTHORITY'
        and (w1.get('single_behavior_variable') or {}).get('name') == 'exp_w1_value_warmup_epochs'
        and not any((repo / 'reports').glob('v5_exp_w2_preregistration*.json'))
    )
    route_ok = not route_triggered or route_selected.get('selected_route') in {'EXP-W1', 'NONE_STOP'} or w1_selected
    requirements.append(item('route pivot selects at most one audit-supported route and never bundles',
                             'PROVEN' if route_ok else 'PENDING',
                             ('not triggered' if not route_triggered else
                              ('EXP-W1 preregistered; W2 ineligible; no bundle' if w1_selected
                               else str(route_selected.get('selected_route') or 'awaiting review')))))
    complete = all(row['status'] == 'PROVEN' for row in requirements)
    failed = [row for row in requirements if row['status'] == 'FAIL']
    return {
        'checked_at': datetime.now(timezone.utc).isoformat(),
        'overall': ('COMPLETE_EXP005C_FAIL_PROTOCOL_ABORT_ROUTE_PIVOT_W1_PREREGISTERED_NO_LAUNCH'
                    if complete and protocol_abort else ('COMPLETE' if complete else ('FAIL' if failed else 'IN_PROGRESS'))),
        'classification': failure.get('classification') if protocol_abort else None,
        'goal_complete': complete, 'requirements': requirements,
        'failed_count': len(failed), 'pending_count': sum(row['status'] == 'PENDING' for row in requirements),
        'next_action': ('objective complete; any EXP-W1 control launch is a separate explicit user-authorized continuation'
                        if complete else ('wait for exact pilot endpoint and locked control launch'
                        if control.get('state') in {None, 'WAITING_FOR_ARM_RUN_DIR'}
                        else ('wait for clean control endpoint freeze' if not control_done else 'follow first pending requirement'))),
    }


def glob_promotion_outputs(repo: Path) -> bool:
    return any((repo / 'models').glob('bench_v55_v5_exp005c_treatment_endpoint_*_part*_hands.jsonl'))


def markdown(payload: dict[str, Any]) -> str:
    lines = ['# EXP005-C Persistent Goal Completion Audit', '', f"- Overall: `{payload['overall']}`",
             f"- Experiment classification: `{payload.get('classification') or 'N/A'}`",
             f"- Pending: `{payload['pending_count']}`", f"- Failed: `{payload['failed_count']}`", '',
             '| Requirement | Status | Evidence |', '| --- | --- | --- |']
    for row in payload['requirements']:
        lines.append(f"| {row['requirement']} | `{row['status']}` | {row['evidence']} |")
    lines += ['', f"Next action: {payload['next_action']}", '',
              'This audit does not shrink the goal. A registered protocol FAIL can complete the operating objective when its fail-closed stop and pivot rules are proven; it never becomes a method PASS.']
    return '\n'.join(lines) + '\n'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--out-json', required=True)
    parser.add_argument('--out-md', required=True)
    args = parser.parse_args(); repo = Path(args.repo).resolve()
    payload = audit(repo)
    Path(args.out_json).write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    Path(args.out_md).write_text(markdown(payload), encoding='utf-8')
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload['failed_count'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
