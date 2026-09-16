"""Exploratory fixed1M versus2M retained external cohorts; zero new poker."""
from datetime import datetime, timezone
from pathlib import Path
import sys
import review_completed as review

r = review.r
BASE, ROOT, HERE = review.BASE, review.ROOT, review.HERE
OLD = ROOT / 'research/experiments/v6-preflop-actor-route-two-seed-external-fresh80k-20260906'

def main():
    out = HERE / 'cross_dose_comparison.json'
    r.protocol.require(not out.exists(), 'preserve prior analysis')
    r.protocol.require(review.readiness()['ready'], 'execution incomplete')
    follow = r.read(HERE / 'followthrough_execution.json')
    r.protocol.require(not r.live_identity(follow) and not r.live_identity(follow['review_child']) and
        follow['review_child']['exit_code'] == 0, 'helper not terminal')
    paths = [OLD / 'post_terminal_review.json', BASE / 'post_terminal_review.json']
    expected = ['e847cc5d8c7e73f535733c16b14ded69605bfc0f8873506ecfeb38e1d4424d46',
                '3a42d5da8efce1926dbf100a4132af4639ebab591939b5e2d9ee85c4b4ea6fc5']
    inputs = {str(p): h for p,h in zip(paths, expected)}
    r.check_hashes(inputs)
    reports = [r.read(p) for p in paths]
    groups = []
    for directory, report in zip((OLD, BASE), reports):
        r.protocol.require(report['passed'] and report['evaluation_hands'] == 80000, 'invalid report')
        r.check_hashes(report['input_sha256'])
        raw, moments, replay_count = review.reviewed_groups(directory, inputs)
        r.protocol.require(replay_count == report['current_decision_replays'] and
            moments == report['independent_integer_moments'], 'retained raw evidence changed')
        groups.append(raw)
    specifications = [r.read(d / 'launch_spec.json') for d in (OLD, BASE)]
    r.protocol.require(specifications[0]['runtime_sha256'] == specifications[1]['runtime_sha256'], 'different execution runtime')
    r.protocol.require(not {x['session_id'] for x in specifications[0]['schedule']} &
        {x['session_id'] for x in specifications[1]['schedule']}, 'reused cohort IDs')
    result = {}
    for arm in r.protocol.ARMS:
        old, new = [g[arm] for g in groups]
        result[arm] = {
            'independent_raw_hands': r.protocol.welch([v for g in new for v in g], [v for g in old for v in g]),
            'independent_session_means': r.protocol.welch([sum(g)/len(g) for g in new], [sum(g)/len(g) for g in old]),
            'earlier_bb100': reports[0]['statistics']['arms'][arm]['bb_per_100'],
            'later_bb100': reports[1]['statistics']['arms'][arm]['bb_per_100'],
            'seat_point_changes': {seat: reports[1]['seat_analysis']['by_arm'][arm][seat]['bb_per_100'] -
                reports[0]['seat_analysis']['by_arm'][arm][seat]['bb_per_100'] for seat in ('0','1')}}
    inputs[str(Path(__file__))] = r.sha(__file__)
    inputs[str(HERE / 'review_completed.py')] = r.sha(HERE / 'review_completed.py')
    inputs[str(BASE / 'pair_protocol.py')] = r.sha(BASE / 'pair_protocol.py')
    r.check_hashes(inputs)
    r.write_new(out, {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
        'command': sys.orig_argv, 'input_sha256': inputs, 'changes_2m_minus_1m': result,
        'new_hands': 0, 'scope': 'Exploratory ordinary95 independent-cohort Welch intervals; no paired server deals, causal attribution, multiplicity correction or seed-population claim.',
        'automatic_scale_or_promotion': False})
    print({arm: row['independent_raw_hands'] for arm,row in result.items()})

if __name__ == '__main__':
    main()
