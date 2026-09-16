import copy
import json
import time

import pytest
import resume_control_second as r


def test_completed_static_is_reused_and_only_moving_stage1_redirected():
    assert r.stage_directory('static', 1) == r.PREVIOUS / 'static_stage1_remainder'
    assert r.stage_directory('moving256', 1) == r.RUN
    for arm in ('static', 'moving256'):
        assert r.stage_directory(arm, 2) == r.BASE / f'{arm}_stage2'


@pytest.mark.parametrize('arm,stage', [('moving256', 1), ('moving256', 2), ('static', 2)])
def test_real_command_preserves_every_non_io_option(monkeypatch, arm, stage):
    monkeypatch.setattr(r.ctl, 'stage_directory', r.stage_directory)
    parent = r.VIEW / 'latest.pt'
    old = r.first.ORIGINAL_COMMAND(arm, stage, parent, 5776996)
    new = r.training_command(arm, stage, parent, 5776996)
    assert old[:2] == new[:2] and old[3:] == new[3:]
    assert new[2] == str(r.WRAPPER)
    for flag, expected in [('--seed', '20263003'), ('--worker-seed-base', '2026300300'),
                           ('--total-environment-hands', str(r.ctl.TARGETS[stage]))]:
        assert new[new.index(flag) + 1] == expected
    assert '--no-reset-optimizer' in new and '--preserve-resumed-optimizer-lr' in new
    assert '--reset-hand-counter' not in new and '--reset-optimizer' not in new
    assert '--deal-attempt-namespace' not in new


def test_completed_static_cannot_be_invoked_again():
    controller = object.__new__(r.SecondRecovery)
    with pytest.raises(ValueError, match='never be rerun'):
        controller.train('static', 1)


def test_original_eval_parent_restored_even_after_resume_failure(monkeypatch):
    def fail(self, arm, stage):
        assert r.ctl.PARENT == r.VIEW / 'latest.pt'
        raise RuntimeError('synthetic failure')
    monkeypatch.setattr(r.ctl.Controller, 'train', fail)
    controller = object.__new__(r.SecondRecovery)
    with pytest.raises(RuntimeError):
        controller.train('moving256', 1)
    assert r.ctl.PARENT == r.ORIGINAL_PARENT


def test_both_partials_count_once_and_unpublished_is_not_extra(monkeypatch):
    monkeypatch.setattr(r.first, 'ORIGINAL_ACCOUNTING', lambda: ({'new_training_hands': 980234, 'new_transition_hands': 865743}, {}))
    static = {'new_retained_physical_hands': 1119129, 'new_retained_transition_hands': 978072,
              'observed_completed_but_uncheckpointed_physical_hands': 4292,
              'observed_completed_but_uncheckpointed_transition_hands': 4123,
              'retained_physical_hands': 5314037, 'iteration': 1117}
    moving = {'recoverable_new_physical_hands': 1582088, 'recoverable_new_transition_hands': 1382376,
              'unpublished_completed_update_physical_hands': 5256, 'candidate_physical_hands': 5776996,
              'candidate_iteration': 1215, 'candidate_sha256': r.CANDIDATE_SHA}
    monkeypatch.setattr(r.ev, 'read_json', lambda p: static if p.name == 'interruption_audit.json' else moving)
    counts, runs = r.live_accounting()
    assert counts['retained_training_hands'] == 3681451
    assert counts['new_training_hands'] == 3685743
    assert counts['recovered_unpublished_physical_hands_already_in_retained'] == 5256
    assert counts['new_transition_hands'] - counts['retained_transition_hands'] == 4123
    assert all(type(v) is int for v in counts.values())
    assert len(runs) == 2


@pytest.mark.parametrize('bad', ['namespace', 'reference'])
def test_new_attempt_requires_fresh_namespace_and_preserved_reference(bad):
    parent = {'moving_source_policy_reference': {'completed_updates': 335, 'reference_round': 1}}
    initial = {**copy.deepcopy(parent), 'fixed_deal_attempt': {'receipt': {'namespace': 'new'}}}
    assert all(r.extra_resume_gates(parent, initial, {'old1', 'old2', 'old3'}, lambda a, b: a == b).values())
    if bad == 'namespace':
        initial['fixed_deal_attempt']['receipt']['namespace'] = 'old2'
    else:
        initial['moving_source_policy_reference']['completed_updates'] = 0
    assert not all(r.extra_resume_gates(parent, initial, {'old1', 'old2', 'old3'}, lambda a, b: a == b).values())


@pytest.mark.parametrize('collapse', [False, True])
def test_sequence_reuses_static_and_honors_original_collapse(monkeypatch, tmp_path, collapse):
    controller = object.__new__(r.SecondRecovery)
    controller.started, controller.child = time.perf_counter(), None
    controller.results = [{'arm': 'static', 'stage': 1}]
    controller.tick = lambda **kwargs: None
    calls = []
    def train(arm, stage):
        calls.append(('train', arm, stage))
        controller.results.append({'arm': arm, 'stage': stage})
    def evaluate(stage):
        calls.append(('evaluate', stage))
        return {'broad_collapse': collapse}
    controller.train, controller.evaluate = train, evaluate
    monkeypatch.setattr(r, 'HERE', tmp_path)
    controller.run()
    expected = [('train', 'moving256', 1), ('evaluate', 1)]
    if not collapse:
        expected += [('train', 'moving256', 2), ('train', 'static', 2), ('evaluate', 2)]
    assert calls == expected
    assert json.loads((tmp_path / 'pipeline_result.json').read_text())['final_goal_qualified'] is False


def test_failure_starts_no_next_job(monkeypatch, tmp_path):
    controller = object.__new__(r.SecondRecovery)
    controller.child, controller.tick = None, lambda **kwargs: None
    calls = []
    def fail(arm, stage):
        calls.append((arm, stage))
        raise RuntimeError('synthetic job failure')
    controller.train = fail
    controller.evaluate = lambda _: pytest.fail('must not evaluate after error')
    monkeypatch.setattr(r, 'HERE', tmp_path)
    with pytest.raises(RuntimeError):
        controller.run()
    assert calls == [('moving256', 1)]
    assert not json.loads((tmp_path / 'controller_error.json').read_text())['automatic_retry']
