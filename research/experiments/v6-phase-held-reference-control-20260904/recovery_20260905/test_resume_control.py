"""Recovery boundary and real child-observer failure tests; no poker hands."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('phase_recovery_tests_target', HERE / 'resume_control.py')
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def boundary():
    accounting = {'completed_hands': 7237515}
    checkpoint = {'iteration': 1525, 'total_hands': 6284575, 'environment_hand_accounting': accounting}
    manifest = copy.deepcopy(checkpoint)
    metrics = [{'iteration': i} for i in range(1, 1526)]
    metrics[-1].update(hands=6284575, environment_hand_accounting=accounting)
    assignments = [{'applies_to_iteration': i} for i in range(1, 1527)]
    assignments[-1]['total_hands_before_iteration'] = 6284575
    return checkpoint, manifest, metrics, assignments


def test_exact_pending_boundary():
    r.validate_boundary(*boundary())


@pytest.mark.parametrize('mutation', ['counter', 'metric_gap', 'unsaved_metric', 'missing_pending', 'pending_counter'])
def test_wrong_boundary_fails_closed(mutation):
    c, m, rows, assignments = boundary()
    if mutation == 'counter':
        m['total_hands'] -= 1
    elif mutation == 'metric_gap':
        rows.pop(8)
    elif mutation == 'unsaved_metric':
        rows.append({'iteration': 1526})
    elif mutation == 'missing_pending':
        assignments.pop()
    else:
        assignments[-1]['total_hands_before_iteration'] -= 1
    with pytest.raises(ValueError):
        r.validate_boundary(c, m, rows, assignments)


def test_partial_jsonl_refused_without_modifying_source(tmp_path):
    path = tmp_path / 'partial.jsonl'
    data = b'{"iteration":1}\n{"iteration":2}'
    path.write_bytes(data)
    with pytest.raises(ValueError):
        r.exact_rows(path)
    assert path.read_bytes() == data


def test_endpoint_redirect_only_static_second_stage():
    assert r.recovered_stage_directory('static', 2) == r.RUN
    for arm, stage in (('static', 1), ('moving256', 1), ('moving256', 2)):
        assert r.recovered_stage_directory(arm, stage) == r.ORIGINAL_STAGE_DIRECTORY(arm, stage)


def test_command_preserves_algorithm_and_seed(monkeypatch):
    old = json.loads((r.OLD / 'command.json').read_text(encoding='utf-8'))
    monkeypatch.setattr(r.ctl, 'stage_directory', r.recovered_stage_directory)
    new = r.ctl.training_command('static', 2, r.PARENT, 7237515)
    for option in ('--out', '--run-dir', '--opponent-assignment-provenance-file', '--resume'):
        old[old.index(option) + 1] = new[new.index(option) + 1]
    assert old == new
    assert new[new.index('--total-environment-hands') + 1] == '8392280'
    assert '--no-reset-optimizer' in new and '--preserve-resumed-optimizer-lr' in new
    assert '--managed-deal-attempts' in new
    assert '--deal-attempt-namespace' not in new


def test_remainder_accounting_adds_retained_prefix_once(monkeypatch):
    monkeypatch.setattr(r, 'ORIGINAL_ACCOUNTING', lambda: (
        {'new_training_hands': 101, 'new_transition_hands': 88}, {}))
    monkeypatch.setattr(r.ev, 'read_json', lambda p: {'partial_attempt': {'new_physical_hands': 939536, 'new_transition_hands': 812166}})
    totals, runs = r.recovery_accounting()
    assert totals == {'new_training_hands': 939637, 'new_transition_hands': 812254}
    assert len(runs) == 1


def fake_controller():
    result = object.__new__(r.Recovery)
    result.inputs = {}
    result.child = None
    result.tick = lambda **kw: None
    result.phase = 'TEST'
    return result


def test_real_child_observer_failure_drains_and_records_no_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(r.ctl, 'logger_update', lambda *args: None)
    controller = fake_controller()
    def observer(line):
        raise RuntimeError('synthetic observer failure')
    argv = [sys.executable, '-B', '-c', "import time; print('first',flush=True); time.sleep(.05); print('last',flush=True)"]
    with pytest.raises(ValueError, match='Job failed'):
        controller.execute(argv, tmp_path, observer)
    receipt = json.loads((tmp_path / 'termination.json').read_text(encoding='utf-8'))
    assert receipt['exit_code'] == 0
    assert receipt['observer_errors'] and receipt['remaining_observed_child_pids'] == []
    assert 'last' in (tmp_path / 'stdout.log').read_text(encoding='utf-8')
    assert controller.child is None


def test_error_drain_does_not_start_a_second_job(monkeypatch):
    results = iter([None, None, 0])
    child = SimpleNamespace(poll=lambda: next(results))
    controller = SimpleNamespace(child=child, phase='TEST')
    monkeypatch.setattr(r.time, 'sleep', lambda n: None)
    r.drain_current(controller)
    assert controller.child is None
    assert controller.phase == 'ERROR_DRAINING_EXISTING_BOUNDED_JOB_NO_NEXT_JOB'
