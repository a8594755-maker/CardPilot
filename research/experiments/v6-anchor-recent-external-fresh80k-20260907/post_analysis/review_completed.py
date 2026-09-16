"""Outcome-gated four-policy raw review; no requests, training, or policy selection."""
from datetime import datetime, timezone
from pathlib import Path
import argparse
import json
import math
import statistics
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
ROOT = BASE.parents[2]
sys.path.insert(0, str(BASE))
import run_pair as r

def readiness():
    execution = r.read(BASE / 'execution.json')
    if r.live_identity(execution):
        return {'ready': False, 'reason': 'exact controller owner live; outcomes not read'}
    if execution['status'] != 'COMPLETED_PENDING_REVIEW':
        return {'ready': False, 'reason': 'complete fixed-budget execution required'}
    if any(r.live_identity(row) for row in execution['children']):
        return {'ready': False, 'reason': 'child identity still live; outcomes not read'}
    r.protocol.require(len(execution['children']) == 41 and
        all(row['exit_code'] == 0 for row in execution['children']), 'incomplete successful jobs')
    r.protocol.require(execution['evaluation_hands'] == execution['slumbot_hands'] == 80000,
        'fixed80k incomplete')
    r.protocol.require(len(execution['waves']) == 4 and all(row['finished_at'] for row in execution['waves']),
        'wave completion missing')
    validate_execution_coverage(execution)
    return {'ready': True}


def validate_execution_coverage(execution):
    expected = {row['session_id'] for row in r.protocol.schedule()}
    expected |= {arm + suffix for arm in r.protocol.ARMS
                 for suffix in ('_combined_audit', '_independence_stdout')}
    expected.add('offline_prerun_tests')
    roles = [row['role'] for row in execution['children']]
    r.protocol.require(len(roles) == len(set(roles)) == 41 and set(roles) == expected,
                       'exact 32 clients, eight audits and one offline test required')
    r.protocol.require([row['wave'] for row in execution['waves']] == list(range(4)),
                       'four ordered fixed waves required')
    for item in r.protocol.schedule():
        child = next(row for row in execution['children'] if row['role'] == item['session_id'])
        expected_argv = [sys.executable, '-u', *r.protocol.session_command(item, BASE, BASE / 'runtime/scripts')]
        r.protocol.require(child['command'] == expected_argv and child['arm'] == item['arm'] and
                           child['wave'] == item['wave'] and child['session_index'] == item['index'],
                           'registered executed client command changed')


def integer_moments(values):
    r.protocol.require(len(values) > 1 and all(type(v) is int and abs(v) <= 20000 for v in values),
        'invalid terminal200bb chips')
    n, total, squares = len(values), sum(values), sum(v * v for v in values)
    mean = total / n
    variance = (n * squares - total * total) / (n * (n - 1))
    half = 1.96 * math.sqrt(variance / n)
    return {'hands': n, 'sum_chips': total, 'sum_squared_chips': squares, 'bb_per_100': mean,
        'variance_chips2': variance, 'raw_ci95': [mean - half, mean + half]}


