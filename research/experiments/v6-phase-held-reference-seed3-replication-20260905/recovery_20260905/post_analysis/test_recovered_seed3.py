"""Synthetic accounting/guard tests: no checkpoint loads or poker model calls."""
import copy
import json
import os

import psutil
import pytest

import analyze_recovered_seed3 as report


def run(arm, stage, index):
    return {'arm': arm, 'stage': stage, 'namespace': f'fresh-{index}', 'passed': True,
            'new_physical_hands': 100, 'new_transition_hands': 80, 'new_replay_rows': 900,
            'new_no_decision_hands': 15, 'residual_worker_tail_hands': 5,
            'unknown_crash_suffix_hands': 0, 'subprocess_wall_seconds': 10.0}


def fixture_data(stages=2):
    order = report.ctl.ORDER if stages == 2 else report.ctl.ORDER[:2]
    completed = [run(arm, stage, i) for i, (arm, stage) in enumerate(order)]
    partial = run('static', 1, 'old')
    partial.update(original_exit_code=1, unknown_additional_worker_tail_hands=None)
    audit = {'observed_completed_but_uncheckpointed_physical_hands': 4292,
             'observed_completed_but_uncheckpointed_transition_hands': 4123}
    return completed, partial, audit


@pytest.mark.parametrize('stages', [1, 2])
def test_retained_executed_replay_and_shared_parent_are_distinct(stages):
    runs, partial, audit = fixture_data(stages)
    result = report.accounting(runs, partial, audit, 25, stages)
    retained = 100 * (1 + 2 * stages)
    assert result['retained_training_hands'] == retained
    assert result['new_training_hands'] == retained + 4292
    assert result['new_transition_hands'] == 80 * (1 + 2 * stages) + 4123
    assert result['new_replay_rows_not_new_hands'] == 900 * (1 + 2 * stages)
    assert result['known_retained_local_lineage_union_hands'] == report.ctl.INITIAL_PHYSICAL + retained
    assert result['per_arm_cumulative_physical_hands'] == {
        'static': report.ctl.INITIAL_PHYSICAL + 100 * (stages + 1),
        'moving256': report.ctl.INITIAL_PHYSICAL + 100 * stages}
    assert result['unknown_additional_worker_tail_hands'] is None
    assert result['all_training_attempt_wall_seconds'] == 25 + 20 * stages
    assert result['retained_physical_hands_per_training_wall_second'] == retained / (25 + 20 * stages)
    assert result['evaluation_hands'] == 65536 * stages
    assert result['offline_samples'] == 40000 * stages
    assert result['slumbot_hands'] == 0
    assert result['training_seed_lineages'] == 1


@pytest.mark.parametrize('bad_order', ['missing', 'reversed', 'extra'])
def test_completed_stage_coverage_is_exact(bad_order):
    runs, partial, audit = fixture_data()
    if bad_order == 'missing':
        runs.pop()
    elif bad_order == 'reversed':
        runs.reverse()
    else:
        runs.append(copy.deepcopy(runs[-1]))
    with pytest.raises(ValueError, match='coverage'):
        report.accounting(runs, partial, audit, 25, 2)


def test_failed_attempt_namespace_cannot_be_reused():
    runs, partial, audit = fixture_data()
    runs[0]['namespace'] = partial['namespace']
    with pytest.raises(ValueError, match='namespace'):
        report.accounting(runs, partial, audit, 25, 2)


def test_opposing_per_attempt_accounting_errors_cannot_cancel():
    runs, partial, audit = fixture_data()
    runs[0]['new_transition_hands'] += 1
    runs[1]['new_transition_hands'] -= 1
    with pytest.raises(ValueError, match='unbalanced retained attempt'):
        report.accounting(runs, partial, audit, 25, 2)


@pytest.mark.parametrize('change', [
    {'new_replay_rows': -1}, {'new_physical_hands': 100.0},
    {'subprocess_wall_seconds': float('nan')}, {'subprocess_wall_seconds': -1},
    {'passed': False}, {'unknown_crash_suffix_hands': None}])
def test_unqualified_or_invalid_completed_attempt_rejected(change):
    runs, partial, audit = fixture_data()
    runs[0].update(change)
    with pytest.raises(ValueError):
        report.accounting(runs, partial, audit, 25, 2)


@pytest.mark.parametrize('wall', [0, -1, float('inf'), float('nan')])
def test_original_attempt_wall_must_be_observed_positive_finite(wall):
    runs, partial, audit = fixture_data()
    with pytest.raises(ValueError, match='wall time'):
        report.accounting(runs, partial, audit, wall, 2)


