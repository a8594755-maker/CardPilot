"""Terminal-only independent raw and state review; never writes the live logger.

This directory is deliberately not a frozen dependency of the running controller.
Its commands/artifacts must be attached to the same record after the owner exits.
"""
from datetime import datetime, timezone
import gzip
import importlib.util
import json
import math
from pathlib import Path
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
PREVIOUS = ROOT / 'research/experiments/v6-current-kl-representation-pilot-20260905'
SOURCE = PREVIOUS / 'post_analysis/review.py'
spec = importlib.util.spec_from_file_location('independent_previous_review', SOURCE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
require, read, sha, live = old.require, old.read, old.sha, old.live
stats, buckets, raw_map, check_reported, training_health = old.stats, old.buckets, old.raw_map, old.check_reported, old.training_health
sys.path.insert(0, str(ROOT / 'research/experiments/v6-current-kl-scope-transfer-20260905'))
from scope_transfer import equal_tree
import torch

PARENT_SHA = {1: '8904f3b2e25baec5bc0bcb6556502c19b3fb213efdc9a32b16d55eee1284a3ef',
              3: 'f2249b0d19937ddadfc29fe5ba10cd7f07909d638dc0edeca89fae05b6f498e2'}
COUNTERS = {1: 10498234, 3: 10492141}
DOSES = {1: 262144, 2: 1048576}
ORDERS = {1: [(1, 'detached'), (1, 'connected'), (3, 'connected'), (3, 'detached')],
          2: [(3, 'detached'), (3, 'connected'), (1, 'connected'), (1, 'detached')]}
INITIAL_KEYS = ('model', 'optimizer', 'total_hands', 'iteration', 'ppo_replay_entries',
    'ppo_replay_rng_state', 'ppo_replay_cumulative_rows', 'pool_snapshots', 'pool_strategy',
    'pool_active_metadata', 'pool_candidate_history', 'main_process_rng_state', 'assignment_replay_origin')


def severe(summary):
    return (sum(value['ci95'][1] < -25 for value in summary['by_anchor'].values()) >= 3
            and all(summary['by_seat'][str(seat)]['ci95'][1] < 0 for seat in (0, 1)))


def compare_arms(full, half, earlier_decks):
    require(full.keys() == half.keys(), 'unmatched arm keys')
    contrast_rows = []
    for key, original in full.items():
        control = half[key]
        require(original['deck'] == control['deck']
                and original['control_rewards_bb'] == control['control_rewards_bb'], 'matched parent disagreement')
        deck = tuple(original['deck'])
        require(deck not in earlier_decks, 'cross-seed/stage deck reuse')
        earlier_decks.add(deck)
        contrast_rows.append((key[0], [control['treatment_rewards_bb'][s] - original['treatment_rewards_bb'][s]
                                     for s in (0, 1)]))
    contrast = buckets(contrast_rows)
    endpoints = {arm: buckets([(key[0], [r['treatment_rewards_bb'][s] - r['control_rewards_bb'][s]
                    for s in (0, 1)]) for key, r in rows.items()]) for arm, rows in (('detached', full), ('connected', half))}
    absolute = {arm: buckets([(key[0], row['treatment_rewards_bb']) for key, row in rows.items()])
                for arm, rows in (('detached', full), ('connected', half))}
    return {'connected_minus_detached': contrast, 'endpoint_minus_parent': endpoints, 'absolute_vs_anchors': absolute,
            'broad_collapse': severe(contrast) or any(severe(value) for value in endpoints.values())}


def counter_deltas(parent, final):
    previous, current = parent['environment_hand_accounting'], final['environment_hand_accounting']
    physical = int(current['completed_hands']) - int(previous['completed_hands'])
    transition = int(final['total_hands']) - int(parent['total_hands'])
    no_decision = int(current['no_trainable_decision_hands']) - int(previous['no_trainable_decision_hands'])
    replay = int(final['ppo_replay_cumulative_rows']) - int(parent['ppo_replay_cumulative_rows'])
    residual = physical - transition - no_decision
    require(physical >= transition > 0 and no_decision >= 0 and residual >= 0 and replay > 0,
            'invalid physical/transition/replay delta')
    return {'new_physical_hands': physical, 'new_transition_hands': transition,
            'new_no_decision_hands': no_decision, 'residual_worker_tail_hands': residual, 'new_replay_rows': replay}


def adam_steps(parent, final, reported, lr):
    left, right = parent['optimizer'], final['optimizer']
    require(len(left['param_groups']) == 1 and left['param_groups'][0]['lr'] == lr
            and equal_tree(left['param_groups'], right['param_groups']), 'optimizer group/LR changed')
    require(set(left['state']) == set(right['state']) == set(range(86)), 'missing or invented Adam state')
    require(reported['new_state_ids'] == [] and set(reported['per_parameter_steps']) == {str(i) for i in range(86)},
            'reported Adam coverage changed')
    deltas = {}
    for index in range(86):
        before, after = left['state'][index], right['state'][index]
        require(set(after) == {'step', 'exp_avg', 'exp_avg_sq'}
                and all(torch.isfinite(after[k]).all() for k in after), 'nonfinite/incomplete optimizer state')
        a, b = float(before['step']), float(after['step'])
        require(a.is_integer() and b.is_integer() and b > a, 'optimizer reset/no update')
        require(reported['per_parameter_steps'][str(index)] == {'before': int(a), 'after': int(b), 'delta': int(b - a)},
                'reported optimizer steps disagree with source')
        deltas[str(index)] = int(b - a)
    return deltas


def gradient_route(parent, initial, final, arm):
    require(arm in ('detached', 'connected'), 'unknown gradient arm')
    expected = arm == 'connected'
    for checkpoint in (parent, initial, final):
        config = checkpoint['config']
        actual = config.get('preflop_trunk_gradient', False)
        require(type(actual) is bool and actual is expected, 'gradient configuration mismatch')
        if 'preflop_trunk_gradient' in checkpoint:
            require(type(checkpoint['preflop_trunk_gradient']) is bool and
                    checkpoint['preflop_trunk_gradient'] is expected, 'gradient metadata mismatch')
        require(checkpoint.get('preflop_trunk_gradient_migration') == parent.get('preflop_trunk_gradient_migration'),
                'gradient migration provenance lost')
        require(checkpoint['critic_contract'] == 'critic_v2', 'critic route changed')
    if expected:
        origin = parent.get('preflop_trunk_gradient_migration')
        require(isinstance(origin, dict) and origin.get('schema') == 'cardpilot.preflop_actor_trunk_gradient.v1'
                and origin.get('target_preflop_trunk_gradient') is True
                and origin.get('source_preflop_trunk_gradient') is False, 'missing explicit gradient migration')
    return {'preflop_actor_to_trunk': expected, 'critic_to_trunk': False, 'origin_preserved': True}


def review_stage(base, stage, hashes, previous_decks):
    reported = read(base / f'stage{stage}_analysis.json')
    require(reported['passed'] and reported['evaluation_hands'] == 131072, 'stage incomplete')
    seeds = {}
    for seed in (1, 3):
        arms = {}
        for arm in ('detached', 'connected'):
            directory = base / f'eval_seed{seed}_{arm}_stage{stage}'
            summary, raw = read(directory / 'summary.json'), directory / 'common_deck_pairs.jsonl.gz'
            require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768
                and summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200
                and summary['observation_style'] == 'legacy_v4', 'wrong evaluation contract')
            require(summary['command'][summary['command'].index('--seed') + 1] == str(20264200 + seed * 10 + stage), 'wrong eval seed')
            require(summary['input_sha256']['control'] == PARENT_SHA[seed], 'wrong control checkpoint')
            require(summary['input_sha256']['treatment'] == sha(base / f'seed{seed}_{arm}_stage{stage}/latest.pt'), 'wrong treatment checkpoint')
            require(summary['raw_pairs_sha256'] == sha(raw), 'raw SHA mismatch')
            for name, path in summary['input_paths'].items():
                require(sha(path) == summary['input_sha256'][name], 'eval model changed')
            arms[arm] = raw_map(raw)
            for anchor in {key[0] for key in arms[arm]}:
                require(sorted(key[2] for key in arms[arm] if key[0] == anchor) == list(range(2048)), 'anchor pair coverage')
            hashes[str(raw)], hashes[str(directory / 'summary.json')] = sha(raw), sha(directory / 'summary.json')
        result = compare_arms(arms['detached'], arms['connected'], previous_decks)
        expected = reported['seeds'][str(seed)]
        check_reported(result['connected_minus_detached'], expected['connected_minus_detached'])
        for group in ('endpoint_minus_parent', 'absolute_vs_anchors'):
            for arm in ('detached', 'connected'):
                check_reported(result[group][arm], expected[group][arm])
        require(result['broad_collapse'] == expected['broad_collapse'], 'seed safety gate differs')
        seeds[str(seed)] = result
    require(reported['broad_collapse'] == any(row['broad_collapse'] for row in seeds.values()), 'stage safety gate differs')
    hashes[str(base / f'stage{stage}_analysis.json')] = sha(base / f'stage{stage}_analysis.json')
    return seeds


