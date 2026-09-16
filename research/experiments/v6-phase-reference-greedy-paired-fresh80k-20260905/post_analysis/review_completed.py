"""Post-terminal independent accounting and historical-context review; no poker."""
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
PREP = ROOT / 'research/experiments/v6-phase-held-reference-control-20260904/recovery_20260905/external_preparation'
sys.path.insert(0, str(PREP))
import run_pair as r

HISTORICAL = {
    'original4M': ('v6-static-seed1-4m-greedy-fresh20k-slumbot-20260904',
        '7ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f'),
    'standard10_same_contract': ('v6-standard10-legacy-bridge-greedy-fresh20k-20260901',
        '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'),
}


def readiness():
    execution = r.read(BASE / 'execution.json')
    if r.live_identity(execution):
        return {'ready': False, 'reason': 'exact controller owner live; outcomes not read'}
    if execution['status'] != 'COMPLETED_PENDING_REVIEW':
        return {'ready': False, 'reason': 'complete fixed-budget execution required'}
    if any(r.live_identity(row) for row in execution['children']):
        return {'ready': False, 'reason': 'child identity still live'}
    r.protocol.require(len(execution['children']) == 37 and
        all(row['exit_code'] == 0 for row in execution['children']), 'incomplete successful jobs')
    r.protocol.require(execution['evaluation_hands'] == execution['slumbot_hands'] == 80000,
        'fixed80k incomplete')
    r.protocol.require(len(execution['waves']) == 4 and all(row['finished_at'] for row in execution['waves']),
        'wave completion missing')
    return {'ready': True}


def integer_moments(values):
    r.protocol.require(len(values) > 1 and all(type(v) is int and abs(v) <= 20000 for v in values),
        'invalid terminal200bb chips')
    n, total, squares = len(values), sum(values), sum(v * v for v in values)
    mean = total / n
    variance = (n * squares - total * total) / (n * (n - 1))
    half = 1.96 * math.sqrt(variance / n)
    return {'hands': n, 'sum_chips': total, 'sum_squared_chips': squares, 'bb_per_100': mean,
        'variance_chips2': variance, 'raw_ci95': [mean - half, mean + half]}


def historical_groups(name, model_sha, inputs):
    directory = ROOT / 'research/experiments' / name
    audit_path = directory / 'combined_audit.json'
    audit = r.read(audit_path)
    r.protocol.require(audit['status'] == 'PASS' and audit['sessions'] == 8 and
        audit['successful_hands'] == 20000 and audit['model_sha256'] == model_sha, 'historical audit mismatch')
    inputs[str(audit_path)] = r.sha(audit_path)
    by_directory = {Path(row['directory']).resolve(): row for row in audit['results']}
    groups = []
    for index in range(1, 9):
        session = directory / 'sessions' / f's{index:02d}'
        verified = by_directory[session.resolve()]
        path = session / 'hands.jsonl'
        r.protocol.require(r.sha(path) == verified['hands_sha256'], 'historical raw SHA changed')
        inputs[str(path)] = verified['hands_sha256']
        values = []
        with path.open(encoding='utf-8') as handle:
            for count, line in enumerate(handle, 1):
                row = json.loads(line)
                r.protocol.require(line.endswith('\n') and row['successful_hand'] == row['attempted_hand'] == count,
                    'historical hand counters changed')
                r.protocol.require(row['model_sha256'] == model_sha and row['session_id'] == verified['session_id']
                    and row['policy_mode'] == 'greedy' and row['policy_temperature'] == 0, 'historical policy changed')
                r.protocol.require(all(d['observation_bridge_contract'] == r.protocol.BRIDGE for d in row['decisions']),
                    'historical bridge differs')
                values.append(row['winnings_chips'])
        r.protocol.require(len(values) == 2500 and sum(values) == verified['cumulative_chips'], 'historical payout mismatch')
        groups.append(values)
    return groups


def build_report():
    r.protocol.require(readiness()['ready'], 'not ready; do not inspect outcomes')
    manifest = r.read(BASE / 'input_manifest.json')
    r.check_hashes(manifest['input_sha256'])
    r.check_prior_prefixes(manifest['prior_raw_initial_sessions'])
    completed = r.read(BASE / 'completed_analysis.json')
    models = {arm: digest for arm, (_, digest) in r.EXPECTED_MODELS.items()}
    r.protocol.require(completed['models'] == r.read(BASE / 'launch_spec.json')['models'] and
        not completed['goal_achieved'], 'completed report policy/goal mismatch')
    groups, seats, streams = r.parse_raw(BASE, models)
    r.protocol.require(r.protocol.summarize_pair(groups, evidence_valid=True) == completed['statistics'],
        'raw statistics differ from controller report')
    r.protocol.require(r.seat_report(seats) == completed['seat_analysis'] and
        streams == completed['cross_arm_visible_stream_audit'], 'seat/stream reaggregation differs')
    inputs = {str(path): r.sha(path) for path in (Path(__file__), BASE / 'execution.json',
        BASE / 'input_manifest.json', BASE / 'completed_analysis.json', BASE / 'launch_spec.json')}
    moments, contextual = {}, {}
    for arm in r.protocol.ARMS:
        moments[arm] = integer_moments([v for group in groups[arm] for v in group])
        saved = completed['statistics']['arms'][arm]
        r.protocol.require(moments[arm]['bb_per_100'] == saved['bb_per_100'] and
            all(math.isclose(a, b, abs_tol=1e-9) for a, b in zip(moments[arm]['raw_ci95'], saved['raw_hand_ci95'])),
            'independent integer-moment statistics disagree')
        audit_path = BASE / f'{arm}_combined_audit.json'
        audit = r.read(audit_path)
        inputs[str(audit_path)] = r.sha(audit_path)
        r.protocol.require(audit['status'] == 'PASS' and audit['model_sha256'] == models[arm], 'full replay audit failed')
        for row in audit['results']:
            path = Path(row['directory']) / 'hands.jsonl'
            r.protocol.require(r.sha(path) == row['hands_sha256'], 'current replay/raw SHA changed')
            inputs[str(path)] = row['hands_sha256']
    for label, (directory, model) in HISTORICAL.items():
        old = historical_groups(directory, model, inputs)
        old_raw = [v for group in old for v in group]
        contextual[label] = {'reference': integer_moments(old_raw), 'reference_model_sha256': model,
            'temporally_confounded_not_randomized_control': True, 'descriptive_not_primary_family': True,
            'by_arm': {arm: {'raw_welch': r.protocol.welch([v for group in groups[arm] for v in group], old_raw),
                'session_welch': r.protocol.welch([statistics.mean(group) for group in groups[arm]],
                    [statistics.mean(group) for group in old])} for arm in r.protocol.ARMS}}
    r.check_hashes(inputs)
    return {'schema': 'cardpilot.phase_reference.external_post_terminal_review.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'input_sha256': inputs,
        'independent_integer_moments': moments, 'statistics': completed['statistics'],
        'historical_context': contextual, 'execution_wall_seconds': r.read(BASE / 'execution.json')['wall_time_seconds'],
        'evaluation_hands': 80000, 'slumbot_hands': 80000, 'analysis_added_hands': 0,
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
