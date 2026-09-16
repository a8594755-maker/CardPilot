"""Terminal-only LR learning curves; reuse the qualified independent-deck math.

No new poker hands, early selection, linear extrapolation or live logger writes.
"""
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys

from review import BASE, PREVIOUS, live, read, require, sha

MATH_SOURCE = PREVIOUS / 'post_analysis/curve_comparison.py'
MATH_SHA = 'dbe4ae9ad29a542b1a9f6a9c21faa978f36d52793ddf963ce2be442cc18a733d'
require(sha(MATH_SOURCE) == MATH_SHA, 'qualified curve math changed')
spec = importlib.util.spec_from_file_location('qualified_previous_curve_math', MATH_SOURCE)
previous = importlib.util.module_from_spec(spec)
spec.loader.exec_module(previous)
independent_change, bucket_changes = previous.independent_change, previous.bucket_changes


def summarize(report):
    require(report['passed'] and report['all_recorded_processes_terminal'], 'terminal review incomplete')
    require(report['unique_new_evaluation_decks'] == 32768
            and report['accounting']['evaluation_hands'] == 262144,
            'need two verified disjoint evaluation stages')
    require(set(report['stages']) == {'1', '2'}
            and all(set(stage) == {'1', '3'} for stage in report['stages'].values()),
            'fixed stage/seed coverage incomplete')
    results = {}
    for seed in ('1', '3'):
        earlier, later = [report['stages'][stage][seed] for stage in ('1', '2')]
        for stage in (earlier, later):
            require(set(stage['endpoint_minus_parent']) == set(stage['absolute_vs_anchors']) == {'full', 'half'},
                    'wrong full-network LR arms')
        changes = {group: {arm: bucket_changes(earlier[group][arm], later[group][arm])
                          for arm in ('full', 'half')}
                   for group in ('endpoint_minus_parent', 'absolute_vs_anchors')}
        doses = {}
        for arm in ('full', 'half'):
            first, second = [report['training_health_and_realized_update_dose'][f'seed{seed}_{arm}_stage{stage}']
                             for stage in (1, 2)]
            expected_lr = 9.999999999999996e-05 * (.5 if arm == 'half' else 1.)
            require(first['actual_lr'] == second['actual_lr'] == expected_lr, 'LR contract changed')
            physical = second['cumulative_physical_hands'] - first['cumulative_physical_hands']
            require(physical == second['new_physical_hands_this_stage'] > 0, 'physical dose mismatch')
            doses[arm] = physical
        results[seed] = {
            'half_minus_full_change': bucket_changes(earlier['half_minus_full'], later['half_minus_full']),
            'endpoint_minus_original_parent_changes': changes['endpoint_minus_parent'],
            'absolute_vs_anchors_changes': changes['absolute_vs_anchors'],
            'physical_hands_between_endpoints': doses,
        }
    return results


def main(base=BASE):
    owner = read(base / 'ownership.json')
    require(not live(owner['pid'], owner['create_time']), 'controller still live')
    output = base / 'post_analysis/curve_comparison.json'
    require(not output.exists(), 'preserve prior curve comparison')
    path = base / 'post_terminal_review.json'
    digest, report = sha(path), read(path)
    results = summarize(report)
    hashes = {str(path): digest, str(Path(__file__)): sha(__file__), str(MATH_SOURCE): MATH_SHA}
    for name in ('review.py', 'test_review.py', 'review_tests.xml', 'test_curve_comparison.py', 'curve_tests.xml'):
        source = base / 'post_analysis' / name
        hashes[str(source)] = sha(source)
    # Do not rely on a terminal review after its underlying evaluation evidence changes.
    for name, expected in report['input_sha256'].items():
        if name.endswith(('common_deck_pairs.jsonl.gz', 'summary.json', 'stage1_analysis.json', 'stage2_analysis.json')):
            hashes[name] = expected
    require(all(sha(name) == expected for name, expected in hashes.items()), 'review/evidence changed')
    result = {
        'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
        'command': sys.orig_argv, 'seeds': results, 'input_sha256': hashes,
        'new_training_or_evaluation_hands': 0,
        'scope': 'Exploratory nominal conditional stage2-minus-stage1 differences on independent decks. '
                 'Training streams differ. Not seed-population inference, causal attribution, Slumbot strength, '
                 'multiplicity-adjusted confirmation, linear forecasting or proof of general improvement.',
        'automatic_promotion_or_qualification': False,
    }
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
