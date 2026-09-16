"""Independent terminal-only 2M continuation review; no poker requests or logger writes."""
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import statistics
import sys
import time
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parents[1]
ROOT = BASE.parents[2]
SOURCE = ROOT/'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906/post_analysis/review.py'
spec = importlib.util.spec_from_file_location('qualified_actor_state_statistics',SOURCE)
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
require,read,sha,live = old.require,old.read,old.sha,old.live
stats,buckets,check_reported,training_health = old.stats,old.buckets,old.check_reported,old.training_health
compare_arms,counter_deltas,adam_steps,gradient_route = old.compare_arms,old.counter_deltas,old.adam_steps,old.gradient_route
equal_tree,torch,INITIAL_KEYS = old.equal_tree,old.torch,old.INITIAL_KEYS
PARENT_SHA,COUNTERS = old.PARENT_SHA,old.COUNTERS
DOSES = {3:2097152}
ORDERS = {3:[(1,'detached'),(1,'connected'),(3,'connected'),(3,'detached')]}
EVAL_SEEDS = {1:20264411,3:20264431}
EXPECTED_OWNER = {'pid':29304,'create_time':1788713773.5332272}


def terminal_guard(base=BASE):
    owner = read(base/'ownership.json')
    require(owner['pid'] == EXPECTED_OWNER['pid'] and
            abs(owner['create_time']-EXPECTED_OWNER['create_time']) < .001,'owner identity changed')
    require(not live(owner['pid'],owner['create_time']),'controller still live')
    require(not (base/'controller_error.json').exists(),'failure requires separate preserved-state review')
    result = read(base/'controller_result.json')
    require(result['phase'] == 'FIXED_2M_COMPLETE_NEEDS_RESEARCH_REVIEW','fixed dose not complete')
    paths = list(base.glob('*/termination.json'))
    require(len(paths) == 8,'eight completed jobs required')
    for path in paths:
        terminal,process = read(path),read(path.parent/'process.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors'] and
                not terminal['remaining_observed_child_pids'],'unclean child termination')
        require(not live(process['pid'],process['create_time']),'job still live')
        require(all(not live(pid,created) for pid,created in terminal['observed_children'].items()),
                'worker still live')
    return {'ready':True,'jobs':8}


def validate_review_qualification(base=BASE):
    value = read(base/'post_analysis/qualification.json')
    require(value['passed'] and value['exit_code'] == 0,'review qualification incomplete')
    require(all(sha(p) == h for p,h in value['input_sha256'].items()),'review qualification inputs changed')
    return value


def raw_map(path):
    result, decks = {}, set()
    with gzip.open(path, 'rt', encoding='utf-8') as handle:
        for line in handle:
            row = json.loads(line)
            key = row['anchor'], row['anchor_seed'], row['pair_index']
            deck = tuple(row['deck'])
            require(key not in result and deck not in decks and sorted(deck) == list(range(52)), 'duplicate/invalid deck')
            for arm in ('control', 'treatment'):
                values = row[f'{arm}_rewards_bb']
                require(len(values) == 2 and all(math.isfinite(x) and abs(x) <= 200 for x in values), 'invalid payout')
                require(math.isclose(row[f'{arm}_pair_mean_bb'], statistics.mean(values), abs_tol=1e-9), 'bad pair mean')
            delta = [row['treatment_rewards_bb'][s] - row['control_rewards_bb'][s] for s in (0, 1)]
            require(all(math.isclose(x, y, abs_tol=1e-9) for x, y in zip(delta, row['treatment_minus_control_rewards_bb']))
                    and len(row['treatment_minus_control_rewards_bb']) == 2, 'bad seat arithmetic')
            require(math.isclose(statistics.mean(delta), row['treatment_minus_control_pair_mean_bb'], abs_tol=1e-9), 'bad delta')
            result[key] = row
            decks.add(deck)
    require(len(result) == 2048, 'incomplete raw evaluation')
    return result


