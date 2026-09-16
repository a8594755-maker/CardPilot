"""Synthetic two-interruption accounting and actual OS identity guards; zero hands."""
import json
import os

import psutil
import pytest
import analyze_twice_recovered as report


def row(arm, stage, namespace, physical=100):
    return {'arm': arm, 'stage': stage, 'namespace': namespace, 'passed': True,
        'new_physical_hands': physical, 'new_transition_hands': physical - 20,
        'new_no_decision_hands': 15, 'residual_worker_tail_hands': 5, 'new_replay_rows': 900,
        'unknown_crash_suffix_hands': 0, 'subprocess_wall_seconds': 10.0}


def fixture(stages=2):
    completed = [row(a, s, f'new-{i}') for i, (a, s) in enumerate(report.ctl.ORDER[:stages * 2])]
    partials = [row('static', 1, 'failed-static', 10000), row('moving256', 1, 'failed-moving', 20000)]
    for item in partials:
        item.update(original_exit_code=1, unknown_additional_worker_tail_hands=None,
                    known_unretained_physical_hands=0, known_unretained_transition_hands=0,
                    recovered_unpublished_hands_already_in_retained=0)
    partials[0].update(known_unretained_physical_hands=4292, known_unretained_transition_hands=4123)
    partials[1]['recovered_unpublished_hands_already_in_retained'] = 5256
    return completed, partials


@pytest.mark.parametrize('stages', [1, 2])
def test_both_interruptions_shared_parent_replay_and_recovered_update(stages):
    completed, partials = fixture(stages)
    result = report.accounting(completed, partials, stages)
    retained = 30000 + 200 * stages
    assert result['retained_training_hands'] == retained
    assert result['new_training_hands'] == retained + 4292  # Do NOT also add recovered5256.
    assert result['observed_uncheckpointed_transition_hands'] == 4123
    assert result['recovered_unpublished_hands_already_in_retained'] == 5256
    assert result['known_retained_local_lineage_union_hands'] == report.ctl.INITIAL_PHYSICAL + retained
    assert result['per_arm_cumulative_physical_hands'] == {
        'static': report.ctl.INITIAL_PHYSICAL + 10000 + 100 * stages,
        'moving256': report.ctl.INITIAL_PHYSICAL + 20000 + 100 * stages}
    assert result['unknown_additional_worker_tail_hands'] is None
    assert len(result['unique_attempt_namespaces']) == 2 + 2 * stages
    assert result['unique_attempt_namespaces'][:3] == ['failed-static', 'new-0', 'failed-moving']
    assert result['all_training_attempt_wall_seconds'] == 20 + 20 * stages
    assert result['retained_physical_hands_per_training_wall_second'] == retained / (20 + 20 * stages)
    assert result['new_replay_rows_not_new_hands'] == 900 * (2 + 2 * stages)
    assert result['evaluation_hands'] == stages * 65536
    assert result['offline_samples'] == stages * 40000
    assert result['slumbot_hands'] == 0 and result['training_seed_lineages'] == 1


@pytest.mark.parametrize('which', ['completed_gap', 'completed_reordered', 'partial_missing', 'partial_reordered'])
def test_missing_or_reordered_attempt_is_not_completed(which):
    completed, partials = fixture()
    if which == 'completed_gap':
        completed.pop()
    elif which == 'completed_reordered':
        completed.reverse()
    elif which == 'partial_missing':
        partials.pop()
    else:
        partials.reverse()
    with pytest.raises(ValueError, match='coverage'):
        report.accounting(completed, partials, 2)


@pytest.mark.parametrize('bad', [
    {'namespace': 'new-0'}, {'unknown_additional_worker_tail_hands': 0},
    {'subprocess_wall_seconds': float('nan')}, {'subprocess_wall_seconds': -1},
    {'new_physical_hands': 1.0}, {'new_replay_rows': -1},
    {'known_unretained_transition_hands': 9999}, {'recovered_unpublished_hands_already_in_retained': 999999}])
