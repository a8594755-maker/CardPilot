"""Outcome-gated Seed3 raw review and fixed-two-lineage synthesis; no poker."""
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

PRIOR = ROOT / 'research/experiments/v6-phase-reference-greedy-paired-fresh80k-20260905'
PRIOR_REVIEW_SHA = '0ca3eff30cd967690d6099f2e7a36e4095a822953b6a1236c32800c53dd54d05'
PRIOR_SPEC_SHA = '5a12f172c99330491e02fefdbd43adaba913667114b685cf4c4ab6fbf79be8ed'


def readiness():
    execution = r.read(BASE / 'execution.json')
    if r.live_identity(execution):
        return {'ready': False, 'reason': 'exact controller owner live; outcomes not read'}
    if execution['status'] != 'COMPLETED_PENDING_REVIEW':
        return {'ready': False, 'reason': 'complete fixed-budget execution required'}
    if any(r.live_identity(row) for row in execution['children']):
        return {'ready': False, 'reason': 'child identity still live; outcomes not read'}
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


def weighted_independent_means(samples, weights, confidence=.95):
    """Conditional fixed-lineage contrast: sampling variance, NOT between-seed variance."""
    r.protocol.require(len(samples) == len(weights) > 0 and 0 < confidence < 1,
        'invalid weighted contrast')
    r.protocol.require(all(type(w) in (int, float) and math.isfinite(w) for w in weights)
        and any(w != 0 for w in weights), 'invalid weights')
    for values in samples:
        r.protocol.values_ok(values)
    components = [w * w * statistics.variance(values) / len(values)
        for values, w in zip(samples, weights)]
    mean = sum(w * statistics.mean(values) for values, w in zip(samples, weights))
    variance = sum(components)
    denominator = sum(v * v / (len(values) - 1) for v, values in zip(components, samples))
    df = variance * variance / denominator if denominator else None
    se = math.sqrt(variance)
    half = float(r.protocol.t.ppf((1 + confidence) / 2, df)) * se if se else 0.
    return {'bb_per_100': mean, 'standard_error': se, 'ci': [mean - half, mean + half],
        'confidence': confidence, 'degrees_of_freedom': df, 'weights': weights,
        'sample_counts': [len(values) for values in samples], 'empirical_zero_variance': se == 0}


def synthesis(by_seed):
    r.protocol.require(set(by_seed) == {'seed1', 'seed3'}, 'both fixed seeds required')
    summaries = {seed: r.protocol.summarize_pair(groups, evidence_valid=True)
        for seed, groups in by_seed.items()}
    adjusted = 1 - .05 / 3
    result = {}
    for unit in ('raw_hands', 'session_means', 'balanced_wave_means'):
        values = {}
        for seed, groups in by_seed.items():
            for arm in r.protocol.ARMS:
                if unit == 'raw_hands':
                    values[seed, arm] = [v for group in groups[arm] for v in group]
                elif unit == 'session_means':
                    values[seed, arm] = summaries[seed]['arms'][arm]['session_means_bb_per_100']
                else:
                    values[seed, arm] = summaries[seed]['arms'][arm]['wave_means_bb_per_100']
        quantities = {}
        for arm in r.protocol.ARMS:
            samples = [values[seed, arm] for seed in ('seed1', 'seed3')]
            quantities[arm + '_absolute'] = {
                'nominal': weighted_independent_means(samples, [.5, .5]),
                'bonferroni_three_sensitivity': weighted_independent_means(samples, [.5, .5], adjusted)}
        if unit == 'balanced_wave_means':
            samples = [[m - s for m, s in zip(values[seed, 'moving256'], values[seed, 'static'])]
                for seed in ('seed1', 'seed3')]
            weights = [.5, .5]
        else:
            samples = [values[seed, arm] for seed in ('seed1', 'seed3') for arm in ('moving256', 'static')]
            weights = [.5, -.5, .5, -.5]
        quantities['moving_minus_static'] = {
            'nominal': weighted_independent_means(samples, weights),
            'bonferroni_three_sensitivity': weighted_independent_means(samples, weights, adjusted)}
        result[unit] = quantities
    return {'conditional_equal_seed_sampling_intervals': result, 'seed_weights': {'seed1': .5, 'seed3': .5},
        'exploratory_prior_seed1_results_influenced_allocation': True,
        'not_confirmatory_alpha_guarantees': True, 'training_seed_population_interval': False,
        'four_different_frozen_policies': True, 'development_hands': 160000, 'final_qualification_hands': 0,
        'assumptions': 'Independent raw sampling or independent session sensitivity; balanced-wave contrast preserves within-wave arm covariance. Only four waves per seed; no proof of arbitrary temporal independence.',
        'no_automatic_winner_or_final_test': True}


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
            and audit['sessions'] == 16 and audit['successful_hands'] == 40000, 'full replay audit mismatch')
        inputs[str(audit_path)] = r.sha(audit_path)
        items = [item for item in spec['schedule'] if item['arm'] == arm]
        by_id = {row['session_id']: row for row in audit['results']}
        r.protocol.require(len(audit['results']) == len(by_id) == 16 and
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
    groups, moments, replays = reviewed_groups(BASE, inputs)
    alternate_groups, seats, streams = r.parse_raw(BASE, models)
    r.protocol.require(groups == alternate_groups, 'independent raw parsers differ')
    current_statistics = r.protocol.summarize_pair(groups, evidence_valid=True)
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
        r.protocol.require(audit['status'] == 'PASS' and audit['hands'] == 40000 and audit['sessions'] == 16
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
    r.protocol.require(r.sha(PRIOR / 'post_terminal_review.json') == PRIOR_REVIEW_SHA
        and r.sha(PRIOR / 'launch_spec.json') == PRIOR_SPEC_SHA, 'fixed Seed1 source changed')
    old_review = r.read(PRIOR / 'post_terminal_review.json')
    r.protocol.require(old_review['passed'] and r.read(PRIOR / 'experiment.json')['status'] == 'COMPLETED',
        'Seed1 not qualified')
    r.check_hashes(old_review['input_sha256'])
    inputs[str(PRIOR / 'post_terminal_review.json')] = PRIOR_REVIEW_SHA
    old_groups, old_moments, old_replays = reviewed_groups(PRIOR, inputs)
    r.protocol.require(r.protocol.summarize_pair(old_groups, evidence_valid=True) == old_review['statistics']
        and old_moments == old_review['independent_integer_moments'], 'Seed1 raw evidence differs')
    combined = synthesis({'seed1': old_groups, 'seed3': groups})
    r.check_hashes(inputs)
    r.check_hashes(manifest['input_sha256'])
    return {'schema': 'cardpilot.seed3.external_post_terminal_two_seed_review.v1', 'passed': True,
        'created_at': datetime.now(timezone.utc).isoformat(), 'input_sha256': inputs,
        'frozen_input_hashes_rechecked': len(manifest['input_sha256']),
        'independent_integer_moments': moments, 'statistics': current_statistics,
        'seat_analysis': completed['seat_analysis'], 'cross_arm_token_audit': cross,
        'prior_seed1_statistics': old_review['statistics'], 'prior_seed1_integer_moments': old_moments,
        'exploratory_two_seed_synthesis': combined, 'current_decision_replays': replays,
        'prior_seed1_decision_replays_reused_not_rerun': old_replays,
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
