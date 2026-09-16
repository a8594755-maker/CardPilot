import copy
import math
import pytest
from qualification_stats import admission,summarize

def parent():
    return {'status':'COMPLETED'},dict(status='PASS',decision='ADMIT_SEPARATE_FRESH100K_CONFIRMATION',
        model_sha256='a'*64,evaluation_hands=20000,slumbot_hands=20000,new_training_hands=0,
        supports_separate_100k_confirmation=True,statistics={'bb_per_100':1.},goal_achieved=False)

def test_complete_positive_parent_only():
    rec,report=parent()
    assert admission(rec,report,'a'*64)
    assert not admission({'status':'RUNNING'},report,'a'*64)
    assert not admission(rec,report,'b'*64)

@pytest.mark.parametrize('key,value',[('status','FAIL'),('evaluation_hands',19999),
    ('slumbot_hands',0),('new_training_hands',1),('supports_separate_100k_confirmation',False),
    ('goal_achieved',True),('statistics',{'bb_per_100':0.}),('statistics',{'bb_per_100':-1.}),
    ('statistics',{'bb_per_100':math.nan})])
def test_invalid_parent(key,value):
    rec,report=parent()
    report[key]=value
    assert not admission(rec,report,'a'*64)

def test_exact100k_positive_does_not_replace_evidence_audit():
    result=summarize([[100]*12500 for _ in range(8)])
    assert result['hands']==100000 and result['bb_per_100']==100
    assert result['raw_hand_ci95']==result['session_t7_ci95']==[100,100]
    assert result['primary_raw_gate'] and result['conservative_statistical_gate']
    assert not result['goal_achieved'] and result['evidence_validation_required']
    assert result['pilot_hands_pooled']==result['old_hands_pooled']==0

def test_cluster_disagreement_is_not_conservative_pass():
    result=summarize([[200]*12500 for _ in range(7)]+[[-1000]*12500])
    assert result['bb_per_100']==50 and result['primary_raw_gate']
    assert result['session_t7_ci95'][0]<0 and not result['conservative_statistical_gate']

def test_zero_boundary_rejected():
    result=summarize([[0]*12500 for _ in range(8)])
    assert not result['primary_raw_gate'] and not result['conservative_statistical_gate']

@pytest.mark.parametrize('bad',[20001,True,1.,float('nan')])
def test_invalid_outcome(bad):
    groups=[[0]*12500 for _ in range(8)]
    groups[0][0]=bad
    with pytest.raises(ValueError):summarize(groups)

def test_20k_or_partial_or_extended_cohort_rejected():
    for groups in ([[0]*2500 for _ in range(8)],[[0]*12500 for _ in range(7)],
                   [[0]*12501 for _ in range(8)]):
        with pytest.raises(ValueError):summarize(groups)

