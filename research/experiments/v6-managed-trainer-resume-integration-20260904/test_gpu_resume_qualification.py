"""No GPU workers: prelaunch contract and fail-closed evidence tests."""
import importlib.util
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location('gpu_qualification_tested', HERE / 'run_gpu_resume_qualification.py')
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


@pytest.mark.parametrize('name', ['', '.', '..', '../old', 'old/new', 'old\\new'])
def test_reject_unsafe_output_name(name):
    with pytest.raises(ValueError):
        MODULE.safe_output_name(name)


@pytest.mark.parametrize('arm,mode,slots', [('single1', 'single', '1'), ('multi8', 'multi', '8')])
def test_command_preserves_recipe_and_counters(tmp_path, arm, mode, slots):
    argv = MODULE.command(tmp_path, tmp_path / 'parent.pt', 4197976, arm, tmp_path / 'registry')
    value = lambda key: argv[argv.index(key) + 1]
    assert value('--total-environment-hands') == str(4197976 + 8192)
    assert value('--rollout-mode') == mode
    assert value('--rollout-envs-per-worker') == slots
    assert value('--workers') == '12'
    assert value('--source-policy-kl-direction') == 'current_to_reference'
    assert value('--source-policy-kl-coef') == '1'
    assert value('--ppo-replay-ratio') == '0.5'
    assert value('--ppo-replay-buffer-iterations') == '2'
    assert value('--worker-seed-base') == '2026300100'
    assert value('--seed') == '20263001'
    for flag in ('--no-reset-optimizer', '--preserve-resumed-optimizer-lr',
                 '--managed-deal-attempts', '--resume-assignment-state-from-provenance'):
        assert flag in argv
    assert '--reset-hand-counter' not in argv


def test_no_new_rollout_arm(tmp_path):
    with pytest.raises(ValueError):
        MODULE.command(tmp_path, tmp_path, 1, 'multi32', tmp_path)


def metric():
    return {'iteration': 883, 'entropy': .5, 'approx_kl': .001, 'reference_policy_kl': .002}


def test_finite_metrics_require_both_sources():
    text = '[  883] hands=1 ploss=0.01 vloss=0.02 vloss_bb2=800\n'
    assert MODULE.finite_update_evidence([metric()], text)
    assert not MODULE.finite_update_evidence([metric()], '')
    assert not MODULE.finite_update_evidence([], text)
    assert not MODULE.finite_update_evidence([{'iteration': 883}], text)
    assert not MODULE.finite_update_evidence([metric()], text.replace('0.02', 'nan'))
    assert not MODULE.finite_update_evidence([metric()], text.replace('883', '884'))


def results(multi_speed=150):
    rows = []
    for index, (arm, attempt) in enumerate(MODULE.ORDER):
        speed = 100 if arm == 'single1' else multi_speed
        rows.append({'arm': arm, 'attempt': attempt, 'namespace': str(index), 'passed': True,
                     'new_physical_hands': 10000, 'new_transition_hands': 8500,
                     'subprocess_wall_seconds': 10000 / speed,
                     'physical_hands_per_wall_second': speed})
    return rows


def test_speed_selection_is_not_strength_promotion():
    report = MODULE.summarize(results(), 400)
    assert report['provisional_throughput_choice'] == 'multi8'
    assert report['multi8_over_single1'] == pytest.approx(1.5)
    assert report['diagnostic_environment_hands'] == 40000
    assert not report['checkpoint_promotion_authorized']
    assert not report['strength_claim']
    assert MODULE.summarize(results(110), 400)['provisional_throughput_choice'] == 'single1'


def test_incomplete_failed_or_reused_evidence_rejected():
    with pytest.raises(ValueError):
        MODULE.summarize(results()[:-1], 1)
    for key, value in [('namespace', '0'), ('passed', False)]:
        rows = results()
        rows[-1][key] = value
        with pytest.raises(ValueError):
            MODULE.summarize(rows, 1)


def test_live_pipeline_preflight_never_launches(monkeypatch, capsys):
    monkeypatch.setattr(MODULE, 'preflight', lambda: {'eligible': False, 'blocked_by': ['live owner']})
    monkeypatch.setattr(MODULE.sys, 'argv', ['qualify', '--preflight-only'])
    monkeypatch.setattr(MODULE.subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected worker launch'))
    MODULE.main()
    assert 'live owner' in capsys.readouterr().out


def test_live_pipeline_actual_run_fails_before_workers(monkeypatch):
    monkeypatch.setattr(MODULE, 'preflight', lambda: {'eligible': False, 'blocked_by': ['live owner']})
    monkeypatch.setattr(MODULE.sys, 'argv', ['qualify'])
    monkeypatch.setattr(MODULE.subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected worker launch'))
    with pytest.raises(RuntimeError, match='live owner'):
        MODULE.main()


def test_existing_output_cannot_be_replayed(monkeypatch, tmp_path):
    monkeypatch.setattr(MODULE, 'BASE', tmp_path)
    (tmp_path / 'gpu_current_recipe_v1').mkdir()
    monkeypatch.setattr(MODULE, 'preflight', lambda: {'eligible': True, 'blocked_by': []})
    monkeypatch.setattr(MODULE.sys, 'argv', ['qualify'])
    monkeypatch.setattr(MODULE.subprocess, 'Popen', lambda *a, **k: pytest.fail('unexpected worker launch'))
    with pytest.raises(RuntimeError, match='existing output'):
        MODULE.main()


def test_pid_reuse_does_not_mean_original_worker_alive(monkeypatch):
    import psutil
    class Process:
        def __init__(self, pid):
            self.pid = pid

        def create_time(self):
            return 2.0

        def is_running(self):
            return True
    monkeypatch.setattr(psutil, 'Process', Process)
    assert MODULE.live_known_children({123: 1.0}) == []
    assert MODULE.live_known_children({123: 2.0}) == [123]