def reviewed_groups(directory, inputs):
    """Raw payout/identity reaggregation tied to full decision-replay and journal hashes."""
    spec = r.read(directory / 'launch_spec.json')
    inputs[str(directory / 'launch_spec.json')] = r.sha(directory / 'launch_spec.json')
    groups, moments, total_replays = {}, {}, 0
    for arm in r.protocol.ARMS:
        audit_path = directory / f'{arm}_combined_audit.json'
        audit = r.read(audit_path)
        model = spec['models'][arm]['sha256']
        r.protocol.require(audit['status'] == 'PASS' and audit['model_sha256'] == model
            and audit['sessions'] == 8 and audit['successful_hands'] == 20000, 'full replay audit mismatch')
        inputs[str(audit_path)] = r.sha(audit_path)
        items = [item for item in spec['schedule'] if item['arm'] == arm]
        by_id = {row['session_id']: row for row in audit['results']}
        r.protocol.require(len(audit['results']) == len(by_id) == 8 and
            set(by_id) == {item['session_id'] for item in items}, 'audit identities mismatch')
        groups[arm] = []
        for item in items:
            verified = by_id[item['session_id']]
            session = directory / 'sessions' / arm / f's{item["index"]:02d}'
            r.protocol.require(Path(verified['directory']).resolve() == session.resolve(), 'audit path mismatch')
            r.protocol.require(verified['status'] == 'PASS' and verified['model_sha256'] == model
                and verified['policy_seed'] == item['policy_seed'], 'session replay identity mismatch')
            r.protocol.require(verified['successful_hands'] == verified['attempted_hands'] ==
                verified['target_hands'] == 2500, 'incomplete session')
            r.protocol.require(not any(verified[key] for key in ('pending_request_id', 'protocol_failures',
                'committed_without_raw', 'partial_journal', 'partial_hands')), 'unresolved session evidence')
            r.protocol.require(verified['decision_replays'] == verified['policy_draws_verified'] > 0,
                'missing decision replay')
            total_replays += verified['decision_replays']
            for name, key in (('hands.jsonl', 'hands_sha256'), ('journal.jsonl', 'journal_sha256')):
                path = session / name
                r.protocol.require(r.sha(path) == verified[key], 'audited raw/journal SHA changed')
                inputs[str(path)] = verified[key]
            values = []
            with (session / 'hands.jsonl').open(encoding='utf-8') as handle:
                for count, line in enumerate(handle, 1):
                    row = json.loads(line)
                    r.protocol.require(line.endswith('\n') and row['successful_hand'] == row['attempted_hand'] == count,
                        'raw counter mismatch')
                    r.protocol.require(row['session_id'] == item['session_id'] and row['policy_seed'] == item['policy_seed']
                        and row['model_sha256'] == model, 'raw identity mismatch')
                    r.protocol.require(row['policy_mode'] == 'greedy' and row['policy_temperature'] == 0
                        and row['strict_policy_execution'], 'execution changed')
                    r.protocol.require(row['terminal_validation']['status'] == 'PASS' and
                        row['winnings_bb'] == row['winnings_chips'] / 100, 'terminal payout invalid')
                    r.protocol.require(all(d['observation_bridge_contract'] == r.protocol.BRIDGE
                        for d in row['decisions']), 'bridge changed')
                    values.append(row['winnings_chips'])
            r.protocol.require(len(values) == 2500 and sum(values) == verified['cumulative_chips'], 'payout mismatch')
            groups[arm].append(values)
        moments[arm] = integer_moments([v for group in groups[arm] for v in group])
    return groups, moments, total_replays


