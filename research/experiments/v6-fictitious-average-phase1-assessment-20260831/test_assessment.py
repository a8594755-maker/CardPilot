import copy
import math
import numpy as np
import pytest
from assessment_contract import parent_gate, paired_difference, assert_parity, estimate, strategic_profile


def parent():
    return dict(status='COMPLETED'), dict(status='PASS', decision='ADMIT_SEPARATE_AVERAGE_ASSESSMENT',
        epochs=4, optimizer_steps=1024, new_training_hands=262144, supervised_validation_hands=8192,
        slumbot_hands=0, goal_achieved=False)


def test_parent_finished_fit_required():
    record, review = parent()
    assert parent_gate(record, review)
    record['status'] = 'RUNNING'
    assert not parent_gate(record, review)


@pytest.mark.parametrize('key,value', [('epochs', 12), ('new_training_hands', 262143), ('decision', 'HISTORICAL_FIT_GATE_NOT_PASSED'), ('goal_achieved', True)])
def test_invalid_parent(key, value):
    record, review = parent()
    review[key] = value
    assert not parent_gate(record, review)


def pairs(values):
    return [dict(pair_index=i, deck=list(range(52)), rewards_bb=[v, v], decisions=[1, 1]) for i, v in enumerate(values)]


def test_pair_units_and_adjusted_intervals():
    result = paired_difference(pairs([2., 4., 6.]), pairs([1., 1., 1.]), 5)
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


def matrix():
    return {(c,a): [0.,0.,0.] for c in ('prior','response','student')
            for a in ('prior','response','anchor0','anchor1','anchor2','anchor3','anchor4')}


def test_primary_pairing_and_mixture_units():
    m = matrix()
    m['student','response'] = [200.,200.,200.]
    m['prior','response'] = [-200.,-200.,-200.]
    m['student','anchor1'] = [300.,300.,300.]
    m['student','anchor2'] = [500.,500.,500.]
    m['response','anchor1'] = [-100.,-100.,-100.]
    m['response','anchor2'] = [-100.,-100.,-100.]
    result = strategic_profile(m)
    assert result['primary_contrasts']['hedge_against_response']['bb_per_100'] == 400
    assert result['primary_contrasts']['retain_anchor1_2_vs_response']['bb_per_100'] == 500
    assert result['student_minus_episode_mixture']['response']['bb_per_100'] == 300
    assert result['decision'] == 'ADMIT_NEXT_RESPONSE_PHASE'


@pytest.mark.parametrize('kind',['zero','negative','wide'])
def test_both_family2_lowers_required(kind):
    m = matrix()
    m['student','response'] = [100.,100.,100.]
    if kind == 'negative': m['student','anchor1'] = [-100.,-100.,-100.]
    if kind == 'wide': m['student','anchor1'] = [-5000.,100.,5000.]
    assert strategic_profile(m)['decision'] == 'AVERAGE_STRATEGIC_GATE_NOT_PASSED'


@pytest.mark.parametrize('kind',['missing','unequal','nan','bounds'])
def test_invalid_matrix_rejected(kind):
    m = matrix()
    if kind == 'missing': m.pop(('prior','prior'))
    if kind == 'unequal': m['prior','prior'].pop()
    if kind == 'nan': m['prior','prior'][0] = float('nan')
    if kind == 'bounds': m['prior','prior'][0] = 20001.
    with pytest.raises(ValueError): strategic_profile(m)


def test_family_correction_widens():
    a,b,c = [estimate([1.,2.,3.,4.], n) for n in (1,2,7)]
    assert c['family7_ci95'][0] < b['family2_ci95'][0] < a['family1_ci95'][0]


def test_retention_combines_within_pair_before_variance():
    m = matrix()
    m['student','anchor1'] = [100.,200.,300.]
    m['student','anchor2'] = [300.,200.,100.]
    result = strategic_profile(m)['primary_contrasts']['retain_anchor1_2_vs_response']
    assert result['bb_per_100'] == 200. and result['standard_error'] == 0.


def test_budget_seeds_and_fixed_matrix():
    import run_assessment as run
    assert run.TOTAL_HANDS == run.PAIRS*2*len(run.CANDIDATES)*len(run.OPPONENTS) == 172032
    assert run.SEED == 20261016 and len(set(run.OPPONENTS)) == 7
    cmds = [run.eval_command(c,a) for c in run.CANDIDATES for a in run.OPPONENTS]
    assert len({tuple(c) for c in cmds}) == 21
    assert all(c[-2:] == ['--device','cpu'] for c in cmds)


def test_real_admission_when_hashes_frozen():
    import run_assessment as run
    if run.STUDENT_SHA is None:
        pytest.skip('Parent fitting remains active; execution is forbidden until hashes frozen')
    assert run.validate_parent()['model_sha256'] == run.STUDENT_SHA