def main(base=BASE):
    output = base / 'post_terminal_review.json'
    require(not output.exists(), 'preserve prior review')
    owner = read(base / 'ownership.json')
    require(not live(owner['pid'], owner['create_time']), 'controller still live')
    require(not (base / 'controller_error.json').exists(), 'failure requires separate recovery review')
    result, contract = read(base / 'controller_result.json'), read(base / 'input_contract.json')
    require(result['phase'] in ('FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW', 'STAGE1_BROAD_COLLAPSE_REVIEW',
            'STAGE2_BROAD_COLLAPSE_REVIEW'), 'unexpected boundary')
    tests = base / 'post_analysis/review_tests.xml'
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    require(suites and sum(int(s.get('tests', 0)) for s in suites) >= 15
        and all(all(int(s.get(k, 0)) == 0 for k in ('failures', 'errors', 'skipped')) for s in suites), 'review tests incomplete')
    started = time.monotonic()
    torch.set_num_threads(1)
    hashes = dict(contract['input_sha256'])
    for path in (Path(__file__), SOURCE, tests, base / 'post_analysis/test_review.py', base / 'ownership.json',
                 base / 'input_contract.json', base / 'controller_result.json'):
        hashes[str(path)] = sha(path)
    counts = {key: 0 for key in ('new_training_hands', 'new_transition_hands', 'new_replay_rows',
        'new_no_decision_hands', 'residual_worker_tail_hands', 'lineage_training_hands', 'evaluation_hands',
        'slumbot_hands', 'final_qualification_hands')}
    stage_count = max(row['stage'] for row in result['training'])
    expected_cells = [(seed, arm, stage) for stage in range(1, stage_count + 1) for seed, arm in ORDERS[stage]]
    require([(r['seed'], r['arm'], r['stage']) for r in result['training']] == expected_cells, 'wrong cell order/coverage')
    job_wall, train_wall, children = 0.0, 0.0, 0
    terminations = list(base.glob('*/termination.json'))
    require(len(terminations) == 8 * stage_count, 'missing/extra terminal job')
    for path in terminations:
        terminal, process = read(path), read(path.parent / 'process.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors']
            and not terminal['remaining_observed_child_pids'] and not live(process['pid'], process['create_time']), 'job not cleanly terminal')
        for pid, created in terminal['observed_children'].items():
            require(not live(pid, created), 'recorded worker live')
            children += 1
        job_wall += terminal['wall_seconds']
        if (path.parent / 'verification.json').exists():
            require(len(terminal['observed_children']) >= 12, 'worker evidence missing')
            train_wall += terminal['wall_seconds']
        for name in ('termination.json', 'process.json', 'command.json'):
            hashes[str(path.parent / name)] = sha(path.parent / name)
    health, namespaces = {}, set()
    for row in result['training']:
        seed, arm, stage = row['seed'], row['arm'], row['stage']
        run = base / f'seed{seed}_{arm}_stage{stage}'
        require(read(run / 'verification.json') == row and row['passed'], 'verification mismatch')
        binding = read(run / 'parent_contract.json')
        require(sha(binding['path']) == binding['sha256'], 'training parent changed')
        parent = torch.load(binding['path'], map_location='cpu', weights_only=False)
        final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
        initial = torch.load(run / 'initial_resumed_state.pt', map_location='cpu', weights_only=False)
        for key in INITIAL_KEYS:
            require(equal_tree(parent[key], initial[key]), f'actual initial state changed:{key}')
        require(parent['environment_hand_accounting']['completed_hands'] == initial['environment_hand_accounting']['completed_hands']
            == binding['physical_hands'], 'initial physical reset')
        require(all(c['all_policy_heads_only_training'] is False for c in (parent, initial, final)), 'not full scope')
        route = gradient_route(parent, initial, final, arm)
        deltas = counter_deltas(parent, final)
        require(all(deltas[key] == row[key] for key in deltas), 'raw/checkpoint accounting mismatch')
        require(final['environment_hand_accounting']['completed_hands'] >= COUNTERS[seed] + DOSES[stage], 'target unmet')
        require(sha(run / 'latest.pt') == row['checkpoint_sha256'], 'endpoint hash mismatch')
        namespace = final['fixed_deal_attempt']['receipt']['namespace']
        require(namespace == row['namespace'] and namespace not in namespaces
            and namespace != parent['fixed_deal_attempt']['receipt']['namespace'], 'namespace reuse')
        require(final['fixed_deal_attempt']['receipt']['parent_checkpoint_sha256'] == binding['sha256'], 'wrong attempt parent')
        namespaces.add(namespace)
        lr = 9.999999999999996e-05
        require(row['actual_lr'] == binding['actual_lr'] == lr, 'wrong arm LR')
        steps = adam_steps(parent, final, row['optimizer_audit'], lr)
        with (run / 'h1_training_metrics.jsonl').open(encoding='utf-8') as handle:
            metrics = [json.loads(line) for line in handle if line.strip()]
        item = training_health(metrics, (run / 'latest_train.log').read_text(encoding='utf-8'), parent['iteration'], final['iteration'])
        item.update(actual_lr=lr, gradient_route=route, per_parameter_optimizer_step_deltas=steps,
            new_optimizer_state_ids=[], cumulative_physical_hands=final['environment_hand_accounting']['completed_hands'],
            new_physical_hands_this_stage=deltas['new_physical_hands'], frozen_endpoint_sha256=row['checkpoint_sha256'])
        health[run.name] = item
        for name, info in read(run / 'prefixes.json').items():
            with (run / name).open('rb') as handle:
                require(old.hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] == sha(info['path']), 'raw prefix changed')
        for key, value in deltas.items():
            counts['new_training_hands' if key == 'new_physical_hands' else key] += value
        counts['lineage_training_hands'] = max(counts['lineage_training_hands'], final['environment_hand_accounting']['completed_hands'])
        for name in ('latest.pt', 'verification.json', 'initial_resumed_state.pt', 'parent_contract.json', 'prefixes.json',
                     'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json', 'latest_train.log'):
            hashes[str(run / name)] = sha(run / name)
        del parent, initial, final
    decks, stages = set(), {}
    for stage in range(1, stage_count + 1):
        stages[str(stage)] = review_stage(base, stage, hashes, decks)
        counts['evaluation_hands'] += 131072
    require(len(decks) == stage_count * 16384, 'unique eval deck count')
    if result['phase'] == 'STAGE1_BROAD_COLLAPSE_REVIEW':
        require(stage_count == 1 and any(r['broad_collapse'] for r in stages['1'].values()), 'wrong early stopping boundary')
    else:
        require(stage_count == 2 and not any(r['broad_collapse'] for r in stages['1'].values()), 'stage2 crossed stop gate')
        require((result['phase'] == 'STAGE2_BROAD_COLLAPSE_REVIEW') == any(r['broad_collapse'] for r in stages['2'].values()), 'wrong final boundary')
    prior_rows = 0
    for path, digest in contract['prior_common_deck_corpus'].items():
        require(sha(path) == digest, 'prior corpus changed')
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                require(tuple(json.loads(line)['deck']) not in decks, 'previous corpus overlap')
                prior_rows += 1
        require(sha(path) == digest, 'prior corpus changed while reading')
        hashes[path] = digest
    require(all(sha(path) == digest for path, digest in hashes.items()), 'source/evidence changed')
    accounting = read(base / 'experiment.json')['accounting']
    for key in ('new_training_hands', 'new_transition_hands', 'evaluation_hands', 'slumbot_hands', 'final_qualification_hands'):
        require(accounting[key] == counts[key], f'logger accounting mismatch:{key}')
    report = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
        'phase': result['phase'], 'accounting': counts, 'stages': stages,
        'training_health_and_realized_update_dose': health, 'new_attempt_namespaces': sorted(namespaces),
        'all_recorded_processes_terminal': True, 'observed_child_identities_checked': children,
        'training_subprocess_wall_seconds': train_wall, 'all_job_wall_seconds': job_wall,
        'controller_wall_seconds': result['wall_seconds'],
        'actual_new_physical_hands_per_training_wall_second': counts['new_training_hands'] / train_wall,
        'prior_common_deck_rows_checked': prior_rows, 'unique_new_evaluation_decks': len(decks),
        'input_sha256': hashes, 'review_wall_seconds': time.monotonic() - started,
        'lineage_training_hands_semantics': 'largest single endpoint counter,not summed branches',
        'no_external_strength_or_final_qualification_claim': True}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ('passed', 'phase', 'accounting', 'review_wall_seconds')}))


if __name__ == '__main__':
    main()
