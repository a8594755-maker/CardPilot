import json
from types import SimpleNamespace

import pytest

import resume_control as r
from prepare_recovery import consumed_metric_prefix


def data(iterations=(1, 2, 3)):
    return b''.join((json.dumps({'iteration': i, 'hands': i * 100}) + '\n').encode() for i in iterations)


def test_derived_prefix_is_byte_exact_and_preserves_source():
    original = data()
    prefix, excluded = consumed_metric_prefix(original, 2)
    assert prefix == data((1, 2))
    assert excluded == [{'iteration': 3, 'hands': 300}]
    assert original == data()


@pytest.mark.parametrize('raw,iteration', [(data()[:-1], 2), (data((1, 3)), 1), (data((1, 2, 2)), 1), (data(), 3)])
def test_partial_duplicate_gap_or_missing_suffix_rejected(raw, iteration):
    with pytest.raises(ValueError):
        consumed_metric_prefix(raw, iteration)


def test_only_interrupted_stage_is_redirected():
    for arm, stage in r.ctl.ORDER:
        expected = r.RUN if (arm, stage) == ('static', 1) else r.ORIGINAL_STAGE_DIRECTORY(arm, stage)
        assert r.recovered_stage_directory(arm, stage) == expected


@pytest.mark.parametrize('arm,stage', r.ctl.ORDER)
def test_wrapper_changes_no_algorithm_seed_target_or_resume_flags(monkeypatch, arm, stage):
    monkeypatch.setattr(r.ctl, 'stage_directory', r.recovered_stage_directory)
    parent = r.VIEW / 'latest.pt' if (arm, stage) == ('static', 1) else r.ORIGINAL_PARENT
    old = r.ORIGINAL_COMMAND(arm, stage, parent, 5314037)
    new = r.recovered_command(arm, stage, parent, 5314037)
    assert old[:2] == new[:2] and old[3:] == new[3:]
    assert new[2] == str(r.WRAPPER)
    assert new[new.index('--seed') + 1] == '20263003'
    assert new[new.index('--worker-seed-base') + 1] == '2026300300'
    assert new[new.index('--total-environment-hands') + 1] == str(r.ctl.TARGETS[stage])
    assert '--no-reset-optimizer' in new and '--preserve-resumed-optimizer-lr' in new
    assert '--deal-attempt-namespace' not in new


def test_original_parent_restored_even_if_remainder_fails(monkeypatch):
    def failure(self, arm, stage):
        assert r.ctl.PARENT == r.VIEW / 'latest.pt'
        raise RuntimeError('synthetic retained-stage failure')
    monkeypatch.setattr(r.ctl.Controller, 'train', failure)
    controller = object.__new__(r.Recovery)
    with pytest.raises(RuntimeError):
        controller.train('static', 1)
    assert r.ctl.PARENT == r.ORIGINAL_PARENT


def test_executed_and_retained_counts_stay_distinct(monkeypatch):
    monkeypatch.setattr(r, 'ORIGINAL_ACCOUNTING', lambda: ({'new_training_hands': 100, 'new_transition_hands': 80}, {}))
    audit = {'new_retained_physical_hands': 1119129, 'new_retained_transition_hands': 978072,
             'observed_completed_but_uncheckpointed_physical_hands': 4292,
             'observed_completed_but_uncheckpointed_transition_hands': 4123,
             'retained_physical_hands': 5314037, 'iteration': 1117}
    monkeypatch.setattr(r.ev, 'read_json', lambda _: audit)
    totals, runs = r.recovery_accounting()
    assert totals['retained_training_hands'] == 1119229
    assert totals['new_training_hands'] == 1123521
    assert totals['new_transition_hands'] - totals['retained_transition_hands'] == 4123
    assert all(isinstance(value, int) for value in totals.values())
    assert len(runs) == 1


def test_first_job_failure_never_starts_next_training_or_evaluation(monkeypatch, tmp_path):
    controller = object.__new__(r.Recovery)
    controller.child = None
    controller.tick = lambda **kwargs: None
    calls = []
    def failed(arm, stage):
        calls.append((arm, stage))
        raise RuntimeError('synthetic failure')
    controller.train = failed
    controller.evaluate = lambda stage: pytest.fail('no subsequent evaluation allowed')
    monkeypatch.setattr(r, 'HERE', tmp_path)
    with pytest.raises(RuntimeError):
        controller.run()
    assert calls == [('static', 1)]
    assert not json.loads((tmp_path / 'controller_error.json').read_text())['automatic_retry']


def test_existing_live_owner_blocks_recovery(monkeypatch):
    monkeypatch.setattr(r.ev, 'read_json', lambda _: {'pid': 1, 'create_time': 1})
    monkeypatch.setattr(r.ctl, 'owner_live', lambda _: True)
    with pytest.raises(ValueError, match='owner live'):
        r.require_dead()
