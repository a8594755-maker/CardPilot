"""Offline draft schedule/statistics, with no network, subprocess or model loads."""
import importlib.util
import math
from pathlib import Path

import pytest
from scipy.stats import ttest_ind

spec = importlib.util.spec_from_file_location('phase_external_draft', Path(__file__).with_name('pair_protocol.py'))
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


def groups(offset=0):
    return [[offset + (index - 8) * 10 + (hand % 2) * 200 - 100 for hand in range(2500)] for index in range(16)]


def test_schedule_complete_balanced_unique_and_order_reversed():
    plan = p.schedule()
    assert len(plan) == len({row['session_id'] for row in plan}) == len({row['policy_seed'] for row in plan}) == 32
    assert sum(row['hands'] for row in plan) == 80000
    for wave in range(4):
        selected = [row for row in plan if row['wave'] == wave]
        assert len(selected) == 8
        assert selected[0]['arm'] == ('static' if wave % 2 == 0 else 'moving256')
        assert [sum(row['arm'] == arm for row in selected) for arm in p.ARMS] == [4, 4]
    for arm in p.ARMS:
        assert [r['index'] for r in plan if r['arm'] == arm] == list(range(1, 17))


def test_all_commands_use_greedy_bridge_and_disjoint_outputs():
    commands = [p.session_command(row, 'draft', 'runtime/scripts') for row in p.schedule()]
    assert len({cmd[cmd.index('--out-dir') + 1] for cmd in commands}) == 32
    for cmd in commands:
        assert cmd[cmd.index('--policy-mode') + 1] == 'greedy'
        assert cmd[cmd.index('--observation-bridge') + 1] == 'legacy-v4'
        assert cmd[cmd.index('--hands') + 1] == '2500'
        assert cmd[cmd.index('--device') + 1] == 'cpu'


def test_unregistered_session_refused():
    row = p.schedule()[0] | {'hands': 5000}
    with pytest.raises(ValueError):
        p.session_command(row, 'draft', 'runtime')


def test_known_effect_accounting_and_no_promotion():
    result = p.summarize_pair({'static': groups(), 'moving256': groups(10)}, evidence_valid=True)
    assert result['moving_minus_static']['independent_raw_hands']['ordinary']['bb_per_100'] == 10
    assert result['moving_minus_static']['balanced_wave_sensitivity']['wave_differences_bb_per_100'] == [10] * 4
    assert all(result['arms'][arm]['hands'] == 40000 for arm in p.ARMS)
    assert result['development_hands'] == 80000 and result['final_qualification_hands'] == 0
    assert result['automatic_model_selection'] is result['goal_achieved'] is False
    assert result['arms']['static']['session_t15']['degrees_of_freedom'] == 15


def test_welch_matches_scipy_with_unequal_variance():
    treatment, control = [4, 8, 10, 14, 90], [-2, 1, 3, 8, 9, 15, 20]
    expected = ttest_ind(treatment, control, equal_var=False).confidence_interval()
    actual = p.welch(treatment, control)
    assert math.isclose(actual['ci'][0], expected.low, rel_tol=1e-12)
    assert math.isclose(actual['ci'][1], expected.high, rel_tol=1e-12)


def test_family_adjustment_widens_intervals():
    result = p.summarize_pair({'static': groups(), 'moving256': groups(10)}, evidence_valid=True)
    contrast = result['moving_minus_static']['independent_sessions']
    assert contrast['family_adjusted']['ci'][0] < contrast['ordinary']['ci'][0]
    assert contrast['family_adjusted']['ci'][1] > contrast['ordinary']['ci'][1]


@pytest.mark.parametrize('case', ['incomplete', 'extra', 'float', 'boolean', 'over_stack', 'nan'])
def test_invalid_hands_rejected(case):
    sample = groups()
    if case == 'incomplete':
        sample[-1].pop()
    elif case == 'extra':
        sample.append(sample[0])
    else:
        sample[0][0] = {'float': 1.0, 'boolean': True, 'over_stack': 20001, 'nan': float('nan')}[case]
    with pytest.raises(ValueError):
        p.arm_summary(sample)


@pytest.mark.parametrize('evidence', [False, None, 1])
def test_no_statistics_without_explicit_audit_pass(evidence):
    with pytest.raises(ValueError):
        p.summarize_pair({'static': groups(), 'moving256': groups(10)}, evidence_valid=evidence)


def test_empirical_zero_variance_is_labeled_not_final_success():
    sample = [[100] * 2500 for _ in range(16)]
    result = p.summarize_pair({'static': sample, 'moving256': sample}, evidence_valid=True)
    assert result['arms']['static']['empirical_zero_raw_variance']
    assert result['moving_minus_static']['independent_sessions']['ordinary']['empirical_zero_variance']
    assert result['automatic_final_test_authorized'] is result['goal_achieved'] is False
