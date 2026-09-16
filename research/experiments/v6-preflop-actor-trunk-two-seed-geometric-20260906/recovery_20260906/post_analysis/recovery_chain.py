"""Recovery-aware terminal admission and bookkeeping; never launches or logs runs."""
from datetime import datetime
import importlib.util
import math
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECOVERY = HERE.parent
BASE = RECOVERY.parent
SOURCE = BASE / 'post_analysis/review.py'
spec = importlib.util.spec_from_file_location('qualified_actor_terminal_math', SOURCE)
normal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(normal)
require, read, sha, live = normal.require, normal.read, normal.sha, normal.live
PARTIAL_SHA = '9bc206c103b925ce7e77b62eadd0cc92575e1f35d6d7bfe59cee2fa9c274478b'
DELTA_KEYS = ('new_physical_hands', 'new_transition_hands', 'new_no_decision_hands',
              'residual_worker_tail_hands', 'new_replay_rows')
PHASES = ('FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW', 'STAGE1_BROAD_COLLAPSE_REVIEW',
          'STAGE2_BROAD_COLLAPSE_REVIEW')


def endpoint(base, seed, arm, stage):
    require(seed in (1, 3) and arm in ('detached', 'connected') and stage in (1, 2), 'unknown cell')
    if (seed, arm, stage) == (1, 'connected', 1):
        return base / 'recovery_20260906/seed1_connected_stage1_remainder'
    return base / f'seed{seed}_{arm}_stage{stage}'


def merge_hashes(*mappings):
    result = {}
    for mapping in mappings:
        for path, digest in mapping.items():
            require(path not in result or result[path] == digest, f'conflicting frozen SHA:{path}')
            result[path] = digest
    return result


def combined_deltas(partial, remainder):
    for row in (partial, remainder):
        require(all(type(row[k]) is int and row[k] >= 0 for k in DELTA_KEYS), 'invalid retained count')
        require(row['new_physical_hands'] == row['new_transition_hands'] +
                row['new_no_decision_hands'] + row['residual_worker_tail_hands'], 'unbalanced retained count')
    return {key: partial[key] + remainder[key] for key in DELTA_KEYS}


def combined_adam_steps(partial, remainder):
    require(set(partial) == set(remainder) == {str(i) for i in range(86)}, 'missing Adam chain coverage')
    require(all(type(row[k]) is int and row[k] > 0 for row in (partial, remainder) for k in row),
            'invalid Adam update count')
    return {key: partial[key] + remainder[key] for key in partial}


def interrupted_wall_bounds(process, status, audit):
    require(status['active_child_pid'] == process['pid'], 'last status did not observe interrupted child live')
    require(audit['original_controller_last_status_at'] == status['updated_at'], 'wrong interruption observation')
    start = float(process['create_time'])
    last = datetime.fromisoformat(status['updated_at']).timestamp()
    observed_dead = datetime.fromisoformat(audit['created_at']).timestamp()
    require(all(math.isfinite(t) for t in (start, last, observed_dead)) and start <= last <= observed_dead,
            'invalid interruption timing')
    return [last - start, observed_dead - start]


def terminal_guard(base=BASE):
    """Reject live owners/jobs before reading endpoint outcomes. One audited exception only."""
    recovery = base / 'recovery_20260906'
    old = base / 'seed1_connected_stage1'
    # Do not read controller_result, stage statistics, or checkpoint outcomes until
    # BOTH exact owner identities are proven absent.
    for root in (base, recovery):
        owner = read(root / 'ownership.json')
        require(not live(owner['pid'], owner['create_time']), 'controller still live; no outcome review')
    require(not (base / 'controller_error.json').exists() and not (recovery / 'controller_error.json').exists(),
            'new failure requires separate boundary review')
    audit = read(recovery / 'interruption_audit.json')
    require(audit['passed'] and audit['checkpoint_sha256'] == PARTIAL_SHA and
            audit['missing_normal_termination_evidence'] is True and audit['exit_code'] is None and
            audit['cause'] is None and audit['unknown_additional_worker_tail_hands'] is None,
            'unqualified missing-receipt exception')
    require(audit['other_python_processes_at_audit'] == [] and audit['original_process_identities_absent'] is True,
            'original missing descendants were not audited')
    process_files = [*base.glob('*/process.json'), *recovery.glob('*/process.json')]
    paths, hashes, child_count, train_wall, all_wall = set(), {}, 0, 0.0, 0.0
    interrupted_seen = False
    for path in process_files:
        run, process = path.parent, read(path)
        require(not live(process['pid'], process['create_time']), 'tracked job still live; no outcome review')
        paths.add(run)
        if run == old:
            interrupted_seen = True
            require(not (run / 'termination.json').exists(), 'new interrupted termination receipt needs review')
            for name in ('process.json', 'command.json', 'latest.pt'):
                file = run / name
                require(sha(file) == audit['frozen_interrupted_inputs'][str(file)], 'interrupted evidence changed')
                hashes[str(file)] = sha(file)
            continue
        terminal = read(run / 'termination.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors'] and
                not terminal['remaining_observed_child_pids'], 'job not cleanly terminal')
        require(math.isfinite(terminal['wall_seconds']) and terminal['wall_seconds'] > 0, 'invalid job wall time')
        for pid, created in terminal['observed_children'].items():
            require(not live(pid, created), 'recorded worker still live')
            child_count += 1
        all_wall += terminal['wall_seconds']
        if (run / 'verification.json').exists():
            require(len(terminal['observed_children']) >= 12, 'missing worker receipts')
            train_wall += terminal['wall_seconds']
        for name in ('termination.json', 'process.json', 'command.json'):
            hashes[str(run / name)] = sha(run / name)
    require(interrupted_seen, 'interrupted process evidence missing')
    result = read(recovery / 'controller_result.json')
    require(result['phase'] in PHASES and result['original_controller_result_not_fabricated'] is True and
            result['interrupted_attempt_audit'] == str(recovery / 'interruption_audit.json'), 'unexpected recovery boundary')
    stage_count = 1 if result['phase'] == 'STAGE1_BROAD_COLLAPSE_REVIEW' else 2
    cells = [(s, a, stage) for stage in range(1, stage_count + 1) for s, a in normal.ORDERS[stage]]
    require([(r['seed'], r['arm'], r['stage']) for r in result['training']] == cells, 'wrong cell order/coverage')
    expected = {old, *(endpoint(base, *cell) for cell in cells)}
    expected.update(base / f'job_eval_seed{s}_{a}_stage{stage}' for s, a, stage in cells)
    require(paths == expected, 'unexpected/missing job receipts')
    for root in (base, recovery):
        for name in ('ownership.json', 'input_contract.json', 'status.json'):
            hashes[str(root / name)] = sha(root / name)
    hashes[str(recovery / 'controller_result.json')] = sha(recovery / 'controller_result.json')
    hashes[str(recovery / 'interruption_audit.json')] = sha(recovery / 'interruption_audit.json')
    bounds = interrupted_wall_bounds(read(old / 'process.json'), read(base / 'status.json'), audit)
    return {'result': result, 'stage_count': stage_count, 'audit': audit, 'hashes': hashes,
            'observed_completed_job_children_checked': child_count,
            'completed_training_subprocess_wall_seconds': train_wall,
            'completed_all_job_wall_seconds': all_wall,
            'interrupted_training_wall_seconds_bounds': bounds,
            'missing_terminal_receipt_exception': str(old), 'unknown_additional_worker_tail_hands': None}
