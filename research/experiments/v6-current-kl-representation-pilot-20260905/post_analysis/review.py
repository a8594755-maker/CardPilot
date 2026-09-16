"""Terminal-only independent accounting and raw paired-return review.

Not a dependency of the live controller. Does not alter its inputs or logger.
Run only after its exact owner and every recorded child identity are terminal.
"""
from collections import defaultdict
from datetime import datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import re
import statistics
import sys
import time

import psutil

BASE = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def live(pid, created):
    try:
        process = psutil.Process(int(pid))
        return abs(process.create_time() - float(created)) < .001 and process.is_running()
    except psutil.NoSuchProcess:
        return False


def stats(values):
    require(len(values) >= 2 and all(math.isfinite(x) for x in values), 'invalid statistical sample')
    point = statistics.mean(values) * 100
    se = statistics.stdev(values) * 100 / math.sqrt(len(values))
    return {'bb100': point, 'se_bb100': se, 'ci95': [point - 1.96 * se, point + 1.96 * se],
            'paired_decks': len(values)}


def buckets(rows):
    by_anchor, seats = defaultdict(list), [[], []]
    for anchor, values in rows:
        require(len(values) == 2 and all(math.isfinite(v) for v in values), 'bad paired rewards')
        by_anchor[anchor].append(statistics.mean(values))
        for seat in (0, 1):
            seats[seat].append(values[seat])
    require(len(by_anchor) == 4, 'wrong anchor coverage')
    return {'pooled': stats([statistics.mean(values) for _, values in rows]),
            'by_anchor': {name: stats(values) for name, values in by_anchor.items()},
            'by_seat': {str(i): stats(values) for i, values in enumerate(seats)}}


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
    require(len(result) == 8192, 'incomplete raw evaluation')
    return result


def check_reported(recomputed, reported):
    for level in ('pooled', 'by_anchor', 'by_seat'):
        left = {'pooled': recomputed[level]} if level == 'pooled' else recomputed[level]
        right = {'pooled': reported[level]} if level == 'pooled' else reported[level]
        require(left.keys() == right.keys(), 'summary bucket mismatch')
        for key, values in left.items():
            expected = right[key]
            require(math.isclose(values['bb100'], expected['bb100'], abs_tol=1e-8) and
                    math.isclose(values['ci95'][0], expected['ci95_low_bb100'], abs_tol=1e-8) and
                    math.isclose(values['ci95'][1], expected['ci95_high_bb100'], abs_tol=1e-8), 'statistical recomputation mismatch')


def training_health(metrics, log_text, parent_iteration, final_iteration):
    rows = [r for r in metrics if r['iteration'] > parent_iteration]
    expected = list(range(parent_iteration + 1, final_iteration + 1))
    require([r['iteration'] for r in rows] == expected and rows, 'training metric gap')
    reports = []
    for line in log_text.splitlines():
        match = re.match(r'^\[\s*(\d+)\]', line)
        if match:
            epoch = re.search(r'\bep=(\d+)/(\d+)', line)
            stop = re.search(r'\bklstop=([01])\b', line)
            require(epoch and stop, 'missing PPO epoch/early-stop evidence')
            reports.append((int(match[1]), int(epoch[1]), int(epoch[2]), int(stop[1])))
    require([r[0] for r in reports] == expected, 'PPO log update gap')
    require(all(1 <= actual <= maximum == 2 for _, actual, maximum, _ in reports), 'wrong reported PPO epochs')
    distributions = {}
    for key in ('entropy', 'approx_kl', 'reference_policy_kl'):
        values = [float(r[key]) for r in rows]
        require(all(math.isfinite(v) for v in values), 'nonfinite training health')
        distributions[key] = {'minimum': min(values), 'mean': statistics.mean(values),
                              'maximum': max(values), 'final': values[-1]}
    return {'completed_training_iterations': len(rows), 'metrics': distributions,
            'kl_early_stop_iterations': sum(r[3] for r in reports),
            'reported_epoch_counts': {str(k): sum(r[1] == k for r in reports) for k in (1, 2)},
            'epoch_counts_are_not_optimizer_step_counts': True,
            'training_rewards_and_KL_are_not_poker_strength_evidence': True}


