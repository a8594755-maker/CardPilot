"""Retained own-parent external curves and measured allocation costs; no new poker."""
from pathlib import Path
import importlib.util
import json
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EXPS = ROOT / 'research/experiments'
CURRENT = EXPS / 'v6-anchor-recent-external-fresh80k-20260907'
PARENT = EXPS / 'v6-preflop-actor-route-2m-external-fresh80k-20260907'
sys.path.insert(0, str(CURRENT / 'post_analysis'))
import review_completed as review
r = review.r

def main():
    start = time.monotonic()
    out = HERE / 'analysis.json'
    r.protocol.require(not out.exists(), 'preserve prior result')
    r.protocol.require(review.readiness()['ready'], 'live/incomplete current execution')
    sources = {}
    reports, groups, specs = {}, {}, {}
    for label, directory in [('parent', PARENT), ('current', CURRENT)]:
        record = r.read(directory / 'experiment.json')
        report = r.read(directory / 'post_terminal_review.json')
        r.protocol.require(record['status'] == 'COMPLETED' and report['passed'], 'unreviewed endpoint')
        r.check_hashes(report['input_sha256'])
        spec = r.read(directory / 'launch_spec.json')
        specs[label], reports[label] = spec, report
        for path in [directory / 'post_terminal_review.json', directory / 'launch_spec.json']:
            sources[str(path)] = r.sha(path)
        groups[label] = {}
        for arm in spec['models']:
            sessions = []
            for item in [x for x in spec['schedule'] if x['arm'] == arm]:
                path = directory / 'sessions' / arm / f"s{item['index']:02d}" / 'hands.jsonl'
                rows = [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]
                r.protocol.require(len(rows) == 2500 and all(x['session_id'] == item['session_id'] and
                    x['model_sha256'] == spec['models'][arm]['sha256'] for x in rows), 'raw identity/count')
                sources[str(path)] = r.sha(path)
                sessions.append([x['winnings_chips'] for x in rows])
            measured = review.integer_moments([v for s in sessions for v in s])
            r.protocol.require(measured == report['independent_integer_moments'][arm], 'raw moments differ')
            groups[label][arm] = sessions
    r.protocol.require(specs['parent']['runtime_sha256'] == specs['current']['runtime_sha256'], 'runtime mismatch')
    r.protocol.require(not {x['session_id'] for x in specs['parent']['schedule']} &
        {x['session_id'] for x in specs['current']['schedule']}, 'cohort reuse')
    changes = {}
    for arm, sessions in groups['current'].items():
        parent_arm = arm.split('_')[0] + '_connected'
        prior = groups['parent'][parent_arm]
        changes[arm] = {'parent_arm': parent_arm,
            'raw_welch': r.protocol.welch([v for s in sessions for v in s], [v for s in prior for v in s]),
            'session_welch': r.protocol.welch([sum(s)/len(s) for s in sessions], [sum(s)/len(s) for s in prior]),
            'parent_bb100': reports['parent']['statistics']['arms'][parent_arm]['bb_per_100'],
            'current_bb100': reports['current']['statistics']['arms'][arm]['bb_per_100']}
    costs = {}
    for name in ['v6-preflop-actor-route-2m-continuation-20260906', 'v6-anchor-recent-two-seed-geometric-20260907']:
        path = EXPS / name / 'experiment.json'
        record = r.read(path)
        sources[str(path)] = r.sha(path)
        costs[name] = {'accounting': record['accounting'], 'metrics': record['metrics']}
    sources[str(Path(__file__))] = r.sha(Path(__file__))
    r.check_hashes(sources)
    r.write_new(out, {'passed': True, 'command': sys.orig_argv, 'input_sha256': sources,
        'own_parent_changes': changes, 'retained_costs': costs, 'analysis_wall_seconds': time.monotonic()-start,
        'new_training_hands': 0, 'new_evaluation_hands': 0, 'new_slumbot_hands': 0,
        'limitations': 'Exploratory unadjusted95 Welch independent-cohort comparisons; shared parents make contrasts dependent. No server-deal pairing, causal attribution, or seed-population inference. Cost records distinguish active training and idle/controller wall.',
        'goal_achieved': False})
    print(json.dumps(changes))

if __name__ == '__main__':
    main()
