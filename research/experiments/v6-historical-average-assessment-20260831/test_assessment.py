import copy
import math
import numpy as np
import pytest
from assessment_contract import parent_gate, paired_difference, assert_parity


def parent():
    return dict(status='COMPLETED'), dict(status='PASS', decision='ADMIT_SEPARATE_STRENGTH_DIAGNOSTIC',
        epochs=12, optimizer_steps=3072, new_training_hands=262144, supervised_validation_hands=8192,
        slumbot_hands=0, goal_achieved=False)


def test_parent_finished_fit_required():
    record, review = parent()
    assert parent_gate(record, review)
    record['status'] = 'RUNNING'
    assert not parent_gate(record, review)


@pytest.mark.parametrize('key,value', [('epochs', 4), ('new_training_hands', 262143), ('decision', 'HISTORICAL_FIT_GATE_NOT_PASSED'), ('goal_achieved', True)])
def test_invalid_parent(key, value):
    record, review = parent()
    review[key] = value
    assert not parent_gate(record, review)


def pairs(values):
    return [dict(pair_index=i, deck=list(range(52)), rewards_bb=[v, v], decisions=[1, 1]) for i, v in enumerate(values)]


def test_pair_units_and_adjusted_intervals():
    result = paired_difference(pairs([2., 4., 6.]), pairs([1., 1., 1.]))
    assert result['bb_per_100'] == 300.
    assert math.isclose(result['standard_error'], 200/math.sqrt(3))
    assert result['family5_ci95'][0] < result['ci95'][0]
    assert result['family5_ci95'][1] > result['ci95'][1]


@pytest.mark.parametrize('kind', ['index', 'deck', 'count', 'nan', 'bounds'])
def test_no_unpaired_or_invalid_rewards(kind):
    left, right = pairs([1., 2.]), pairs([1., 2.])
    if kind == 'index':
        right[0]['pair_index'] = 1
    elif kind == 'deck':
        right[0]['deck'].reverse()
    elif kind == 'count':
        right.pop()
    elif kind == 'nan':
        right[0]['rewards_bb'][0] = float('nan')
    else:
        right[0]['rewards_bb'][0] = 201
    with pytest.raises(ValueError):
        paired_difference(left, right)


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
