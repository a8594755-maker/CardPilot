"""Conditional stage2-minus-stage1 changes on independent evaluation decks.

This is post-analysis, not a new training or evaluation experiment. No extrapolated
learning rate, automatic promotion, multiplicity-adjusted claim or seed-population CI.
"""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import sys

from review import BASE, live, read, require, sha


def independent_change(earlier, later):
    for row in (earlier, later):
        require(all(math.isfinite(row[k]) for k in ('bb100', 'se_bb100')) and
                row['se_bb100'] >= 0 and row['paired_decks'] >= 2, 'invalid stage statistics')
    point = later['bb100'] - earlier['bb100']
    se = math.hypot(earlier['se_bb100'], later['se_bb100'])
    return {'bb100': point, 'se_bb100': se, 'ci95': [point - 1.96 * se, point + 1.96 * se],
            'earlier_paired_decks': earlier['paired_decks'], 'later_paired_decks': later['paired_decks']}


def bucket_changes(earlier, later):
    result = {'pooled': independent_change(earlier['pooled'], later['pooled'])}
    for group in ('by_anchor', 'by_seat'):
        require(earlier[group].keys() == later[group].keys(), 'stage bucket mismatch')
        result[group] = {key: independent_change(earlier[group][key], later[group][key]) for key in earlier[group]}
    return result


def main():
    owner = read(BASE / 'ownership.json')
    require(not live(owner['pid'], owner['create_time']), 'controller still live')
    path = BASE / 'post_terminal_review.json'
    report = read(path)
    require(report['passed'] and report['all_recorded_processes_terminal'], 'terminal review incomplete')
    require(report['unique_new_evaluation_decks'] == 32768 and report['accounting']['evaluation_hands'] == 262144,
            'need both independently verified disjoint stages')
    require(set(report['stages']) == {'1', '2'}, 'missing stage')
    require(all(set(s) == {'1', '3'} for s in report['stages'].values()), 'missing fixed training seed')
    hashes = {str(path): sha(path), str(Path(__file__)): sha(__file__),
              str(Path(__file__).with_name('review.py')): sha(Path(__file__).with_name('review.py'))}
    results = {}
    for seed in ('1', '3'):
        earlier, later = report['stages']['1'][seed], report['stages']['2'][seed]
        arms = {arm: bucket_changes(earlier['endpoint_minus_parent'][arm], later['endpoint_minus_parent'][arm])
                for arm in ('full', 'heads')}
        doses = {}
        for arm in ('full', 'heads'):
            previous, current = [report['training_health_and_realized_update_dose'][f'seed{seed}_{arm}_stage{stage}'] for stage in (1, 2)]
            doses[arm] = current['cumulative_physical_hands'] - previous['cumulative_physical_hands']
            require(doses[arm] == current['new_physical_hands_this_stage'] > 0, 'stage training dose mismatch')
        results[seed] = {'full_minus_heads_change': bucket_changes(earlier['full_minus_heads'], later['full_minus_heads']),
                         'endpoint_minus_original_parent_changes': arms, 'physical_hands_between_endpoints': doses}
    output = BASE / 'post_analysis/curve_comparison.json'
    require(not output.exists(), 'preserve prior curve comparison')
    require(sha(path) == hashes[str(path)], 'terminal review changed')
    result = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
              'command': [sys.executable, '-B', str(Path(__file__).resolve())], 'seeds': results,
              'input_sha256': hashes, 'new_training_or_evaluation_hands': 0,
              'scope': 'Exploratory nominal conditional fixed-checkpoint stage changes on independent decks; not training-seed population, Slumbot strength, causal attribution or linear extrapolation.',
              'automatic_promotion_or_qualification': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(result, handle, indent=2, allow_nan=False)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