def main():
    output = BASE / 'post_terminal_review.json'
    require(not output.exists(), 'preserve prior review')
    owner = read(BASE / 'ownership.json')
    require(not live(owner['pid'], owner['create_time']), 'controller still live; do not review partially')
    require(not (BASE / 'controller_error.json').exists(), 'failure requires separate recovery review')
    result, contract = read(BASE / 'controller_result.json'), read(BASE / 'input_contract.json')
    require(result['phase'] in ('FIXED_DOSE_COMPLETE_NEEDS_RESEARCH_REVIEW',
            'STAGE1_BROAD_COLLAPSE_REVIEW', 'STAGE2_BROAD_COLLAPSE_REVIEW'), 'unexpected terminal boundary')
    started = time.monotonic()
    hashes = dict(contract['input_sha256'])
    hashes[str(Path(__file__))] = sha(__file__)
    counts = {'new_training_hands': 0, 'new_transition_hands': 0, 'new_replay_rows': 0,
              'lineage_training_hands': 0, 'new_no_decision_hands': 0, 'residual_worker_tail_hands': 0,
              'evaluation_hands': 0, 'slumbot_hands': 0, 'final_qualification_hands': 0}
    train_wall, job_wall, children, namespaces = 0., 0., 0, set()
    health = {}
    for path in BASE.glob('*/termination.json'):
        terminal, process = read(path), read(path.parent / 'process.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors'] and
                not terminal['remaining_observed_child_pids'], 'nonclean terminal evidence')
        require(not live(process['pid'], process['create_time']), 'job still live')
        for pid, created in terminal['observed_children'].items():
            require(not live(pid, created), 'recorded worker still live')
            children += 1
        job_wall += terminal['wall_seconds']
        if (path.parent / 'verification.json').exists():
            require(len(terminal['observed_children']) >= 12, 'missing training workers')
            train_wall += terminal['wall_seconds']
        hashes[str(path)], hashes[str(path.parent / 'process.json')] = sha(path), sha(path.parent / 'process.json')
    import torch
    torch.set_num_threads(1)
    for row in result['training']:
        run = BASE / f'seed{row["seed"]}_{row["arm"]}_stage{row["stage"]}'
        verification, parent = read(run / 'verification.json'), read(run / 'parent_contract.json')
        require(row == verification and row['passed'], 'controller training result mismatch')
        final = torch.load(run / 'latest.pt', map_location='cpu', weights_only=False)
        physical = final['environment_hand_accounting']['completed_hands'] - parent['physical_hands']
        transition = final['total_hands'] - parent['transition_hands']
        require(physical == row['new_physical_hands'] and transition == row['new_transition_hands'], 'hand delta mismatch')
        require(sha(run / 'latest.pt') == row['checkpoint_sha256'], 'endpoint changed')
        require(row['namespace'] == final['fixed_deal_attempt']['receipt']['namespace'] and
                row['namespace'] not in namespaces, 'managed namespace mismatch/reuse')
        namespaces.add(row['namespace'])
        require(final['all_policy_heads_only_training'] is (row['arm'] == 'heads'), 'wrong serialized training scope')
        require(final['iteration'] > parent['iteration'], 'no completed updates')
        with (run / 'h1_training_metrics.jsonl').open(encoding='utf-8') as handle:
            metrics = [json.loads(line) for line in handle if line.strip()]
        health[run.name] = training_health(metrics, (run / 'latest_train.log').read_text(encoding='utf-8'),
                                            parent['iteration'], final['iteration'])
        # The per-parameter clocks distinguish76 new representation states from
        # the10 retained head/critic histories, rather than comparing global minima.
        steps = row['optimizer_audit']['per_parameter_steps']
        require(set(steps) == {str(k) for k in final['optimizer']['state']}, 'optimizer clock coverage')
        for key, item in steps.items():
            require(item['after'] == int(final['optimizer']['state'][int(key)]['step']) and
                    item['delta'] == item['after'] - item['before'] > 0, 'optimizer clock evidence mismatch')
        health[run.name]['per_parameter_optimizer_step_deltas'] = {key: item['delta'] for key, item in steps.items()}
        health[run.name]['new_optimizer_state_ids'] = row['optimizer_audit']['new_state_ids']
        health[run.name]['cumulative_physical_hands'] = final['environment_hand_accounting']['completed_hands']
        health[run.name]['new_physical_hands_this_stage'] = physical
        health[run.name]['frozen_endpoint_sha256'] = row['checkpoint_sha256']
        for name, info in read(run / 'prefixes.json').items():
            with (run / name).open('rb') as handle:
                require(hashlib.sha256(handle.read(info['bytes'])).hexdigest() == info['sha256'] == sha(info['path']), 'prefix altered')
        for key, value in (('new_training_hands', physical), ('new_transition_hands', transition),
                           ('new_replay_rows', row['new_replay_rows']),
                           ('new_no_decision_hands', row['new_no_decision_hands']),
                           ('residual_worker_tail_hands', row['residual_worker_tail_hands'])):
            counts[key] += value
        counts['lineage_training_hands'] = max(counts['lineage_training_hands'],
                                               final['environment_hand_accounting']['completed_hands'])
        for name in ('latest.pt', 'verification.json', 'initial_resumed_state.pt', 'parent_contract.json',
                     'prefixes.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl', 'run_manifest.json', 'latest_train.log'):
            hashes[str(run / name)] = sha(run / name)
        del final
    stages, prior_decks = {}, set()
    stage_count = max(row['stage'] for row in result['training'])
    require(len(result['training']) == stage_count * 4, 'missing seed or scope cell')
    for stage in range(1, stage_count + 1):
        reported = read(BASE / f'stage{stage}_analysis.json')
        seeds = {}
        for seed in (1, 3):
            arms = {}
            for arm in ('heads', 'full'):
                directory = BASE / f'eval_seed{seed}_{arm}_stage{stage}'
                summary, raw = read(directory / 'summary.json'), directory / 'common_deck_pairs.jsonl.gz'
                require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768 and
                        summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200 and
                        summary['observation_style'] == 'legacy_v4', 'wrong evaluation contract')
                require(summary['command'][summary['command'].index('--seed') + 1] == str(20263800 + seed * 10 + stage), 'wrong eval seed')
                require(summary['raw_pairs_sha256'] == sha(raw), 'raw SHA mismatch')
                for name, path in summary['input_paths'].items():
                    require(sha(path) == summary['input_sha256'][name], 'eval model changed')
                arms[arm] = raw_map(raw)
                counts['evaluation_hands'] += 32768
                hashes[str(raw)], hashes[str(directory / 'summary.json')] = sha(raw), sha(directory / 'summary.json')
            require(arms['heads'].keys() == arms['full'].keys(), 'unmatched comparison')
            contrast_rows = []
            for key, heads in arms['heads'].items():
                full = arms['full'][key]
                require(heads['deck'] == full['deck'] and heads['control_rewards_bb'] == full['control_rewards_bb'], 'matched-state parent disagreement')
                require(tuple(heads['deck']) not in prior_decks, 'cross-seed/stage deck repeat')
                prior_decks.add(tuple(heads['deck']))
                contrast_rows.append((key[0], [full['treatment_rewards_bb'][s] - heads['treatment_rewards_bb'][s] for s in (0, 1)]))
            contrast = buckets(contrast_rows)
            check_reported(contrast, reported['seeds'][str(seed)]['full_minus_heads'])
            endpoints = {}
            for arm, rows in arms.items():
                endpoints[arm] = buckets([(key[0], [r['treatment_rewards_bb'][s] - r['control_rewards_bb'][s] for s in (0, 1)]) for key, r in rows.items()])
                check_reported(endpoints[arm], reported['seeds'][str(seed)]['endpoint_minus_parent'][arm])
            collapse = sum(v['ci95'][1] < -25 for v in contrast['by_anchor'].values()) >= 3 and all(v['ci95'][1] < 0 for v in contrast['by_seat'].values())
            require(collapse == reported['seeds'][str(seed)]['broad_collapse'], 'collapse rule mismatch')
            seeds[str(seed)] = {'full_minus_heads': contrast, 'endpoint_minus_parent': endpoints, 'broad_collapse': collapse}
        stages[str(stage)] = seeds
        hashes[str(BASE / f'stage{stage}_analysis.json')] = sha(BASE / f'stage{stage}_analysis.json')
    prior_rows = 0
    for path, digest in contract['prior_common_deck_corpus'].items():
        require(sha(path) == digest, 'prior corpus changed')
        with gzip.open(path, 'rt', encoding='utf-8') as handle:
            for line in handle:
                require(tuple(json.loads(line)['deck']) not in prior_decks, 'previous corpus overlap')
                prior_rows += 1
    require(all(sha(path) == digest for path, digest in hashes.items()), 'frozen input/evidence changed')
    record = read(BASE / 'experiment.json')
    require(record['accounting']['new_training_hands'] == counts['new_training_hands'] and
            record['accounting']['evaluation_hands'] == counts['evaluation_hands'], 'logger/raw accounting mismatch')
    report = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
              'command': [sys.executable, *sys.argv], 'phase': result['phase'], 'accounting': counts,
              'stages': stages, 'training_health_and_realized_update_dose': health,
              'new_attempt_namespaces': sorted(namespaces),
              'all_recorded_processes_terminal': True, 'observed_child_identities_checked': children,
              'training_subprocess_wall_seconds': train_wall, 'all_job_wall_seconds': job_wall,
              'controller_wall_seconds': result['wall_seconds'],
              'actual_new_physical_hands_per_training_wall_second': counts['new_training_hands'] / train_wall,
              'lineage_training_hands_semantics': 'largest single endpoint cumulative counter, never sum branches/seeds',
              'prior_common_deck_rows_checked': prior_rows, 'unique_new_evaluation_decks': len(prior_decks),
              'input_sha256': hashes, 'review_wall_seconds': time.monotonic() - started,
              'no_external_strength_or_final_qualification_claim': True}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ('input_sha256', 'stages',
          'training_health_and_realized_update_dose')}), flush=True)


if __name__ == '__main__':
    main()