def test_invalid_interruption_fields_rejected(bad):
    completed, partials = fixture()
    partials[0].update(bad)
    with pytest.raises(ValueError):
        report.accounting(completed, partials, 2)


def test_per_attempt_errors_cannot_cancel_in_the_total():
    completed, partials = fixture()
    completed[0]['new_transition_hands'] += 1
    partials[0]['new_transition_hands'] -= 1
    with pytest.raises(ValueError, match='per-attempt'):
        report.accounting(completed, partials, 2)


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def identity(live=False):
    process = psutil.Process(os.getpid())
    return {'pid': process.pid, 'create_time': process.create_time() if live else process.create_time() - 1000}


def termination(exit_code=0):
    return {'exit_code': exit_code, 'observer_errors': [], 'remaining_observed_child_pids': [], 'observed_children': {}}


@pytest.fixture
def isolated(monkeypatch, tmp_path):
    roots = tuple(tmp_path / name for name in ('original', 'first', 'second'))
    monkeypatch.setattr(report, 'ROOTS', roots)
    monkeypatch.setattr(report, 'SECOND', roots[-1])
    failed = {roots[0] / 'failed_static', roots[0] / 'failed_moving'}
    monkeypatch.setattr(report, 'FAILED', failed)
    for root in roots:
        write_json(root / 'ownership.json', identity())
    return roots


@pytest.mark.parametrize('index', [0, 1, 2])
def test_any_actual_live_controller_blocks_before_any_outcomes(isolated, index):
    write_json(isolated[index] / 'ownership.json', identity(live=True))
    with pytest.raises(ValueError, match='controller still live'):
        report.build_report()


@pytest.mark.parametrize('mode', ['live_job', 'live_descendant', 'missing_receipt', 'observer_error'])
def test_dead_controllers_do_not_hide_incomplete_child(isolated, mode):
    job = isolated[-1] / 'synthetic_job'
    write_json(job / 'process.json', identity(live=mode == 'live_job'))
    receipt = termination()
    if mode == 'live_descendant':
        current = identity(live=True)
        receipt['observed_children'] = {str(current['pid']): current['create_time']}
    if mode == 'observer_error':
        receipt['observer_errors'] = ['synthetic']
    if mode != 'missing_receipt':
        write_json(job / 'termination.json', receipt)
    with pytest.raises(ValueError, match='tracked'):
        report.build_report()


def test_missing_terminal_result_does_not_imply_success(isolated):
    with pytest.raises(ValueError, match='result absent'):
        report.build_report()


@pytest.mark.parametrize('phase,ready', [(report.FULL, True), (report.COLLAPSE, True), ('ERROR_PRESERVED_RESEARCH_REVIEW', False)])
def test_only_preregistered_terminal_paths_allowed(isolated, phase, ready):
    write_json(isolated[-1] / 'pipeline_result.json', {'phase': phase})
    assert report.readiness()['ready'] is ready


def test_only_two_exact_failed_jobs_may_exit1(isolated):
    failed = sorted(report.FAILED)
    normal = isolated[-1] / 'completed'
    for job in [*failed, normal]:
        write_json(job / 'process.json', identity())
        write_json(job / 'termination.json', termination(1))
        write_json(job / 'command.json', ['synthetic-not-executed'])
    for job in failed:
        assert len(report.verify_job(job)) == 3
    with pytest.raises(ValueError, match='termination'):
        report.verify_job(normal)
    write_json(normal / 'termination.json', termination())
    assert len(report.verify_job(normal)) == 3


def test_seed_and_shared_parent_bindings_are_exact():
    assert report.BASE == report.ctl.BASE == report.ev.BASE
    assert report.BASE.name == 'v6-phase-held-reference-seed3-replication-20260905'
    assert report.ctl.INITIAL_PHYSICAL == 4194908 and report.ctl.TRAINING_SEED == 20263003
    assert report.cross.SEED1_BASE != report.BASE
