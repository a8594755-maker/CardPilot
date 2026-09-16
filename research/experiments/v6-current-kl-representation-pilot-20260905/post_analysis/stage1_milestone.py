"""Read closed stage1 evidence only; never mutate live inputs or the logger."""
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

from review import BASE, buckets, check_reported, live, raw_map, read, require, sha, training_health


def main():
    output = BASE / 'post_analysis' / 'stage1_milestone.json'
    require(not output.exists(), 'preserve existing milestone')
    started = time.monotonic()
    reported = read(BASE / 'stage1_analysis.json')
    hashes = {str(Path(__file__)): sha(__file__),
              str(Path(__file__).with_name('review.py')): sha(Path(__file__).with_name('review.py')),
              str(BASE / 'stage1_analysis.json'): sha(BASE / 'stage1_analysis.json')}
    seeds, health, decks = {}, {}, set()
    training_hands, transition_hands, train_wall, eval_wall = 0, 0, 0., 0.
    for seed in (1, 3):
        arms = {}
        for arm in ('heads', 'full'):
            name = f'seed{seed}_{arm}_stage1'
            run, evaluation = BASE / name, BASE / f'eval_{name}'
            for job in (run, BASE / f'job_eval_{name}'):
                process, terminal = read(job / 'process.json'), read(job / 'termination.json')
                require(terminal['exit_code'] == 0 and not terminal['observer_errors'] and
                        not terminal['remaining_observed_child_pids'], 'unclean stage1 job')
                require(not live(process['pid'], process['create_time']), 'stage1 job still live')
                require(all(not live(pid, created) for pid, created in terminal['observed_children'].items()),
                        'recorded stage1 child still live')
                if job == run:
                    train_wall += terminal['wall_seconds']
                else:
                    eval_wall += terminal['wall_seconds']
                for file in ('process.json', 'termination.json', 'command.json'):
                    hashes[str(job / file)] = sha(job / file)
            verification, parent = read(run / 'verification.json'), read(run / 'parent_contract.json')
            require(verification['passed'], 'stage1 training audit failed')
            training_hands += verification['new_physical_hands']
            transition_hands += verification['new_transition_hands']
            metrics = [json.loads(line) for line in (run / 'h1_training_metrics.jsonl').read_text(encoding='utf-8').splitlines() if line.strip()]
            health[name] = training_health(metrics, (run / 'latest_train.log').read_text(encoding='utf-8'),
                                           parent['iteration'], metrics[-1]['iteration'])
            health[name]['per_parameter_optimizer_steps'] = verification['optimizer_audit']['per_parameter_steps']
            health[name]['new_physical_hands'] = verification['new_physical_hands']
            summary, raw = read(evaluation / 'summary.json'), evaluation / 'common_deck_pairs.jsonl.gz'
            require(summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 32768 and
                    summary['policy_mode'] == 'greedy' and summary['starting_stack_bb'] == 200 and
                    summary['observation_style'] == 'legacy_v4', 'wrong evaluation contract')
            require(summary['raw_pairs_sha256'] == sha(raw), 'raw SHA mismatch')
            require(summary['input_sha256']['treatment'] == verification['checkpoint_sha256'], 'wrong endpoint')
            for key, path in summary['input_paths'].items():
                require(sha(path) == summary['input_sha256'][key], 'evaluation model changed')
                hashes[path] = summary['input_sha256'][key]
            arms[arm] = raw_map(raw)
            for file in (raw, evaluation / 'summary.json', run / 'verification.json',
                         run / 'parent_contract.json', run / 'h1_training_metrics.jsonl', run / 'latest_train.log'):
                hashes[str(file)] = sha(file)
        require(arms['heads'].keys() == arms['full'].keys(), 'unmatched evaluation')
        rows = []
        for key, heads in arms['heads'].items():
            full = arms['full'][key]
            require(heads['deck'] == full['deck'] and heads['control_rewards_bb'] == full['control_rewards_bb'],
                    'deck or repeated-parent mismatch')
            require(tuple(heads['deck']) not in decks, 'cross-seed duplicate deck')
            decks.add(tuple(heads['deck']))
            rows.append((key[0], [full['treatment_rewards_bb'][s] - heads['treatment_rewards_bb'][s] for s in (0, 1)]))
        contrast = buckets(rows)
        check_reported(contrast, reported['seeds'][str(seed)]['full_minus_heads'])
        endpoints = {}
        for arm, raw_rows in arms.items():
            endpoints[arm] = buckets([(key[0], r['treatment_minus_control_rewards_bb']) for key, r in raw_rows.items()])
            check_reported(endpoints[arm], reported['seeds'][str(seed)]['endpoint_minus_parent'][arm])
        collapse = sum(v['ci95'][1] < -25 for v in contrast['by_anchor'].values()) >= 3 and all(v['ci95'][1] < 0 for v in contrast['by_seat'].values())
        require(collapse == reported['seeds'][str(seed)]['broad_collapse'], 'preregistered rule mismatch')
        seeds[str(seed)] = {'full_minus_heads': contrast, 'endpoint_minus_parent': endpoints, 'broad_collapse': collapse}
    require(all(sha(path) == digest for path, digest in hashes.items()), 'evidence changed during review')
    report = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(),
              'command': [sys.executable, *sys.argv], 'stage': 1, 'seeds': seeds,
              'training_health': health, 'stage1_new_physical_hands': training_hands,
              'stage1_new_transition_hands': transition_hands, 'evaluation_hands': 131072,
              'new_hands_from_this_review': 0, 'unique_stage1_evaluation_decks': len(decks),
              'training_subprocess_wall_seconds': train_wall, 'evaluation_subprocess_wall_seconds': eval_wall,
              'prior_corpus_freshness_scope': 'controller stage1 result; independently rechecked at terminal review',
              'ci_scope': 'conditional paired deck means; nominal, not training-seed population or Slumbot strength',
              'decision': 'Negative stage1, especially Seed3. No preregistered severe broad collapse; unchanged fixed stage2 continues. Not a positive-strength gate.',
              'input_sha256': hashes, 'review_wall_seconds': time.monotonic() - started}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({k: v for k, v in report.items() if k not in ('input_sha256', 'training_health', 'seeds')}))


if __name__ == '__main__':
    main()
