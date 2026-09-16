import copy
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_4m_deviation import ANCHORS, broad_reversal, descriptive_report, verify_raw_arithmetic, validate_nontraining_integrity


@pytest.mark.parametrize('seats, negative_anchors, expected', [
    (True, 0, True), (True, 2, True), (True, 3, True),
    (False, 3, True), (False, 4, True), (False, 2, False), (False, 0, False),
])
def test_broad_reversal_uses_preregistered_or(seats, negative_anchors, expected):
    summary = {'both_seats_negative': seats,
               'by_anchor': {name: {'bb100': -1 if i < negative_anchors else 1} for i, name in enumerate(ANCHORS)}}
    assert broad_reversal(summary) is expected


def rows(reward):
    return [{'anchor': anchor, 'pair_index': i, 'deck': list(range(52)),
        'control_rewards_bb': [0., 0.], 'treatment_rewards_bb': [reward, reward],
        'control_pair_mean_bb': 0., 'treatment_pair_mean_bb': reward,
        'treatment_minus_control_rewards_bb': [reward, reward],
        'treatment_minus_control_pair_mean_bb': reward} for anchor in ANCHORS for i in range(3)]


def drift():
    return {str(seed): {'mean_tv': .01, 'greedy_disagreement_rate': .02} for seed in (1, 2, 3)}


def test_positive_synthetic_outcome_never_authorizes_promotion():
    report = descriptive_report({seed: rows(1.) for seed in (1, 2, 3)}, drift())
    assert report['all_directional_gates_descriptively_pass']
    assert report['promote'] is False
    assert report['automatic_scaling_authorized'] is False


def test_incident_subset_is_always_seed1_seed3_not_selected_by_outcome():
    report = descriptive_report({1: rows(-1.), 2: rows(100.), 3: rows(-1.)}, drift())
    assert report['incident_unaffected_seed_ids'] == [1, 3]
    assert report['aggregate']['incident_unaffected_seed1_seed3']['pooled']['bb100'] == -100.
    assert report['aggregate']['combined_all_three']['pooled']['bb100'] > 0


def test_cannot_drop_the_incident_seed():
    with pytest.raises(ValueError, match='all three'):
        descriptive_report({1: rows(1.), 3: rows(1.)}, drift())


@pytest.mark.parametrize('fault', ['mean', 'difference', 'deck', 'nonfinite'])
def test_raw_terminal_arithmetic_fail_closed(fault):
    data = copy.deepcopy(rows(1.))
    if fault == 'mean':
        data[0]['treatment_minus_control_pair_mean_bb'] = 2.
    elif fault == 'difference':
        data[0]['treatment_minus_control_rewards_bb'][0] = 2.
    elif fault == 'deck':
        data[0]['deck'][0] = 1
    else:
        data[0]['control_rewards_bb'][0] = float('nan')
    with pytest.raises(ValueError):
        verify_raw_arithmetic(data)


def test_known_training_failure_is_not_a_blanket_integrity_bypass():
    validate_nontraining_integrity({'training_audit_passed': False, 'seed1_raw_hash': True})
    with pytest.raises(ValueError, match='unrelated'):
        validate_nontraining_integrity({'training_audit_passed': False, 'seed1_raw_hash': False})


def test_algebraically_equivalent_float_roundoff_is_allowed():
    data = rows(.1)
    data[0]['treatment_minus_control_pair_mean_bb'] += 1e-14
    verify_raw_arithmetic(data)


@pytest.mark.parametrize('field, boundary', [('mean_tv', .08), ('greedy_disagreement_rate', .12)])
def test_preregistered_below_drift_limit_is_strict(field, boundary):
    values = drift()
    values['1'][field] = boundary
    report = descriptive_report({seed: rows(1.) for seed in (1, 2, 3)}, values)
    assert not report['directional_gates_descriptive_only']['all_final_source_drift_below_limits']
