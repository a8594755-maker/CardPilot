import copy
import numpy as np
import pytest
from parity_contract import assert_parity, assert_coverage


def fixture():
    obs = dict(card_info=np.zeros((6,4,13)), action_info=np.zeros((25,4,5)), extra_info=np.ones(2),
               legal_mask=np.array([0,1,0,0,0,0,0,0,0]), player=1)
    table = [None,'k',None,None,None,None,None,None,None]
    decision = ('k', dict(behavior_probs=[0,1.,0,0,0,0,0,0,0], selected_action_slot=1,
                          direct_increment='k', behavior_action_probability=1., policy_mode='sample', temperature=1.))
    return obs, table, decision


def test_identical():
    obs, table, decision = fixture()
    assert_parity(obs, table, copy.deepcopy(obs), table[:], copy.deepcopy(decision), decision)


@pytest.mark.parametrize('key', ['card_info','action_info','extra_info','legal_mask'])
def test_observation_mismatch(key):
    obs, table, decision = fixture()
    second = copy.deepcopy(obs)
    second[key].flat[0] += 1
    with pytest.raises(ValueError): assert_parity(obs, table, second, table, decision, decision)


@pytest.mark.parametrize('kind', ['nan','normalization','illegal','selected','increment','mode'])
def test_decision_invalid_even_if_both_equal(kind):
    obs, table, decision = fixture()
    info = decision[1]
    if kind == 'nan': info['behavior_probs'][1] = float('nan')
    if kind == 'normalization': info['behavior_probs'][1] = .5
    if kind == 'illegal': info['behavior_probs'][0:2] = [.5,.5]
    if kind == 'selected': info['selected_action_slot'] = 0
    if kind == 'increment': info['direct_increment'] = 'f'
    if kind == 'mode': info['policy_mode'] = 'greedy'
    with pytest.raises(ValueError): assert_parity(obs, table, obs, table, decision, decision)


def test_unequal_decisions():
    obs, table, decision = fixture()
    second = copy.deepcopy(decision)
    second[1]['temperature'] = 2.
    with pytest.raises(ValueError): assert_parity(obs, table, obs, table, decision, second)


def test_missing_coverage():
    valid = {f'street{s}_seat{p}':1 for s in range(4) for p in range(2)}
    assert_coverage(valid)
    valid['street3_seat0'] = 0
    with pytest.raises(ValueError): assert_coverage(valid)
