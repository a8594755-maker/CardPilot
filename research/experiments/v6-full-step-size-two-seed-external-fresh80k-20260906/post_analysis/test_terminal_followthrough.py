import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location('four_policy_terminal_chain_tests', Path(__file__).with_name('terminal_followthrough.py'))
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_waits_for_exact_live_owner_without_reading_any_outcomes():
    states = iter([True, True, False])
    pauses, reads = [], []
    def read_execution():
        reads.append('execution_only')
        return dict(m.EXPECTED_OWNER)
    value = m.wait_for_owner(m.EXPECTED_OWNER, live=lambda _: next(states),
                             read_execution=read_execution, pause=pauses.append)
    assert value == m.EXPECTED_OWNER
    assert pauses == [15, 15] and reads == ['execution_only'] * 3


@pytest.mark.parametrize('field', ['pid', 'create_time'])
def test_pid_reuse_or_replaced_owner_is_not_continuation(field):
    value = dict(m.EXPECTED_OWNER)
    value[field] += 1
    with pytest.raises(ValueError, match='identity replaced'):
        m.wait_for_owner(m.EXPECTED_OWNER, live=lambda _: False,
                         read_execution=lambda: value, pause=lambda _: pytest.fail('unexpected wait'))


def test_transient_observation_error_does_not_become_owner_exit():
    calls, pauses, errors = [], [], []
    def inaccessible(_):
        calls.append(1)
        if len(calls) == 1:
            raise PermissionError('synthetic observation failure')
        return False
    result = m.wait_for_owner(m.EXPECTED_OWNER, live=inaccessible,
        read_execution=lambda: m.EXPECTED_OWNER, pause=pauses.append, on_observation_error=errors.append)
    assert result == m.EXPECTED_OWNER and calls == [1, 1] and pauses == [15]
    assert len(errors) == 1 and isinstance(errors[0], PermissionError)


def test_atomic_state_read_failure_repolls_same_identity():
    values = iter([FileNotFoundError('rename gap'), dict(m.EXPECTED_OWNER)])
    def read():
        value = next(values)
        if isinstance(value, Exception): raise value
        return value
    pauses = []
    result = m.wait_for_owner(m.EXPECTED_OWNER, live=lambda _: False, read_execution=read, pause=pauses.append)
    assert result == m.EXPECTED_OWNER and pauses == [15]


def test_review_command_is_fixed_and_contains_no_training_or_requests():
    argv = m.review_command()
    assert argv[1] == '-B'
    assert Path(argv[2]).name == 'review_completed.py'
    assert argv[3] == '--out' and Path(argv[4]) == m.review.BASE / 'post_terminal_review.json'
    assert len(argv) == 5


def test_existing_attempt_blocks_before_any_admission_or_outcomes(tmp_path, monkeypatch):
    (tmp_path / 'followthrough_execution.json').write_text('{}')
    monkeypatch.setattr(m, 'HERE', tmp_path)
    monkeypatch.setattr(m, 'validate_qualification', lambda: pytest.fail('prior attempt must block first'))
    with pytest.raises(ValueError, match='existing attempt'):
        m.run()


@pytest.mark.parametrize('terminal_ready', [False, True])
def test_no_model_review_if_owner_not_currently_live(tmp_path, monkeypatch, terminal_ready):
    monkeypatch.setattr(m, 'HERE', tmp_path)
    monkeypatch.setattr(m.review, 'BASE', tmp_path)
    monkeypatch.setattr(m, 'validate_qualification', lambda: None)
    monkeypatch.setattr(m.review.r, 'read', lambda _: dict(m.EXPECTED_OWNER))
    monkeypatch.setattr(m.review.r, 'live_identity', lambda _: False)
    monkeypatch.setattr(m.review, 'readiness', lambda: {'ready': terminal_ready})
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *a, **k: pytest.fail('dead initial owner cannot launch'))
    with pytest.raises(ValueError, match='currently live'):
        m.run()
    assert not list(tmp_path.iterdir())


def test_terminal_but_failed_controller_never_launches_review(tmp_path, monkeypatch):
    monkeypatch.setattr(m, 'HERE', tmp_path)
    monkeypatch.setattr(m.review, 'BASE', tmp_path)
    monkeypatch.setattr(m, 'validate_qualification', lambda: None)
    monkeypatch.setattr(m.review.r, 'read', lambda _: dict(m.EXPECTED_OWNER))
    monkeypatch.setattr(m.review.r, 'live_identity', lambda _: True)
    monkeypatch.setattr(m, 'wait_for_owner', lambda *a, **k: dict(m.EXPECTED_OWNER))
    monkeypatch.setattr(m.review, 'readiness', lambda: {'ready': False})
    monkeypatch.setattr(m.subprocess, 'Popen', lambda *a, **k: pytest.fail('failed controller must not run review'))
    with pytest.raises(SystemExit):
        m.run()
    state = m.json.loads((tmp_path / 'followthrough_execution.json').read_text())
    assert state['status'] == 'STOPPED_PRESERVED_NO_RETRY' and state['review_child'] is None
