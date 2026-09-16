"""Terminal-only descriptive parent preservation and internal/external alignment.

Does not read current outcomes until BOTH exact controller and followthrough
identities are terminal. No new hands, model queries, logger writes or selection.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from scipy.stats import t
import review_completed as review

r = review.r
HERE, BASE, ROOT = Path(__file__).resolve().parent, review.BASE, review.ROOT
OLD = ROOT / 'research/experiments/v6-full-step-size-two-seed-external-fresh80k-20260906'
OLD_SHA = '505bedf2ef6847ad98db9640c3ea0b147f15dc31735f51a50306494313251be1'
PARENTS = {1: '8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef',
           3: 'f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2'}


def mean_variance(moment):
    n, total, squares = (moment[k] for k in ('hands', 'sum_chips', 'sum_squared_chips'))
    r.protocol.require(all(type(v) is int for v in (n, total, squares)) and n > 1,
                       'integer sufficient statistics required')
    r.protocol.require(abs(total) <= n * 20000 and 0 <= squares <= n * 20000 ** 2,
                       'outside physical200bb bounds')
    numerator = n * squares - total * total
    r.protocol.require(numerator >= 0, 'negative variance')
    return n, total / n, numerator / (n * (n - 1))


def moment_welch(treatment, control):
    nt, mt, vt = mean_variance(treatment)
    nc, mc, vc = mean_variance(control)
    at, ac = vt / nt, vc / nc
    se = math.sqrt(at + ac)
    df = (at + ac) ** 2 / (at ** 2 / (nt - 1) + ac ** 2 / (nc - 1)) if se else None
    half = float(t.ppf(.975, df)) * se if se else 0.0
    return {'bb_per_100': mt - mc, 'ci95': [mt - mc - half, mt - mc + half],
            'standard_error': se, 'degrees_of_freedom': df, 'empirical_zero_variance': se == 0,
            'exploratory_historical_not_contemporaneous': True, 'family_adjusted': False}


def terminal_guard():
    r.protocol.require(review.readiness()['ready'], 'fixed80k controller not terminal/ready')
    follow = r.read(HERE / 'followthrough_execution.json')
    r.protocol.require(follow['pid'] == 58116 and
        abs(follow['create_time'] - 1788709462.2370713) < .001,
        'unexpected followthrough identity')
    r.protocol.require(not r.live_identity(follow), 'followthrough still live; no outcome read')
    child = follow['review_child']
    r.protocol.require(follow['status'] == 'REVIEW_COMPLETE_NEEDS_RESEARCH_DECISION' and
        child and child['exit_code'] == 0 and not r.live_identity(child), 'review not complete')
    r.protocol.require(r.sha(BASE / 'post_terminal_review.json') == follow['review_sha256'],
                       'terminal review replaced')


def main():
    output = HERE / 'parent_transfer_comparison.json'
    r.protocol.require(not output.exists(), 'preserve earlier comparison')
    terminal_guard()
    qualification = r.read(HERE / 'parent_transfer_qualification.json')
    r.protocol.require(qualification['passed'], 'comparison tests not qualified')
    r.check_hashes(qualification['input_sha256'])
    current = r.read(BASE / 'post_terminal_review.json')
    r.protocol.require(current['passed'] and current['evaluation_hands'] == 80000 and
        current['final_qualification_hands'] == 0, 'wrong current review scope')
    old_path = OLD / 'post_terminal_review.json'
    r.protocol.require(r.sha(old_path) == OLD_SHA and
        r.read(OLD / 'experiment.json')['status'] == 'COMPLETED', 'historical external source changed')
    old = r.read(old_path)
    r.protocol.require(old['passed'] and old['evaluation_hands'] == 80000, 'historical source incomplete')
    r.check_hashes(current['input_sha256'])
    r.check_hashes(old['input_sha256'])
    old_spec, spec = r.read(OLD / 'launch_spec.json'), r.read(BASE / 'launch_spec.json')
    r.protocol.require(old_spec['runtime_sha256'] == spec['runtime_sha256'], 'execution runtime differs')
    r.protocol.require(r.read(OLD / 'environment.json')['packages'] ==
        r.read(BASE / 'environment.json')['packages'], 'package contract differs')
    r.protocol.require(r.sha(r.REPORT) == r.REPORT_SHA, 'internal endpoint report changed')
    internal = r.read(r.REPORT)
    rows = {}
    for seed in (1, 3):
        parent_arm = f'seed{seed}_full'
        parent_model = old_spec['models'][parent_arm]
        r.protocol.require(parent_model['sha256'] == PARENTS[seed] and
            internal['input_sha256'].get(parent_model['path']) == PARENTS[seed],
            'historical policy is not the original training parent')
        arms = {}
        for label in ('detached', 'connected'):
            arm = f'seed{seed}_{label}'
            endpoint = current['independent_integer_moments'][arm]
            r.protocol.require(endpoint['hands'] == 20000, 'wrong endpoint coverage')
            arms[label] = {'absolute_external_bb100': endpoint['bb_per_100'],
                'minus_historical_parent': moment_welch(endpoint, old['independent_integer_moments'][parent_arm]),
                'internal_minus_parent': internal['stages']['2'][str(seed)]['endpoint_minus_parent'][label]['pooled']}
        rows[str(seed)] = {'historical_parent': old['independent_integer_moments'][parent_arm],
            'endpoints': arms,
            'external_connected_minus_detached': current['statistics']['connected_minus_detached_by_seed'][str(seed)],
            'internal_connected_minus_detached': internal['stages']['2'][str(seed)]['connected_minus_detached']['pooled']}
    paths = [Path(__file__), BASE/'post_terminal_review.json', old_path, r.REPORT,
        HERE/'followthrough_execution.json', HERE/'naming_deviation_outcome_blind.md',
        BASE/'launch_spec.json', BASE/'session_commands.json', BASE/'preregistration.md',
        HERE/'parent_transfer_qualification.json', HERE/'parent_transfer_tests.xml']
    hashes = {str(path): r.sha(path) for path in paths}
    r.write_new(output, {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
        'command': sys.orig_argv, 'input_sha256': hashes, 'seeds': rows,
        'shared_parent_makes_two_endpoint_parent_contrasts_correlated': True,
        'historical_parent_cohort_not_time_matched_or_randomized': True,
        'same_frozen_runtime_and_package_contract': True,
        'naming_documentation_deviation_preserved': True,
        'interpretation': 'Exploratory preservation context only. Do not infer causality from separate historical cohorts, combine policies as one policy, or use nominal intervals as multiplicity-adjusted discovery.',
        'new_hands': 0, 'new_model_queries': 0, 'goal_achieved': False,
        'automatic_training_or_policy_selection': False})
    print(json.dumps({'passed': True, 'new_hands': 0, 'research_decision_required': True}))


if __name__ == '__main__':
    main()
