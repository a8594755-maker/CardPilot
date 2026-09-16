"""Describe realized update dose for two CLOSED cells; no new poker or live writes."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import statistics
import sys

from review import BASE, SOURCE, live, read, require, sha, training_health


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', type=int, choices=(1, 3), required=True)
    parser.add_argument('--stage', type=int, choices=(1, 2), required=True)
    args = parser.parse_args()
    output = BASE / f'post_analysis/seed{args.seed}_stage{args.stage}_realized_dose.json'
    require(not output.exists(), 'preserve prior dose observation')
    inputs = {str(path): sha(path) for path in (Path(__file__), Path(__file__).with_name('review.py'), SOURCE)}
    arms = {}
    for arm in ('full', 'half'):
        run = BASE / f'seed{args.seed}_{arm}_stage{args.stage}'
        terminal, process = read(run / 'termination.json'), read(run / 'process.json')
        require(terminal['exit_code'] == 0 and not terminal['observer_errors']
                and not terminal['remaining_observed_child_pids'] and not live(process['pid'], process['create_time']),
                'cell not cleanly terminal')
        require(all(not live(pid, created) for pid, created in terminal['observed_children'].items()), 'worker still live')
        verification, parent = read(run / 'verification.json'), read(run / 'parent_contract.json')
        require(verification['passed'] and verification['arm'] == arm and verification['training_scope'] == 'full_network', 'wrong cell')
        require(sha(run / 'latest.pt') == verification['checkpoint_sha256'], 'endpoint changed')
        with (run / 'h1_training_metrics.jsonl').open(encoding='utf-8') as handle:
            metrics = [json.loads(line) for line in handle if line.strip()]
        manifest = read(run / 'run_manifest.json')
        require(manifest['status'] == 'finished', 'manifest not terminal')
        health = training_health(metrics, (run / 'latest_train.log').read_text(encoding='utf-8'),
                                 parent['iteration'], manifest['iteration'])
        steps = verification['optimizer_audit']['per_parameter_steps']
        require(set(steps) == {str(i) for i in range(86)} and not verification['optimizer_audit']['new_state_ids'], 'Adam coverage')
        deltas = [value['delta'] for value in steps.values()]
        require(all(value > 0 for value in deltas), 'missing actual updates')
        health.update(new_physical_hands=verification['new_physical_hands'],
            new_transition_hands=verification['new_transition_hands'], actual_lr=verification['actual_lr'],
            per_parameter_step_delta_minimum=min(deltas), per_parameter_step_delta_maximum=max(deltas),
            mean_per_parameter_step_delta=statistics.mean(deltas),
            subprocess_wall_seconds=verification['subprocess_wall_seconds'],
            physical_hands_per_second=verification['physical_hands_per_second'],
            source_checkpoint_sha256=verification['checkpoint_sha256'])
        arms[arm] = health
        for name in ('termination.json', 'process.json', 'verification.json', 'parent_contract.json',
                     'h1_training_metrics.jsonl', 'run_manifest.json', 'latest_train.log', 'latest.pt'):
            inputs[str(run / name)] = sha(run / name)
    require(all(sha(path) == digest for path, digest in inputs.items()), 'closed input changed')
    require(arms['half']['actual_lr'] == .5 * arms['full']['actual_lr'], 'actual LR ratio incorrect')
    report = {'passed': True, 'created_at': datetime.now(timezone.utc).isoformat(), 'command': sys.orig_argv,
        'seed': args.seed, 'stage': args.stage, 'arms': arms,
        'half_over_full_mean_step_count': arms['half']['mean_per_parameter_step_delta'] / arms['full']['mean_per_parameter_step_delta'],
        'input_sha256': inputs, 'new_training_or_evaluation_hands': 0,
        'scope': 'Descriptive realized-dose comparison of closed training cells. Different statistical training streams;not causal step-dose isolation,poker strength or seed-population evidence.',
        'allocation_changed': False, 'live_controller_or_record_modified': False}
    with output.open('x', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, allow_nan=False)
    print(json.dumps({key: value for key, value in report.items() if key != 'input_sha256'}, indent=2))


if __name__ == '__main__':
    main()
