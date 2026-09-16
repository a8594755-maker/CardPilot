import json
from pathlib import Path

import pytest

import resume_actor as r


@pytest.mark.parametrize('seed,arm,stage', [(s, a, stage) for stage, order in r.ctl.ORDERS.items() for s, a in order])
def test_only_interrupted_logical_endpoint_is_redirected(seed, arm, stage):
    expected = r.RUN if (seed, arm, stage) == (1, 'connected', 1) else r.ORIGINAL_DIRECTORY(seed, arm, stage)
    assert r.recovered_directory(seed, arm, stage) == expected


def test_remainder_command_changes_only_output_and_resume_paths(monkeypatch):
    recorded = r.read(r.OLD / 'command.json')
    assert isinstance(recorded, list)
    monkeypatch.setattr(r.ctl, 'directory', r.recovered_directory)
    actual = r.ctl.training_command(1, 'connected', 1, r.OLD / 'latest.pt', 10507221)
    allowed = {'--resume', '--run-dir', '--out', '--opponent-assignment-provenance-file'}
    assert len(actual) == len(recorded)
    changes = []
    for i, (old, new) in enumerate(zip(recorded, actual)):
        if old != new:
            assert i and actual[i - 1] in allowed
            changes.append(actual[i - 1])
    assert set(changes) == allowed
    assert actual[actual.index('--total-environment-hands') + 1] == '10760378'
    assert actual[actual.index('--max-runtime-seconds') + 1] == '7200'
    assert '--no-reset-optimizer' in actual and '--preserve-resumed-optimizer-lr' in actual
    assert '--preflop-trunk-gradient' in actual and '--deal-attempt-namespace' not in actual


def test_stage2_uses_recovered_endpoint_but_eval_keeps_original_parent(monkeypatch):
    original_parent = r.ctl.PARENTS[1]
    monkeypatch.setattr(r.ctl, 'directory', r.recovered_directory)
    monkeypatch.setattr(r.ctl, 'parent_path', r.recovered_parent_path)
    assert r.ctl.parent_path(1, 'connected', 1) == r.OLD / 'latest.pt'
    assert r.ctl.parent_path(1, 'connected', 2) == r.RUN / 'latest.pt'
    command = r.ctl.evaluate_command(1, 'connected', 1)
    assert Path(command[command.index('--control') + 1]) == original_parent
    assert Path(command[command.index('--treatment') + 1]) == r.RUN / 'latest.pt'
    assert command[command.index('--seed') + 1] == '20264211'


def test_original_parent_restored_after_failed_remainder(monkeypatch):
    original = r.ctl.PARENTS[1]
    monkeypatch.setattr(r, 'sha', lambda _: r.SAVED_SHA)
    def failed(self, seed, arm, stage):
        assert r.ctl.PARENTS[1] == r.OLD / 'latest.pt'
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(r.ctl.Controller, 'train', failed)
    with pytest.raises(RuntimeError, match='synthetic failure'):
        object.__new__(r.Recovery).train(1, 'connected', 1)
    assert r.ctl.PARENTS[1] == original


@pytest.mark.parametrize('unsaved', (0, 17))
def test_interrupted_counts_are_added_once_and_unknown_tail_is_not_invented(unsaved):
    original = {'new_training_hands': 266415 + 100, 'new_transition_hands': 230891 + 80, 'evaluation_hands': 0}
    partial = {'new_retained_physical_hands': 8987, 'new_retained_transition_hands': 8253,
               'observed_completed_but_uncheckpointed_physical_hands': unsaved,
               'observed_completed_but_uncheckpointed_transition_hands': 0,
               'unknown_additional_worker_tail_hands': None}
    totals = r.add_interrupted_accounting(original, partial)
    assert totals['retained_training_hands'] == 266415 + 8987 + 100
    assert totals['new_training_hands'] == totals['retained_training_hands'] + unsaved
    assert totals['new_transition_hands'] == 230891 + 8253 + 80
    assert original['new_training_hands'] == 266515
    assert 'unknown_additional_worker_tail_hands' not in totals


def test_existing_owner_blocks_recovery(monkeypatch):
    monkeypatch.setattr(r.audit.ctl.execution, 'owner_live', lambda _: True)
    with pytest.raises(ValueError, match='original process live'):
        r.audit.require_dead()


def test_fresh_namespace_gate_and_full_state_checks(monkeypatch):
    called = []
    monkeypatch.setattr(r.ctl.prior, 'initial_audit', lambda p, i, f: called.append(('full', f)))
    monkeypatch.setattr(r.ctl, 'route_audit', lambda i, e, p: called.append(('route', e)))
    monkeypatch.setattr(r.ctl.GRADIENT, 'checkpoint_flag', lambda _: True)
    parent = {'fixed_deal_attempt': {'receipt': {'namespace': 'parent'}}}
    initial = {'fixed_deal_attempt': {'receipt': {'namespace': 'fresh'}}}
    assert r.initial_gate(parent, initial, {'old'})['passed']
    assert called == [('full', True), ('route', True)]
    with pytest.raises(ValueError, match='namespace reused'):
        r.initial_gate(parent, initial, {'fresh'})
    initial['fixed_deal_attempt']['receipt']['namespace'] = 'parent'
    with pytest.raises(ValueError, match='namespace reused'):
        r.initial_gate(parent, initial, set())


@pytest.mark.parametrize('stage1_collapse,stage2_collapse', [(False, False), (True, False), (False, True)])
def test_fixed_schedule_skips_completed_control_and_retains_both_gates(monkeypatch, tmp_path, stage1_collapse, stage2_collapse):
    controller = object.__new__(r.Recovery)
    controller.started = r.time.perf_counter()
    controller.results = []
    controller.child = None
    controller.tick = lambda **kwargs: None
    calls = []
    controller.train = lambda seed, arm, stage: calls.append(('train', seed, arm, stage))
    def evaluate(stage):
        calls.append(('evaluate', stage))
        return {'broad_collapse': stage1_collapse if stage == 1 else stage2_collapse}
    controller.evaluate = evaluate
    monkeypatch.setattr(r, 'HERE', tmp_path)
    monkeypatch.setattr(r.ctl, 'logger', lambda *args: None)
    controller.run()
    expected = [('train', 1, 'connected', 1), ('train', 3, 'connected', 1), ('train', 3, 'detached', 1), ('evaluate', 1)]
    if not stage1_collapse:
        expected += [('train', s, a, 2) for s, a in r.ctl.ORDERS[2]] + [('evaluate', 2)]
    assert calls == expected
    expected_phase = 'STAGE1_BROAD_COLLAPSE_REVIEW' if stage1_collapse else ('STAGE2_BROAD_COLLAPSE_REVIEW' if stage2_collapse else 'FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW')
    assert controller.phase == expected_phase
    assert not json.loads((tmp_path / 'controller_result.json').read_text())['goal_achieved']


def test_first_remainder_failure_never_launches_other_work(monkeypatch, tmp_path):
    controller = object.__new__(r.Recovery)
    controller.child = None
    controller.tick = lambda **kwargs: None
    calls = []
    def failed(*args):
        calls.append(args)
        raise RuntimeError('synthetic failure')
    controller.train = failed
    controller.evaluate = lambda _: pytest.fail('must not evaluate')
    monkeypatch.setattr(r, 'HERE', tmp_path)
    with pytest.raises(RuntimeError):
        controller.run()
    assert calls == [(1, 'connected', 1)]
    assert not json.loads((tmp_path / 'controller_error.json').read_text())['automatic_retry']