def review_stage(base, stage, hashes, previous_decks):
    reported = read(base / f'stage{stage}_analysis.json')
    require(reported['passed'] and reported['evaluation_hands'] == 32768, 'stage incomplete')
    seeds = {}
    for seed in (1, 3):
        arms = {}
        for arm in ('detached', 'connected'):
            directory = base / f'eval_seed{seed}_{arm}_stage{stage}'
            summary, raw = read(directory / 'summary.json'), directory / 'common_deck_pairs.jsonl.gz'
            require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 8192
                and summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200
                and summary['observation_style'] == 'legacy_v4', 'wrong evaluation contract')
            require(summary['command'][summary['command'].index('--seed') + 1] == str(EVAL_SEEDS[seed]), 'wrong eval seed')
            require(summary['input_sha256']['control'] == PARENT_SHA[seed], 'wrong control checkpoint')
            require(summary['input_sha256']['treatment'] == sha(base / f'seed{seed}_{arm}_stage{stage}/latest.pt'), 'wrong treatment checkpoint')
            require(summary['raw_pairs_sha256'] == sha(raw), 'raw SHA mismatch')
            for name, path in summary['input_paths'].items():
                require(sha(path) == summary['input_sha256'][name], 'eval model changed')
            arms[arm] = raw_map(raw)
            for anchor in {key[0] for key in arms[arm]}:
                require(sorted(key[2] for key in arms[arm] if key[0] == anchor) == list(range(512)), 'anchor pair coverage')
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
    terminal_guard(base)
    require(not (base / 'controller_error.json').exists(), 'failure requires separate recovery review')
    result, contract = read(base / 'controller_result.json'), read(base / 'input_contract.json')
    require(result['phase'] == 'FIXED_2M_COMPLETE_NEEDS_RESEARCH_REVIEW', 'unexpected boundary')
    tests = base / 'post_analysis/tests.xml'
    suites = list(ET.parse(tests).getroot().iter('testsuite'))
    require(suites and sum(int(s.get('tests', 0)) for s in suites) >= 10
        and all(all(int(s.get(k, 0)) == 0 for k in ('failures', 'errors', 'skipped')) for s in suites), 'review tests incomplete')
    started = time.monotonic()
    torch.set_num_threads(1)
    hashes = dict(contract['input_sha256'])
    qualification = validate_review_qualification(base)
    hashes.update(qualification['input_sha256'])
    for path in (Path(__file__), SOURCE, tests, base / 'post_analysis/test_terminal_review.py', base / 'ownership.json',
                 base / 'input_contract.json', base / 'controller_result.json'):
        hashes[str(path)] = sha(path)
    counts = {key: 0 for key in ('new_training_hands', 'new_transition_hands', 'new_replay_rows',
        'new_no_decision_hands', 'residual_worker_tail_hands', 'lineage_training_hands', 'evaluation_hands',
        'slumbot_hands', 'final_qualification_hands')}
    expected_cells = [(seed, arm, 3) for seed, arm in ORDERS[3]]
    require([(r['seed'], r['arm'], r['stage']) for r in result['training']] == expected_cells, 'wrong cell order/coverage')
    job_wall, train_wall, children = 0.0, 0.0, 0
    terminations = list(base.glob('*/termination.json'))
    require(len(terminations) == 8, 'missing/extra terminal job')
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
        expected_parent = read(base / 'qualification.json')['parents'][f'seed{seed}_{arm}']
        require(binding['path'] == expected_parent['path'] and binding['sha256'] == expected_parent['sha256'],
                'wrong current1M parent')
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
            and namespace != parent['fixed_deal_attempt']['receipt']['namespace']
            and namespace not in contract['known_attempt_namespaces'], 'namespace reuse')
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
                require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] == sha(info['path']), 'raw prefix changed')
        for key, value in deltas.items():
            counts['new_training_hands' if key == 'new_physical_hands' else key] += value
        counts['lineage_training_hands'] = max(counts['lineage_training_hands'], final['environment_hand_accounting']['completed_hands'])
        for name in ('latest.pt', 'verification.json', 'initial_resumed_state.pt', 'parent_contract.json', 'prefixes.json',
                     'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json', 'latest_train.log'):
            hashes[str(run / name)] = sha(run / name)
        del parent, initial, final
    decks, stages = set(), {}
    for stage in (3,):
        stages[str(stage)] = review_stage(base, stage, hashes, decks)
        counts['evaluation_hands'] += 32768
    require(len(decks) == 4096, 'unique eval deck count')
    require(result['internal_broad_collapse'] == any(r['broad_collapse'] for r in stages['3'].values()),
            'terminal broad-collapse summary differs')
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
        'no_external_strength_or_final_qualification_claim': True,
        'earlier_unknown_lineage_tail_hands': None, 'statistical_not_bitwise_worker_continuation': True,
        'goal_achieved': False, 'automatic_next_scale': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({key: report[key] for key in ('passed', 'phase', 'accounting', 'review_wall_seconds')}))



if __name__ == '__main__':
    main()

