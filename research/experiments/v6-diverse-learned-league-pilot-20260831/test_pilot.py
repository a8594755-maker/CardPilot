import math
from pathlib import Path
import pytest
import run_pilot as pilot


def test_matched_commands_only_pool_and_run_identity_differ():
    control, diverse = pilot.training_command('control3'), pilot.training_command('diverse5')
    normalized = [v.replace('control3','diverse5') for v in control]
    extra = [str(pilot.BASE/'frozen'/f'{name}.pt') for name,_,_ in pilot.LEAGUE]
    assert [v for v in diverse if v not in extra] == normalized
    for cmd in [control,diverse]:
        for flag,value in [('--total-environment-hands','262144'),('--seed','20260926'),('--worker-seed-base','2026092600'),
                           ('--rollout-mode','multi'),('--rollout-envs-per-worker','8'),('--source-policy-kl-coef','.01')]:
            assert cmd[cmd.index(flag)+1] == value
        assert cmd[cmd.index('--resume')+1] == str(pilot.ROOT/'models/baseline/standard10/latest.pt')
        assert all(flag in cmd for flag in ['--reset-optimizer','--reset-hand-counter','--validate-stream','--v6-rebind-legacy-weights'])
    for cmd, expected in [(control,['anchor0.pt','anchor1.pt','anchor2.pt']),
                          (diverse,['anchor0.pt','anchor1.pt','anchor2.pt','league_kl001.pt','league_kl010.pt'])]:
        start = cmd.index('--fixed-opponent-checkpoints')+1
        end = next(i for i in range(start,len(cmd)) if cmd[i].startswith('--'))
        assert [Path(p).name for p in cmd[start:end]] == expected


def row(a=0,mean=5,low=1): return dict(anchor=a,bb_per_100=mean,ci_adjusted=[low,10])


def test_gate_requires_heldout_and_control_difference():
    valid = [row(a,low=1 if a in [0,1,3] else -1) for a in range(5)]
    assert pilot.stats.gate(valid,row())
    assert not pilot.stats.gate(valid,row(low=-1))
    assert not pilot.stats.gate([row(a,low=1 if a < 3 else -1) for a in range(5)],row())
    assert not pilot.stats.gate([row(a,mean=-1 if a==4 else 5) for a in range(5)],row())


@pytest.mark.parametrize('values',[[],[1],[1,math.nan],[1,math.inf]])
def test_nonfinite_or_incomplete_statistics_rejected(values):
    with pytest.raises(ValueError): pilot.stats.estimate(values)


def test_six_family_statistics_and_complete_line_accounting(tmp_path):
    r = pilot.stats.estimate([1,3])
    assert r['bb_per_100'] == 2 and r['standard_error'] == 1
    assert r['ci95'] == pytest.approx([.04,3.96])
    assert r['ci_adjusted'][0] < -0.5758
    path = tmp_path/'pairs.jsonl'
    path.write_bytes(b'{}\n{}\n{"partial":')
    assert pilot.stats.raw_count(path) == 2


def test_independent_interval_agrees():
    review = pilot.load_module('previous_independent_interval',pilot.RETENTION/'review_finish.py')
    values = [-25.25,0,88.125,39.5,-12]
    assert pilot.stats.estimate(values)['ci_adjusted'] == pytest.approx(review.interval(values)['ci_adjusted'])
