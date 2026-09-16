"""Fail-closed observation/decision equality checks, no model or network."""
import math
import numpy as np


def assert_parity(first_obs, first_table, second_obs, second_table, first_decision, second_decision):
    for key in ['card_info', 'action_info', 'extra_info', 'legal_mask']:
        left, right = np.asarray(first_obs[key]), np.asarray(second_obs[key])
        if not np.isfinite(left).all() or not np.isfinite(right).all() or not np.array_equal(left, right):
            raise ValueError('Observation mismatch: '+key)
    if first_obs['player'] != second_obs['player'] or first_table != second_table:
        raise ValueError('Seat/action table mismatch')
    if first_decision != second_decision: raise ValueError('Full inference mismatch')
    increment, info = first_decision
    probs = info['behavior_probs']
    mask = first_obs['legal_mask']
    if len(probs) != 9 or not all(math.isfinite(p) and p >= 0 for p in probs):
        raise ValueError('Invalid probabilities')
    if not math.isclose(math.fsum(probs), 1., rel_tol=0, abs_tol=1e-12):
        raise ValueError('Unnormalized probabilities')
    if any(p != 0 for p, m in zip(probs, mask) if not m): raise ValueError('Illegal action probability')
    selected = info['selected_action_slot']
    if type(selected) is not int or selected not in range(9) or not mask[selected]:
        raise ValueError('Illegal selected action')
    if increment != first_table[selected] or increment != info['direct_increment']:
        raise ValueError('Action increment mismatch')
    if info['behavior_action_probability'] != probs[selected]: raise ValueError('Selected probability mismatch')
    if info['policy_mode'] != 'sample' or info['temperature'] != 1.: raise ValueError('Policy mode mismatch')


def assert_coverage(counts):
    if set(counts) != {f'street{s}_seat{p}' for s in range(4) for p in range(2)} or any(v <= 0 for v in counts.values()):
        raise ValueError('Missing street/seat stratum')
