"""Do not lose or double-count the interrupted prefix in a completed stage."""
import copy
import importlib.util
from pathlib import Path
import pytest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('recovery_final_analysis_tests', HERE / 'final_analysis.py')
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def data():
    completed = [dict(arm=arm, stage=stage, namespace=str(index), passed=True,
                     unknown_crash_suffix_hands=0, new_physical_hands=100, new_transition_hands=80,
                     new_replay_rows=1000, new_no_decision_hands=18, residual_worker_tail_hands=2,
                     subprocess_wall_seconds=10) for index, (arm, stage) in enumerate(m.ctl.ORDER)]
    partial = dict(arm='static', stage=2, namespace='interrupted', retained_boundary_verified=True,
                   terminal_attempt=False, unknown_crash_suffix_hands=None, new_physical_hands=50,
                   new_transition_hands=40, new_replay_rows=300, new_no_decision_hands=9,
                   retained_worker_tail_hands=1, last_checkpoint_utc='2026-09-05T01:00:05+00:00')
    return completed, partial, {'audited_at': '2026-09-05T01:00:10+00:00'}, {'started_at': '2026-09-05T01:00:00+00:00'}


def test_interrupted_prefix_counted_once_with_unknown_and_cost_bounds():
    counts = m.accounting(*data())
    assert counts['new_training_hands'] == 450
    assert counts['new_transition_hands'] == 360
    assert counts['new_replay_rows_not_new_hands'] == 4300
    assert counts['per_arm_cumulative_physical_hands'] == {
        'static': m.ctl.INITIAL_PHYSICAL + 250, 'moving256': m.ctl.INITIAL_PHYSICAL + 200}
    assert counts['known_local_lineage_union_physical_hands'] == m.ctl.INITIAL_PHYSICAL + 450
    assert counts['unknown_crash_suffix_hands'] is None
    assert counts['all_training_attempt_wall_bounds_seconds'] == [45, 50]
    assert counts['retained_physical_hands_per_training_wall_second_bounds'] == [9, 10]


@pytest.mark.parametrize('mutation', ['namespace', 'unknown_to_zero', 'pretend_terminal', 'missing_attempt', 'physical_mismatch', 'bad_time'])
def test_invalid_interruption_accounting_fails(mutation):
    completed, partial, interruption, process = copy.deepcopy(data())
    if mutation == 'namespace':
        partial['namespace'] = completed[0]['namespace']
    elif mutation == 'unknown_to_zero':
        partial['unknown_crash_suffix_hands'] = 0
    elif mutation == 'pretend_terminal':
        partial['terminal_attempt'] = True
    elif mutation == 'missing_attempt':
        completed.pop()
    elif mutation == 'physical_mismatch':
        partial['new_physical_hands'] += 1
    else:
        process['started_at'] = '2026-09-05T02:00:00+00:00'
    with pytest.raises(ValueError):
        m.accounting(completed, partial, interruption, process)


def test_live_owner_blocks_final_analysis(monkeypatch):
    monkeypatch.setattr(m.ctl, 'owner_live', lambda owner: True)
    assert m.readiness() == {'ready': False, 'reason': 'exact controller owner still live'}
