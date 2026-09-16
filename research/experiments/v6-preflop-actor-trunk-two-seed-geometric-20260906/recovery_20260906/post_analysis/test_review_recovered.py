import ast
import inspect
import json
from pathlib import Path

import pytest

import recovery_chain as chain
import review_recovered as review
import curve_recovered as curve


@pytest.mark.parametrize('name', ('severe', 'compare_arms', 'counter_deltas', 'adam_steps', 'gradient_route'))
def test_qualified_core_algorithms_are_ast_identical(name):
    actual = ast.parse(inspect.getsource(getattr(review, name)))
    original = ast.parse(inspect.getsource(getattr(chain.normal, name)))
    assert ast.dump(actual, include_attributes=False) == ast.dump(original, include_attributes=False)


def test_stage_review_changes_only_endpoint_resolution():
    source = inspect.getsource(chain.normal.review_stage).replace(
        "sha(base / f'seed{seed}_{arm}_stage{stage}/latest.pt')",
        "sha(endpoint(base, seed, arm, stage) / 'latest.pt')")
    assert ast.dump(ast.parse(source), include_attributes=False) == ast.dump(
        ast.parse(inspect.getsource(review.review_stage)), include_attributes=False)


def test_curve_math_is_the_qualified_function_not_a_new_estimator():
    assert curve.summarize is curve.qualified_curve.summarize


def row(i):
    return {'iteration': i, 'entropy': .4, 'approx_kl': .01, 'reference_policy_kl': .02}


def log(i):
    return f'[{i:5d}] ep=1/2 klstop=1'


def deltas(n):
    return {'new_physical_hands': n, 'new_transition_hands': n - 2, 'new_no_decision_hands': 2,
            'residual_worker_tail_hands': 0, 'new_replay_rows': n * 3}


def partial():
    return {'parent_iteration': 10, 'final_iteration': 12, 'deltas': deltas(100),
            'optimizer_step_deltas': {str(i): 2 for i in range(86)}, 'log_text': log(11) + '\n' + log(12)}


def test_interrupted_and_remaining_health_are_recomputed_as_one_logical_stage():
    steps = {str(i): 3 for i in range(86)}
    health, merged_steps, merged_deltas = review.logical_health(1, 'connected', 1, partial(),
        [row(i) for i in range(1, 15)], log(13) + '\n' + log(14), 12, 14, steps, deltas(200))
    assert health['completed_training_iterations'] == health['kl_early_stop_iterations'] == 4
    assert set(merged_steps.values()) == {5}
    assert merged_deltas['new_physical_hands'] == 300
    assert merged_deltas['new_replay_rows'] == 900


def test_wrong_chain_boundary_is_rejected():
    with pytest.raises(ValueError, match='not attached'):
        review.logical_health(1, 'connected', 1, partial(), [], '', 11, 14, {}, {})


def test_stage2_is_not_given_the_partial_prefix_a_second_time():
    steps, d = {str(i): 3 for i in range(86)}, deltas(200)
    health, merged_steps, merged_deltas = review.logical_health(1, 'connected', 2, partial(),
        [row(i) for i in range(1, 15)], log(13) + '\n' + log(14), 12, 14, steps, d)
    assert health['completed_training_iterations'] == 2
    assert merged_steps is steps and merged_deltas is d


@pytest.mark.parametrize('module', (review, curve))
def test_live_guard_blocks_entry_before_outcome_read(monkeypatch, tmp_path, module):
    def stop(*args):
        raise ValueError('controller still live')
    monkeypatch.setattr(module if module is review else chain, 'terminal_guard', stop)
    monkeypatch.setattr(module, 'read', lambda *_: pytest.fail('outcome read while controller live'))
    with pytest.raises(ValueError, match='controller still live'):
        module.main(tmp_path)


def test_existing_terminal_review_is_never_overwritten(tmp_path):
    path = tmp_path / 'recovery_20260906/post_terminal_review.json'
    path.parent.mkdir()
    path.write_text('original', encoding='utf-8')
    with pytest.raises(ValueError, match='preserve prior review'):
        review.main(tmp_path)
    assert path.read_text() == 'original'


def test_stage1_stop_never_runs_two_stage_curve(monkeypatch, tmp_path):
    monkeypatch.setattr(chain, 'terminal_guard', lambda _: {'stage_count': 1})
    monkeypatch.setattr(curve, 'read', lambda *_: pytest.fail('curve must reject before outcome read'))
    with pytest.raises(ValueError, match='two completed stages'):
        curve.main(tmp_path)


def write_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj), encoding='utf-8')


