import math
from pathlib import Path
import random
import pytest
import run_pilot as pilot
import transfer_stats as stats
import review_finish as review
from alpha_holdem.train_v5 import build_group_opponent_assignments


def test_only_selfplay_share_and_run_identity_differ():
    a,b=pilot.training_command('control25'),pilot.training_command('selfplay75')
    normalized=[v.replace('control25','selfplay75') for v in a]
    normalized[normalized.index('--self-play-fraction')+1]='.75'
    assert normalized==b
    for cmd in [a,b]:
        for flag,value in [('--total-environment-hands','1048576'),('--seed','20261005'),
                           ('--worker-seed-base','2026100500'),('--rollout-mode','multi'),
                           ('--rollout-envs-per-worker','8'),('--source-policy-kl-coef','.01')]:
            assert cmd[cmd.index(flag)+1]==value
        assert cmd[0]==str(pilot.BASE/'execution_code/source_files/scripts/alpha_holdem/train_v5.py')
        assert cmd[cmd.index('--resume')+1]==str(pilot.ROOT/'models/baseline/standard10/latest.pt')
        assert all(f in cmd for f in ['--reset-optimizer','--reset-hand-counter','--validate-stream','--v6-rebind-legacy-weights'])
        start=cmd.index('--fixed-opponent-checkpoints')+1
        end=next(i for i in range(start,len(cmd)) if cmd[i].startswith('--'))
        assert [Path(p).name for p in cmd[start:end]]==['anchor0.pt','anchor1.pt','anchor2.pt']


@pytest.mark.parametrize('fraction,expected',[(.25,2),(.75,6)])
def test_group_fraction_and_reproducible_rng(fraction,expected):
    rng,replica=random.Random(20261005),random.Random(20261005)
    for _ in range(20):
        a,groups=build_group_opponent_assignments(12,3,8,fraction,rng,[.1,.2,.7])
        b,repeated=build_group_opponent_assignments(12,3,8,fraction,replica,[.1,.2,.7])
        assert list(a)==list(b) and groups==repeated
        assert len(groups)==8 and sum(g['opponent_id']==-1 for g in groups)==expected
        assert sorted(w for g in groups for w in g['workers'])==list(range(12))


def test_both_healthy_endpoints_required_no_score_input():
    valid={label:dict(status='PASS',new_training_hands=1048576,bb_per_100=-999)
           for label in ['control25','selfplay75']}
    assert stats.external_pair_admission(valid)
    valid['selfplay75']['status']='FAIL'
    assert not stats.external_pair_admission(valid)
    valid['selfplay75'].update(status='PASS',new_training_hands=1048575)
    assert not stats.external_pair_admission(valid)
    with pytest.raises(ValueError): stats.external_pair_admission({'control25':valid['control25']})


def test_independent_arithmetic_agrees():
    for values in [[-100,100,300],[0]*20,[-20.1,17.3,20000,-19990]]:
        a,b=stats.estimate(values),review.interval(values)
        for k in ['bb_per_100','standard_error']: assert a[k]==pytest.approx(b[k])
        for k in ['ci95','ci_adjusted']: assert a[k]==pytest.approx(b[k])
        assert a['ci_adjusted'][0]<=a['ci95'][0]<=a['ci95'][1]<=a['ci_adjusted'][1]


@pytest.mark.parametrize('values',[[],[1],[0,math.nan],[0,math.inf]])
def test_bad_values_rejected(values):
    for fn in [stats.estimate,review.interval]:
        with pytest.raises(ValueError): fn(values)


def test_count_complete_raw_lines_only(tmp_path):
    path=tmp_path/'raw.jsonl'
    assert stats.raw_count(path)==0
    path.write_bytes(b'{}\n{}\n{')
    assert stats.raw_count(path)==2


def test_raw_prefix_deck_and_rewards_validation():
    rows=[dict(pair_index=i,deck=list(range(52)),rewards_bb=[-1,2],decisions=[2,3]) for i in range(pilot.PAIRS)]
    assert review.raw_values(rows)==[50]*pilot.PAIRS
    with pytest.raises(ValueError): review.raw_values(rows[:-1])
    rows[10]['rewards_bb']=[201,0]
    with pytest.raises(AssertionError): review.raw_values(rows)


def test_exposure_is_assignment_slots_not_hand_fraction():
    rows=[]
    rng=random.Random(20261005)
    for i in range(3):
        assigned,groups=build_group_opponent_assignments(12,3,8,.75,rng,[.1,.2,.7])
        rows.append(dict(applies_to_iteration=i+1,group_metadata=groups,
                         workers=[dict(worker_id=w,opponent=dict(kind='self_play' if a==-1 else 'pool_snapshot'))
                                  for w,a in enumerate(assigned)]))
    result=stats.exposure(rows,3,6)
    assert result['all_worker_slots']==36 and result['terminal_hand_fraction'] is None
    assert result['selfplay_worker_slots']==sum(result['selfplay_workers_per_update'])
    with pytest.raises(AssertionError): stats.exposure(rows,3,2)


def test_budget_and_frozen_diagnostic_design():
    assert pilot.TARGET==1048576 and pilot.PAIRS==4096 and pilot.EVAL_SEED==20261006
    assert pilot.EVAL_HANDS==3*5*4096*2==122880
