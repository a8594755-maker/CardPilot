"""Pure evidence/paired statistics contract for the fixed final assessment."""
import math
import statistics
import numpy as np


def parent_gate(record, review):
    return (record.get('status') == 'COMPLETED' and review.get('status') == 'PASS'
            and review.get('decision') == 'ADMIT_SEPARATE_AVERAGE_ASSESSMENT'
            and review.get('epochs') == 4 and review.get('optimizer_steps') == 1024
            and review.get('new_training_hands') == 262144
            and review.get('supervised_validation_hands') == 8192
            and review.get('slumbot_hands') == 0 and review.get('goal_achieved') is False)


def estimate(values, family=1):
    if type(family) is not int or family < 1 or len(values) < 2 or not all(math.isfinite(x) for x in values):
        raise ValueError('Invalid independent-pair values')
    mean, se = statistics.mean(values), statistics.stdev(values)/math.sqrt(len(values))
    z = statistics.NormalDist().inv_cdf(1-.05/(2*family))
    return dict(bb_per_100=mean, standard_error=se, ci95=[mean-1.96*se, mean+1.96*se],
                **{f'family{family}_ci95': [mean-z*se, mean+z*se]})


def paired_difference(student, source, family=1):
    if len(student) != len(source):
        raise ValueError('Different pair counts')
    values = []
    for a, b in zip(student, source):
        if a['pair_index'] != b['pair_index'] or a['deck'] != b['deck']:
            raise ValueError('Unmatched paired deals')
        for row in (a, b):
            if len(row['rewards_bb']) != 2 or not all(math.isfinite(x) and abs(x) <= 200 for x in row['rewards_bb']):
                raise ValueError('Invalid reward')
        values.append((sum(a['rewards_bb'])-sum(b['rewards_bb']))*50)
    return estimate(values, family)


def assert_parity(first_obs, first_table, second_obs, second_table, first_decision, second_decision):
    for key in ('card_info', 'action_info', 'extra_info', 'legal_mask'):
        left, right = np.asarray(first_obs[key]), np.asarray(second_obs[key])
        if not np.isfinite(left).all() or not np.isfinite(right).all() or not np.array_equal(left, right):
            raise ValueError('Observation mismatch: '+key)
    if first_obs['player'] != second_obs['player'] or first_table != second_table:
        raise ValueError('Seat/action table mismatch')
    if first_decision != second_decision:
        raise ValueError('Full inference mismatch')
    increment, info = first_decision
    probs, mask = info['behavior_probs'], first_obs['legal_mask']
    if len(probs) != 9 or not all(math.isfinite(p) and p >= 0 for p in probs):
        raise ValueError('Invalid probabilities')
    if not math.isclose(math.fsum(probs), 1., rel_tol=0, abs_tol=1e-12):
        raise ValueError('Unnormalized probabilities')
    if any(p != 0 for p, m in zip(probs, mask) if not m):
        raise ValueError('Illegal action probability')
    selected = info['selected_action_slot']
    if type(selected) is not int or selected not in range(9) or not mask[selected]:
        raise ValueError('Illegal selected action')
    if increment != first_table[selected] or increment != info['direct_increment']:
        raise ValueError('Action increment mismatch')
    if info['behavior_action_probability'] != probs[selected]:
        raise ValueError('Selected probability mismatch')
    if info['policy_mode'] != 'sample' or info['temperature'] != 1.:
        raise ValueError('Policy mode mismatch')


def strategic_profile(values):
    opponents = ('prior', 'response', 'anchor0', 'anchor1', 'anchor2', 'anchor3', 'anchor4')
    required = {(c, a) for c in ('prior','response','student') for a in opponents}
    if set(values) != required or len({len(v) for v in values.values()}) != 1:
        raise ValueError('Incomplete or unequal fixed21cell matrix')
    if any(not math.isfinite(x) or abs(x) > 20000 for v in values.values() for x in v):
        raise ValueError('Invalid absolute pair payoff')
    n = len(values['prior','prior'])
    primary = {
        'hedge_against_response': estimate([values['student','response'][i]-values['prior','response'][i] for i in range(n)], 2),
        'retain_anchor1_2_vs_response': estimate([
            sum(values['student',a][i]-values['response',a][i] for a in ('anchor1','anchor2'))/2 for i in range(n)], 2),
    }
    calibration = {a: estimate([values['student',a][i]-
        .5*(values['prior',a][i]+values['response',a][i]) for i in range(n)], 7) for a in opponents}
    decision = ('ADMIT_NEXT_RESPONSE_PHASE' if all(r['family2_ci95'][0] > 0 for r in primary.values())
                else 'AVERAGE_STRATEGIC_GATE_NOT_PASSED')
    return dict(primary_contrasts=primary, student_minus_episode_mixture=calibration, decision=decision)
