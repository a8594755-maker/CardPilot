#!/usr/bin/env python3
"""After EXP005-C PASS, lock and run exact-endpoint promotion/formal routing."""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import stat
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


LOCK_SHA = '2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007'
V4_MODEL_SHA = '0ac447e4d37f86936fcd6991047450f1d45e0d5e5f3f50fdc27b4076336b01c5'


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception:
        return {}
    return value if isinstance(value, dict) else {}


def write_json(path: Path, value: dict[str, Any], *, exclusive: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = 'x' if exclusive else 'w'
    with path.open(mode, encoding='utf-8') as handle:
        json.dump(value, handle, indent=2, sort_keys=True); handle.write('\n')


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def combined_strong(*, pipeline_status: dict[str, Any], promotion_gate: dict[str, Any],
                    relative: dict[str, Any], expected_checkpoint_sha: str) -> tuple[bool, list[str]]:
    blockers: list[str] = []
    if pipeline_status.get('state') != 'PASS': blockers.append('pipeline state not PASS')
    audit = (pipeline_status.get('benchmark_result') or {}).get('artifact_audit') or {}
    if audit.get('overall') != 'PASS': blockers.append('full artifact audit not PASS')
    if promotion_gate.get('overall') != 'PASS': blockers.append('promotion gate artifact not PASS')
    if not (promotion_gate.get('decisions') or {}).get('promotion_20k_strong'): blockers.append('built-in promotion_20k_strong false')
    if relative.get('overall') != 'PASS' or not relative.get('relative_v4_pass'): blockers.append('fresh-V4 relative CI lower not positive')
    checkpoint = Path(str(promotion_gate.get('checkpoint_path') or ''))
    if not checkpoint.exists() or sha256_path(checkpoint) != expected_checkpoint_sha: blockers.append('promotion checkpoint hash mismatch')
    return not blockers, blockers


def append_ledger(repo: Path, text: str) -> None:
    local = datetime.now().astimezone().strftime('%Y-%m-%d %H:%M')
    with (repo / 'reports/v5_experiment_ledger.md').open('ab') as handle:
        handle.write(f"\n| {local} | {text} |\n".encode('utf-8'))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default=r'C:\Users\a8594\CardPilot')
    parser.add_argument('--primary-status', required=True)
    parser.add_argument('--treatment-status', required=True)
    parser.add_argument('--status-json', required=True)
    parser.add_argument('--poll-seconds', type=int, default=30)
    parser.add_argument('--validate-only', action='store_true')
    args = parser.parse_args()
    repo = Path(args.repo).resolve(); os.chdir(repo)
    status_path = Path(args.status_json).resolve()
    main_lock = repo / 'reports/v5_exp005c_design_lock_v2_20260710.json'
    v4_model = repo / 'models/alpha_holdem_v4_final.pt'
    v4_report = repo / 'reports/v4_vs_slumbot_fresh_20260709_final.json'
    v4_hands = sorted((repo / 'tmp/v4_vs_slumbot_fresh').glob('w*_hands.jsonl'))
    pipeline = repo / 'scripts/alpha_holdem/v5_slumbot_benchmark_watch.py'
    relative_tool = repo / 'scripts/alpha_holdem/v5_relative_v4_ci.py'
    endpoint_tool = repo / 'scripts/alpha_holdem/v5_exp005c_arm_endpoint_freeze_watch.py'
    self_path = Path(__file__).resolve()
    static_errors: list[str] = []
    if sha256_path(main_lock) != LOCK_SHA: static_errors.append('main design lock SHA mismatch')
    if sha256_path(v4_model) != V4_MODEL_SHA: static_errors.append('V4 model SHA mismatch')
    if len(v4_hands) != 12: static_errors.append('fresh V4 hand files != 12')
    v4_summary = read_json(v4_report)
    if (v4_summary.get('result') or {}).get('hands') != 20400: static_errors.append('fresh V4 report hand count mismatch')
    for path in (pipeline, relative_tool, endpoint_tool, self_path):
        if not path.exists(): static_errors.append(f'missing tool {path.name}')
    if static_errors:
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'STATIC_CONTRACT_FAILURE', 'errors': static_errors})
        return 1
    if args.validate_only:
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'VALIDATE_ONLY_STATIC_CONTRACT_PASS'})
        return 0

    while True:
        primary = read_json(Path(args.primary_status))
        treatment = read_json(Path(args.treatment_status))
        if primary.get('overall') == 'FAIL' or treatment.get('overall') == 'FAIL':
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'UPSTREAM_FAILURE'})
            return 1
        if primary.get('state') != 'PRIMARY_100K_TERMINAL' or treatment.get('state') != 'ARM_ENDPOINT_FROZEN':
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'PENDING', 'state': 'WAITING_FOR_PRIMARY_AND_TREATMENT_ENDPOINT'})
            time.sleep(max(1, args.poll_seconds)); continue
        if primary.get('decision') != 'PASS':
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'TIER2_FROZEN_NO_PROMOTION',
                                     'primary_decision': primary.get('decision'), 'route_review_required': True})
            return 0
        treatment_checkpoint = Path(str(treatment.get('checkpoint_path') or '')).resolve()
        treatment_sha = str(treatment.get('checkpoint_sha256') or '')
        if not treatment_checkpoint.exists() or sha256_path(treatment_checkpoint) != treatment_sha:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'TREATMENT_ENDPOINT_HASH_FAILURE'})
            return 1

        promotion_lock_path = repo / 'reports/v5_exp005c_promotion_design_lock.json'
        ledger = repo / 'reports/v5_experiment_ledger.md'
        ledger_bytes = ledger.read_bytes()
        promotion_tag = 'v5_exp005c_treatment_endpoint_promotion20k'
        formal_tag = 'v5_exp005c_treatment_endpoint_formal100k'
        promotion_lock = {
            'schema_version': 'v5.exp005c.promotion_lock.v1', 'status': 'LOCKED', 'locked_at': now_iso(),
            'main_design_lock_sha256': LOCK_SHA,
            'primary_status_path': str(Path(args.primary_status).resolve()), 'primary_status_sha256': sha256_path(Path(args.primary_status)),
            'treatment_checkpoint': str(treatment_checkpoint), 'treatment_checkpoint_sha256': treatment_sha,
            'treatment_iteration': treatment.get('iteration'), 'treatment_hands': treatment.get('hands'),
            'promotion': {'policy': 'greedy-direct', 'sessions': 12, 'hands_per_session': 1700, 'hands': 20400,
                          'launch_path': 'direct', 'priority': 'BelowNormal', 'tag': promotion_tag,
                          'full_bundle_required': True, 'no_quality_gate_rationale': 'EXP005-C primary PASS is the locked method quality gate'},
            'relative_v4': {'method': 'independent Welch 95% CI', 'pass_rule': 'lower_bound > 0',
                            'point_estimate_only_forbidden': True, 'v4_model': str(v4_model),
                            'v4_model_sha256': V4_MODEL_SHA, 'v4_report': str(v4_report),
                            'v4_report_sha256': sha256_path(v4_report),
                            'v4_hand_files': [{'path': str(p), 'sha256': sha256_path(p)} for p in v4_hands]},
            'formal': {'authorized_only_if_combined_promotion_20k_strong': True, 'policy': 'greedy-direct',
                       'sessions': 20, 'hands_per_session': 5000, 'hands': 100000, 'tag': formal_tag,
                       'same_checkpoint_required': True, 'priority': 'BelowNormal'},
            'program_stop': {'promotion_non_strong': 'FREEZE_TIER2_AND_ROUTE_REVIEW',
                             'promotion_strong': 'ALLOW_EXACT_SAME_CHECKPOINT_FORMAL100K'},
            'tool_sha256': {str(path.relative_to(repo)).replace('\\', '/'): sha256_path(path)
                            for path in (pipeline, relative_tool, endpoint_tool, self_path)},
            'ledger_prefix_bytes': len(ledger_bytes), 'ledger_prefix_sha256': hashlib.sha256(ledger_bytes).hexdigest(),
        }
        write_json(promotion_lock_path, promotion_lock, exclusive=True)
        os.chmod(promotion_lock_path, stat.S_IREAD)
        promotion_lock_sha = sha256_path(promotion_lock_path)
        append_ledger(repo, f"EXP005-C immutable promotion sub-lock published | Primary100k PASS and exact treatment endpoint SHA{treatment_sha} bound before any Slumbot launch. Lock {promotion_lock_path} SHA{promotion_lock_sha} pins greedy-direct12x1700 direct BelowNormal full bundle, fresh V4 model/report/12 hand-file hashes, Welch relative CI lower>0, point-only forbidden, and same-checkpoint formal rule. [event_id=v5-exp005c-promotion-sublock-published]")

        treatment_run = repo / 'models/alpha_holdem_v5_from_zero/v5_zero_l6_exp005c_treatment_pergroup5_same31400_20m_r1_20260710'
        promo_status = repo / 'reports/v5_exp005c_promotion20k_status.json'
        promo_plan_json = repo / 'reports/v5_exp005c_promotion20k_plan.json'
        promo_plan_md = repo / 'reports/v5_exp005c_promotion20k_plan.md'
        promo_log = repo / 'reports/v5_exp005c_promotion20k_watch.log'
        command = [sys.executable, str(pipeline), '--run-dir', str(treatment_run), '--checkpoint', str(treatment_checkpoint),
                   '--stage', 'promotion20k', '--tag', promotion_tag, '--output-dir', str(repo / 'models'),
                   '--sessions', '12', '--hands-per-session', '1700', '--min-training-hands', str(treatment['hands']),
                   '--no-require-quality-gate', '--no-health-age-check', '--once', '--launch-path', 'direct',
                   '--policy-mode', 'greedy', '--plan-json', str(promo_plan_json), '--plan-md', str(promo_plan_md),
                   '--status-json', str(promo_status), '--log', str(promo_log)]
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PENDING', 'state': 'PROMOTION20K_RUNNING',
                                 'promotion_lock': str(promotion_lock_path), 'promotion_lock_sha256': promotion_lock_sha})
        result = subprocess.run(command, check=False)
        if result.returncode != 0:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'PROMOTION20K_PIPELINE_FAILED', 'exit_code': result.returncode})
            return 1
        pipeline_status = read_json(promo_status)
        promotion_gate_path = Path(str((((pipeline_status.get('benchmark_result') or {}).get('artifact_audit') or {}).get('artifacts') or {}).get('promotion_json') or ''))
        if not promotion_gate_path.is_absolute(): promotion_gate_path = repo / promotion_gate_path
        promotion_gate = read_json(promotion_gate_path)
        relative_path = repo / 'reports/v5_exp005c_promotion_relative_v4_ci.json'
        candidate_glob = str(repo / 'models' / f'bench_v55_{promotion_tag}_part*_hands.jsonl')
        rel_cmd = [sys.executable, str(relative_tool), '--candidate-hands-glob', candidate_glob,
                   '--v4-hands-glob', str(repo / 'tmp/v4_vs_slumbot_fresh/w*_hands.jsonl'),
                   '--candidate-checkpoint', str(treatment_checkpoint), '--expected-candidate-sha256', treatment_sha,
                   '--v4-model', str(v4_model), '--expected-v4-model-sha256', V4_MODEL_SHA,
                   '--v4-report', str(v4_report), '--expected-v4-report-sha256', sha256_path(v4_report),
                   '--out-json', str(relative_path)]
        if subprocess.run(rel_cmd, check=False).returncode != 0:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'RELATIVE_V4_CI_AUDIT_FAILED'})
            return 1
        relative = read_json(relative_path)
        strong, blockers = combined_strong(pipeline_status=pipeline_status, promotion_gate=promotion_gate,
                                           relative=relative, expected_checkpoint_sha=treatment_sha)
        program_gate_path = repo / 'reports/v5_exp005c_promotion_program_gate.json'
        program_gate = {'checked_at': now_iso(), 'overall': 'PASS', 'promotion_20k_strong': strong,
                        'blockers': blockers, 'promotion_pipeline_status': str(promo_status),
                        'promotion_gate': str(promotion_gate_path), 'relative_v4_ci': str(relative_path),
                        'treatment_checkpoint_sha256': treatment_sha,
                        'next_action': 'ALLOW_FORMAL100K' if strong else 'FREEZE_TIER2_AND_ROUTE_REVIEW'}
        write_json(program_gate_path, program_gate, exclusive=True)
        if not strong:
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'PROMOTION_NON_STRONG_TIER2_FROZEN',
                                     'program_gate': str(program_gate_path), 'blockers': blockers, 'route_review_required': True})
            append_ledger(repo, f"EXP005-C promotion20k non-strong; Tier2 frozen | Full promotion pipeline and fresh-V4 Welch gate completed; blockers {blockers}. No formal launch; route review required. [event_id=v5-exp005c-promotion-nonstrong-tier2-frozen]")
            return 0

        formal_status = repo / 'reports/v5_exp005c_formal100k_status.json'
        formal_cmd = [sys.executable, str(pipeline), '--run-dir', str(treatment_run), '--checkpoint', str(treatment_checkpoint),
                      '--stage', 'formal100k', '--tag', formal_tag, '--output-dir', str(repo / 'models'),
                      '--sessions', '20', '--hands-per-session', '5000', '--min-training-hands', str(treatment['hands']),
                      '--promotion-gate-json', str(promotion_gate_path), '--no-require-quality-gate', '--no-health-age-check',
                      '--once', '--launch-path', 'direct', '--policy-mode', 'greedy',
                      '--plan-json', str(repo / 'reports/v5_exp005c_formal100k_plan.json'),
                      '--plan-md', str(repo / 'reports/v5_exp005c_formal100k_plan.md'),
                      '--status-json', str(formal_status), '--log', str(repo / 'reports/v5_exp005c_formal100k_watch.log')]
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PENDING', 'state': 'FORMAL100K_RUNNING',
                                 'program_gate': str(program_gate_path)})
        formal_result = subprocess.run(formal_cmd, check=False)
        formal_payload = read_json(formal_status)
        if formal_result.returncode != 0 or formal_payload.get('state') != 'PASS':
            write_json(status_path, {'checked_at': now_iso(), 'overall': 'FAIL', 'state': 'FORMAL100K_PIPELINE_FAILED',
                                     'exit_code': formal_result.returncode, 'formal_status': str(formal_status)})
            return 1
        write_json(status_path, {'checked_at': now_iso(), 'overall': 'PASS', 'state': 'FORMAL100K_COMPLETE',
                                 'formal_status': str(formal_status), 'strength_claim': 'ONLY_AS_REPORTED_BY_AUDITED_FORMAL_GATE'})
        append_ledger(repo, "EXP005-C same-checkpoint formal100k completed | Combined promotion strong gate allowed exact treatment endpoint greedy-direct formal100k; full pipeline status PASS. Strength classification is only the audited formal gate result. [event_id=v5-exp005c-formal100k-complete]")
        return 0


if __name__ == '__main__':
    raise SystemExit(main())
