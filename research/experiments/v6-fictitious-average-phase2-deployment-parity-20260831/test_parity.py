import copy
import math
import numpy as np
import pytest
import run_readiness as run
from parity_contract import assert_parity,fit_gate

def fixture():
    obs = dict(card_info=np.zeros((6, 4, 13)), action_info=np.zeros((25, 4, 5)), extra_info=np.ones(2),
               legal_mask=np.array([0, 1, 0, 0, 0, 0, 0, 0, 0]), player=1)
    table = [None, 'k', None, None, None, None, None, None, None]
    decision = ('k', dict(behavior_probs=[0, 1., 0, 0, 0, 0, 0, 0, 0], selected_action_slot=1,
        direct_increment='k', behavior_action_probability=1., policy_mode='sample', temperature=1.))
    return obs, table, decision


def test_identical_parity():
    obs, table, decision = fixture()
    assert_parity(obs, table, copy.deepcopy(obs), table[:], copy.deepcopy(decision), decision)


@pytest.mark.parametrize('key', ['card_info', 'action_info', 'extra_info', 'legal_mask'])
def test_observation_mismatch(key):
    obs, table, decision = fixture()
    second = copy.deepcopy(obs)
    second[key].flat[0] += 1
    with pytest.raises(ValueError):
        assert_parity(obs, table, second, table, decision, decision)


@pytest.mark.parametrize('kind', ['nan', 'normalization', 'illegal', 'selected', 'increment', 'mode'])
def test_invalid_equal_decisions(kind):
    obs, table, decision = fixture()
    info = decision[1]
    if kind == 'nan': info['behavior_probs'][1] = float('nan')
    if kind == 'normalization': info['behavior_probs'][1] = .5
    if kind == 'illegal': info['behavior_probs'][0:2] = [.5, .5]
    if kind == 'selected': info['selected_action_slot'] = 0
    if kind == 'increment': info['direct_increment'] = 'f'
    if kind == 'mode': info['policy_mode'] = 'greedy'
    with pytest.raises(ValueError):
        assert_parity(obs, table, obs, table, decision, decision)



def parent():
    return dict(status='COMPLETED'),dict(status='PASS',decision='ADMIT_SEPARATE_AVERAGE_ASSESSMENT',
        model_sha256='a'*64,epochs=8,optimizer_steps=2048,new_training_hands=262144,
        supervised_validation_hands=8192,strength_evaluation_hands=0,slumbot_hands=0,
        qualification_hands=0,goal_achieved=False,hand_ci95=[.1,.3])


def test_exact_completed_epoch8_fit_required():
    record,review=parent()
    assert fit_gate(record,review,'a'*64)
    record['status']='RUNNING'
    assert not fit_gate(record,review,'a'*64)


@pytest.mark.parametrize('key,value',[('epochs',4),('optimizer_steps',1024),('new_training_hands',262143),
    ('supervised_validation_hands',8191),('model_sha256','wrong'),('slumbot_hands',1),
    ('goal_achieved',True),('hand_ci95',[0.,1.]),('hand_ci95',[math.nan,1.])])
def test_invalid_parent_fit(key,value):
    record,review=parent()
    review[key]=value
    assert not fit_gate(record,review,'a'*64)


def test_missing_hashes_fail_before_output_or_queries(monkeypatch,tmp_path):
    monkeypatch.setattr(run,'BASE',tmp_path)
    monkeypatch.setattr(run,'MODEL_SHA',None)
    monkeypatch.setattr(run,'FIT_REVIEW_SHA',None)
    with pytest.raises(ValueError,match='no model queries or output creation'):
        run.main()
    assert list(tmp_path.iterdir())==[]


def test_real_admission_after_hash_freeze():
    if run.MODEL_SHA is None or run.FIT_REVIEW_SHA is None:
        pytest.skip('Future phase2average not yet fitted; no admission')
    run.require_admission()