def terminal_fixture(base, monkeypatch):
    recovery, old = base / 'recovery_20260906', base / 'seed1_connected_stage1'
    for idx, root in enumerate((base, recovery), 1):
        write_json(root / 'ownership.json', {'pid': idx, 'create_time': 1.})
        write_json(root / 'input_contract.json', {})
        write_json(root / 'status.json', {'active_child_pid': 10, 'updated_at': '1970-01-01T00:02:10+00:00'})
    write_json(old / 'process.json', {'pid': 10, 'create_time': 100.})
    write_json(old / 'command.json', [])
    (old / 'latest.pt').write_bytes(b'synthetic checkpoint bytes')
    digest = chain.sha(old / 'latest.pt')
    monkeypatch.setattr(chain, 'PARTIAL_SHA', digest)
    audit = {'passed': True, 'checkpoint_sha256': digest, 'missing_normal_termination_evidence': True,
             'exit_code': None, 'cause': None, 'unknown_additional_worker_tail_hands': None,
             'other_python_processes_at_audit': [], 'original_process_identities_absent': True,
             'created_at': '1970-01-01T00:03:00+00:00',
             'original_controller_last_status_at': '1970-01-01T00:02:10+00:00',
             'frozen_interrupted_inputs': {str(old / n): chain.sha(old / n) for n in ('process.json', 'command.json', 'latest.pt')}}
    write_json(recovery / 'interruption_audit.json', audit)
    cells = [(s, a, 1) for s, a in chain.normal.ORDERS[1]]
    for idx, cell in enumerate(cells, 20):
        run = chain.endpoint(base, *cell)
        for name, value in (('process.json', {'pid': idx, 'create_time': 1.}), ('command.json', []), ('verification.json', {}),
                            ('termination.json', {'exit_code': 0, 'observer_errors': [], 'remaining_observed_child_pids': [],
                            'wall_seconds': 100., 'observed_children': {str(idx * 100 + i): 1. for i in range(12)}})):
            write_json(run / name, value)
        s, a, stage = cell
        job = base / f'job_eval_seed{s}_{a}_stage{stage}'
        for name, value in (('process.json', {'pid': idx + 100, 'create_time': 1.}), ('command.json', []),
                            ('termination.json', {'exit_code': 0, 'observer_errors': [], 'remaining_observed_child_pids': [],
                             'wall_seconds': 50., 'observed_children': {}})):
            write_json(job / name, value)
    write_json(recovery / 'controller_result.json', {'phase': 'STAGE1_BROAD_COLLAPSE_REVIEW',
        'original_controller_result_not_fabricated': True, 'interrupted_attempt_audit': str(recovery / 'interruption_audit.json'),
        'training': [{'seed': s, 'arm': a, 'stage': stage} for s, a, stage in cells]})
    monkeypatch.setattr(chain, 'live', lambda *_: False)
    return old, recovery


def test_exact_missing_receipt_exception_admits_only_complete_terminal_job_inventory(tmp_path, monkeypatch):
    old, _ = terminal_fixture(tmp_path, monkeypatch)
    result = chain.terminal_guard(tmp_path)
    assert result['stage_count'] == 1 and result['missing_terminal_receipt_exception'] == str(old)
    assert result['completed_training_subprocess_wall_seconds'] == 400.
    assert result['completed_all_job_wall_seconds'] == 600.
    assert result['interrupted_training_wall_seconds_bounds'] == [30., 80.]
    assert result['unknown_additional_worker_tail_hands'] is None


@pytest.mark.parametrize('problem', ('missing_receipt', 'live_worker', 'changed_partial', 'extra_job', 'fake_clean_partial'))
def test_terminal_guard_rejects_other_evidence_failures(tmp_path, monkeypatch, problem):
    old, recovery = terminal_fixture(tmp_path, monkeypatch)
    if problem == 'missing_receipt':
        # Removing a synthetic test fixture is not a workspace evidence mutation.
        (chain.endpoint(tmp_path, 3, 'connected', 1) / 'termination.json').unlink()
    elif problem == 'live_worker':
        monkeypatch.setattr(chain, 'live', lambda pid, _: int(pid) == 2000)
    elif problem == 'changed_partial':
        (old / 'latest.pt').write_bytes(b'changed synthetic checkpoint')
    elif problem == 'extra_job':
        write_json(recovery / 'extra/process.json', {'pid': 999, 'create_time': 1.})
        write_json(recovery / 'extra/command.json', [])
        write_json(recovery / 'extra/termination.json', {'exit_code': 0, 'observer_errors': [],
                   'remaining_observed_child_pids': [], 'wall_seconds': 1., 'observed_children': {}})
    else:
        write_json(old / 'termination.json', {'exit_code': 0})
    with pytest.raises((ValueError, FileNotFoundError)):
        chain.terminal_guard(tmp_path)