def build_report():
    r.protocol.require(readiness()['ready'], 'not ready; do not inspect outcomes')
    manifest = r.read(BASE / 'input_manifest.json')
    r.check_hashes(manifest['input_sha256'])
    r.check_prior_prefixes(manifest['prior_raw_initial_sessions'])
    inputs = {str(path): r.sha(path) for path in (Path(__file__), BASE / 'execution.json',
        BASE / 'input_manifest.json', BASE / 'completed_analysis.json', BASE / 'launch_spec.json')}
    completed = r.read(BASE / 'completed_analysis.json')
    models = {arm: digest for arm, (_, digest) in r.EXPECTED_MODELS.items()}
    r.protocol.require(completed['models'] == r.read(BASE / 'launch_spec.json')['models']
        and not completed['goal_achieved'], 'completed model/goal mismatch')
    spec = r.read(BASE / 'launch_spec.json')
    r.protocol.require(spec['schedule'] == r.protocol.schedule() and
        spec['models'] == {arm: {'path': str(path), 'sha256': digest}
                         for arm, (path, digest) in r.EXPECTED_MODELS.items()},
        'preregistered final models or complete schedule substituted')
    r.protocol.require(completed['evaluation_hands'] == completed['slumbot_hands'] == 80000 and
        completed['new_training_hands'] == 0, 'completed accounting differs')
    qualification = r.read(HERE / 'qualification.json')
    r.protocol.require(qualification['passed'] and qualification['exit_code'] == 0,
                       'independent reviewer qualification incomplete')
    r.check_hashes(qualification['source_sha256'])
    r.protocol.require(r.sha(HERE / 'tests.xml') == qualification['xml_sha256'], 'reviewer tests changed')
    inputs[str(HERE / 'qualification.json')] = r.sha(HERE / 'qualification.json')
    inputs[str(HERE / 'tests.xml')] = qualification['xml_sha256']
    groups, moments, replays = reviewed_groups(BASE, inputs)
    alternate_groups, seats, streams = r.parse_raw(BASE, models)
    r.protocol.require(groups == alternate_groups, 'independent raw parsers differ')
    current_statistics = r.protocol.summarize_four(groups, evidence_valid=True)
    r.protocol.require(current_statistics == completed['statistics'], 'current raw statistics differ')
    r.protocol.require(r.seat_report(seats) == completed['seat_analysis']
        and streams == completed['cross_arm_visible_stream_audit'], 'seat/stream reaggregation differs')
    for arm in r.protocol.ARMS:
        saved = current_statistics['arms'][arm]
        r.protocol.require(moments[arm]['bb_per_100'] == saved['bb_per_100'] and
            all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(moments[arm]['raw_ci95'], saved['raw_hand_ci95'])),
            'independent integer moments differ')
        path = BASE / f'{arm}_independence_audit.json'
        audit = r.read(path)
        r.protocol.require(audit['status'] == 'PASS' and audit['hands'] == 20000 and audit['sessions'] == 8
            and audit['model_sha256'] == models[arm] and not audit['server_rng_independence_proven'],
            'independence audit failed')
        r.protocol.require(audit == completed['independence'][arm], 'independence report changed')
        inputs[str(path)] = r.sha(path)
    prior_tokens = {row['initial_token_sha256'] for row in manifest['prior_raw_initial_sessions']}
    for entry in manifest['prior_token_audits']:
        r.protocol.require(r.sha(Path(entry['path'])) == entry['sha256'], 'prior token audit changed')
        prior = r.read(Path(entry['path']))
        r.protocol.require(prior['status'] == 'PASS', 'prior token audit invalid')
        prior_tokens.update(value for row in prior['results'] for value in row['token_sha256'])
    r.protocol.require(len(prior_tokens) == manifest['prior_tokens'], 'prior token coverage changed')
    audits = {arm: r.read(BASE / f'{arm}_combined_audit.json') for arm in r.protocol.ARMS}
    cross = r.verify_audits(audits, models, prior_tokens)
    r.protocol.require(cross == completed['cross_arm_token_audit'], 'cross-arm/prior audit changed')
    r.check_hashes(inputs)
    r.check_hashes(manifest['input_sha256'])
    return {'schema': 'cardpilot.anchor_recent.four_policy_post_terminal_review.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'input_sha256': inputs,
        'frozen_input_hashes_rechecked': len(manifest['input_sha256']),
        'independent_integer_moments': moments, 'statistics': current_statistics,
        'seat_analysis': completed['seat_analysis'], 'cross_arm_token_audit': cross,
        'current_decision_replays': replays,
        'training_seed_population_inference': False,
        'current_review_command': [sys.executable, *sys.orig_argv[1:]],
        'execution_wall_seconds': r.read(BASE / 'execution.json')['wall_time_seconds'],
        'evaluation_hands': 80000, 'slumbot_hands': 80000, 'new_training_hands': 0,
        'analysis_added_hands': 0, 'final_qualification_hands': 0,
        'goal_achieved': False, 'research_decision_required': True}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-ready', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    if args.check_ready:
        print(json.dumps(readiness()))
    else:
        if args.out is None:
            parser.error('--out required')
        r.protocol.require(not args.out.exists(), 'preserve prior report')
        report = build_report()
        r.write_new(args.out, report)
        print(json.dumps({'passed': report['passed'], 'hands': 80000, 'analysis_added_hands': 0}))