def test_unknown_original_tail_cannot_be_silently_zeroed():
    runs, partial, audit = fixture_data()
    partial['unknown_additional_worker_tail_hands'] = 0
    with pytest.raises(ValueError, match='interrupted prefix'):
        report.accounting(runs, partial, audit, 25, 2)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def owner(live=False):
    proc = psutil.Process(os.getpid())
    return {'pid': proc.pid, 'create_time': proc.create_time() if live else proc.create_time() - 1000}


def terminal(exit_code=0):
    return {'exit_code': exit_code, 'observer_errors': [], 'remaining_observed_child_pids': [],
            'observed_children': {}}


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    base = tmp_path / 'base'
    recovery = base / 'recovery'
    monkeypatch.setattr(report, 'BASE', base)
    monkeypatch.setattr(report, 'RECOVERY', recovery)
    monkeypatch.setattr(report, 'OLD', base / 'static_stage1')
    for path in (base, recovery):
        write_json(path / 'ownership.json', owner())
    return base, recovery


@pytest.mark.parametrize('live_root', ['base', 'recovery'])
def test_actual_live_owner_blocks_before_missing_outcomes(isolated, live_root):
    base, recovery = isolated
    write_json((base if live_root == 'base' else recovery) / 'ownership.json', owner(live=True))
    assert not report.readiness()['ready']
    with pytest.raises(ValueError, match='controller still live'):
        report.build_report()


def test_missing_terminal_is_not_success(isolated):
    assert not report.readiness()['ready']
    with pytest.raises(ValueError, match='terminal recovery result absent'):
        report.build_report()


@pytest.mark.parametrize('phase,ready', [(report.FULL, True), (report.COLLAPSE, True),
                                       ('SAFE_BOUNDARY_REQUIRES_RESEARCHER_RESUME_REVIEW', False)])
def test_only_explicit_normal_or_collapse_phase_is_ready(isolated, phase, ready):
    _, recovery = isolated
    write_json(recovery / 'pipeline_result.json', {'phase': phase})
    assert report.readiness()['ready'] is ready


@pytest.mark.parametrize('mode', ['live_job', 'live_descendant', 'missing_receipt', 'observer_error'])
def test_dead_controller_does_not_hide_surviving_or_unaccounted_child(isolated, mode):
    _, recovery = isolated
    job = recovery / 'synthetic_job'
    write_json(job / 'process.json', owner(live=mode == 'live_job'))
    receipt = terminal()
    if mode == 'live_descendant':
        current = owner(live=True)
        receipt['observed_children'] = {str(current['pid']): current['create_time']}
    if mode == 'observer_error':
        receipt['observer_errors'] = ['synthetic observer error']
    if mode != 'missing_receipt':
        write_json(job / 'termination.json', receipt)
    assert not report.readiness()['ready']
    # No pipeline or outcomes exist: failure must occur at process evidence, not a result read.
    with pytest.raises(ValueError, match='tracked'):
        report.build_report()


def test_exit1_only_allowed_for_preserved_original_failure(isolated):
    base, recovery = isolated
    old, normal = base / 'static_stage1', recovery / 'static_stage1_remainder'
    for job in (old, normal):
        write_json(job / 'process.json', owner())
        write_json(job / 'termination.json', terminal(1))
        write_json(job / 'command.json', ['synthetic-not-executed'])
    assert len(report.verify_job(old, original_failed=True)) == 3
    with pytest.raises(ValueError, match='only original'):
        report.verify_job(normal, original_failed=True)
    with pytest.raises(ValueError, match='termination receipt'):
        report.verify_job(normal)
    write_json(normal / 'termination.json', terminal(0))
    assert len(report.verify_job(normal)) == 3


def test_original_failure_receipt_cannot_hide_live_descendant(isolated):
    base, _ = isolated
    job = base / 'static_stage1'
    write_json(job / 'process.json', owner())
    current = owner(live=True)
    receipt = terminal(1)
    receipt['observed_children'] = {str(current['pid']): current['create_time']}
    write_json(job / 'termination.json', receipt)
    with pytest.raises(ValueError, match='descendant still live'):
        report.verify_job(job, original_failed=True)


def test_hash_collision_is_not_silently_overwritten():
    assert report.merge_hashes({'a': 'sha1'}, {'a': 'sha1', 'b': 'sha2'}) == {'a': 'sha1', 'b': 'sha2'}
    with pytest.raises(ValueError, match='conflicting frozen input'):
        report.merge_hashes({'a': 'sha1'}, {'a': 'different'})


def test_real_module_bindings_are_seed3_not_seed1():
    assert report.BASE == report.ctl.BASE == report.ev.BASE
    assert report.BASE.name == 'v6-phase-held-reference-seed3-replication-20260905'
    assert report.cross.SEED1_BASE.name == 'v6-phase-held-reference-control-20260904'
    assert report.ctl.INITIAL_PHYSICAL == 4194908
    assert report.ctl.TRAINING_SEED == 20263003
