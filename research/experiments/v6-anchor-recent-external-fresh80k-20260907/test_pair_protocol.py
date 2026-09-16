"""Offline four-policy allocation and independent-hand/session statistical tests."""
import importlib.util
import math
from pathlib import Path

import pytest
from scipy.stats import ttest_ind

spec = importlib.util.spec_from_file_location('four_policy_stats_tests', Path(__file__).with_name('pair_protocol.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def groups(offset=0):
    return [[offset + (index - 4) * 10 + (hand % 2) * 200 - 100
             for hand in range(2500)] for index in range(8)]


def all_groups():
    return {arm: groups(10 if arm.endswith('recent') else 0) for arm in p.ARMS}


def test_schedule_32_unique_sessions_four_balanced_waves():
    plan = p.schedule()
    assert len(plan) == len({r['session_id'] for r in plan}) == len({r['policy_seed'] for r in plan}) == 32
    assert sum(r['hands'] for r in plan) == 80000
    assert [r['launch_index'] for r in plan] == list(range(32))
    assert p.PRIMARY_FAMILY_SIZE == 6
    for wave in range(4):
        rows = [r for r in plan if r['wave'] == wave]
        assert len(rows) == 8
        assert [r['arm'] for r in rows[:4]] == list(p.ARMS[wave:] + p.ARMS[:wave])
        assert [sum(r['arm'] == a for r in rows) for a in p.ARMS] == [2] * 4
    for arm in p.ARMS:
        rows = [r for r in plan if r['arm'] == arm]
        assert [r['index'] for r in rows] == list(range(1, 9))
        assert sum(r['hands'] for r in rows) == 20000
        assert all(r['session_id'] == f"v6_anchor_recent_external_20260907_{arm}_s{r['index']:02d}" for r in rows)
    # Each arm occupies each within-quartet launch position exactly twice.
    for arm in p.ARMS:
        assert [sum(r['arm'] == arm and r['launch_index'] % 4 == slot for r in plan)
                for slot in range(4)] == [2] * 4


def test_all_commands_are_frozen_cpu_greedy_bridge_with_disjoint_output():
    commands = [p.session_command(r, 'draft', 'runtime/scripts') for r in p.schedule()]
    assert len({c[c.index('--out-dir') + 1] for c in commands}) == 32
    for c in commands:
        for flag, value in [('--policy-mode', 'greedy'), ('--observation-bridge', 'legacy-v4'),
                            ('--hands', '2500'), ('--device', 'cpu')]:
            assert c[c.index(flag) + 1] == value


@pytest.mark.parametrize('field,value', [('hands', 5000), ('policy_seed', 1), ('session_id', 'wrong'), ('arm', 'best')])
def test_unregistered_session_refused(field, value):
    with pytest.raises(ValueError):
        p.session_command(p.schedule()[0] | {field: value}, 'draft', 'runtime')


def test_both_seed_contrasts_units_and_six_quantity_family():
    result = p.summarize_four(all_groups(), evidence_valid=True)
    assert len(result['primary_family']) == 6
    for seed in ('1', '3'):
        c = result['recent_minus_control_by_seed'][seed]
        assert c['independent_raw_hands']['ordinary']['bb_per_100'] == 10
        assert c['balanced_wave_sensitivity']['wave_differences_bb_per_100'] == [10] * 4
        assert c['balanced_wave_sensitivity']['t3']['degrees_of_freedom'] == 3
        assert c['balanced_wave_sensitivity']['not_paired_server_deals']
    for arm in p.ARMS:
        a = result['arms'][arm]
        assert a['hands'] == 20000 and a['sessions'] == 8
        assert a['session_t7']['degrees_of_freedom'] == 7
    assert result['development_hands'] == 80000 and result['final_qualification_hands'] == 0
    assert result['automatic_model_selection'] is result['goal_achieved'] is False
    assert result['training_seed_population_inference'] is False


def test_welch_matches_scipy_unequal_variance():
    treatment, control = [4, 8, 10, 14, 90], [-2, 1, 3, 8, 9, 15, 20]
    expected = ttest_ind(treatment, control, equal_var=False).confidence_interval()
    actual = p.welch(treatment, control)
    assert math.isclose(actual['ci'][0], expected.low, rel_tol=1e-12)
    assert math.isclose(actual['ci'][1], expected.high, rel_tol=1e-12)


def test_family_adjustment_widens_all_primary_intervals():
    result = p.summarize_four(all_groups(), evidence_valid=True)
    for a in result['arms'].values():
        assert a['raw_hand_ci_family_adjusted'][0] < a['raw_hand_ci95'][0]
        assert a['raw_hand_ci_family_adjusted'][1] > a['raw_hand_ci95'][1]
    for c in result['recent_minus_control_by_seed'].values():
        for unit in ('independent_raw_hands', 'independent_sessions'):
            assert c[unit]['family_adjusted']['ci'][0] < c[unit]['ordinary']['ci'][0]
            assert c[unit]['family_adjusted']['ci'][1] > c[unit]['ordinary']['ci'][1]


@pytest.mark.parametrize('case', ['incomplete', 'extra', 'old16', 'float', 'boolean', 'over_stack', 'nan'])
def test_invalid_hand_or_old_coverage_rejected(case):
    sample = groups()
    if case == 'incomplete': sample[-1].pop()
    elif case == 'extra': sample.append(sample[0])
    elif case == 'old16': sample = sample * 2
    else: sample[0][0] = {'float': 1.0, 'boolean': True, 'over_stack': 20001, 'nan': float('nan')}[case]
    with pytest.raises(ValueError):
        p.arm_summary(sample)


@pytest.mark.parametrize('evidence', [False, None, 1])
def test_no_statistics_without_explicit_audit_pass(evidence):
    with pytest.raises(ValueError):
        p.summarize_four(all_groups(), evidence_valid=evidence)


@pytest.mark.parametrize('arm', p.ARMS)
def test_no_selection_by_omitting_any_policy(arm):
    sample = all_groups()
    sample.pop(arm)
    with pytest.raises(ValueError):
        p.summarize_four(sample, evidence_valid=True)


def test_empirical_zero_variance_is_labeled_not_final_success():
    sample = {arm: [[100] * 2500 for _ in range(8)] for arm in p.ARMS}
    result = p.summarize_four(sample, evidence_valid=True)
    assert all(a['empirical_zero_raw_variance'] for a in result['arms'].values())
    assert result['automatic_final_test_authorized'] is result['goal_achieved'] is False
