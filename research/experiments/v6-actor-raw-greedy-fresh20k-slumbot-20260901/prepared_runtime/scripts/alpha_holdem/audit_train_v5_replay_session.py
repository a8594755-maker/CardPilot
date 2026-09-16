"""Audit a completed interrupted/resumed train_v5 PPO-replay session."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from train_v5 import restore_group_assignment_rng_from_evidence


ARCHIVE_RE = re.compile(
    r'^checkpoint_iter(?P<iteration>\d+)_hands(?P<hands>\d+)\.pt$'
)


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def load_jsonl(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding='utf-8').splitlines()
        if line.strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--expected-target-hands', type=int, required=True)
    parser.add_argument('--expected-final-iteration', type=int, required=True)
    parser.add_argument('--expected-recovery-iteration', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    checkpoint_path = run_dir / 'latest.pt'
    manifest_path = run_dir / 'run_manifest.json'
    metrics_path = run_dir / 'h1_training_metrics.jsonl'
    assignments_path = run_dir / 'opponent_assignments.jsonl'
    train_log_path = run_dir / 'latest_train.log'
    for path in (
        checkpoint_path,
        manifest_path,
        metrics_path,
        assignments_path,
        train_log_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    checkpoint = torch.load(
        checkpoint_path, map_location='cpu', weights_only=False
    )
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    metrics = load_jsonl(metrics_path)
    assignments = load_jsonl(assignments_path)
    config = checkpoint.get('config') or {}
    iterations = [int(row['iteration']) for row in metrics]
    hands = [int(row['hands']) for row in metrics]
    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    if iterations != expected_iterations:
        raise RuntimeError('training metric iterations are not exactly contiguous')
    if any(right <= left for left, right in zip(hands, hands[1:])):
        raise RuntimeError('training hand counter is not strictly increasing')
    final_hands = hands[-1]
    final_iteration = iterations[-1]
    if final_iteration != args.expected_final_iteration:
        raise RuntimeError('unexpected final iteration')
    if final_hands < args.expected_target_hands:
        raise RuntimeError('actual final hands are below target')
    if int(checkpoint.get('total_hands', -1)) != final_hands:
        raise RuntimeError('checkpoint/metric final hand mismatch')
    if int(checkpoint.get('iteration', -1)) != final_iteration:
        raise RuntimeError('checkpoint/metric final iteration mismatch')
    if int(manifest.get('total_hands', -1)) != final_hands:
        raise RuntimeError('manifest/metric final hand mismatch')
    if int(manifest.get('iteration', -1)) != final_iteration:
        raise RuntimeError('manifest/metric final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('run manifest is not terminal finished')

    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config['seed']),
        worker_count=int(config['workers']),
        pool_size=len(config['fixed_opponent_checkpoints']),
        group_count=int(config['opponent_groups']),
        self_play_fraction=float(config['self_play_fraction']),
        checkpoint_iteration=final_iteration,
        checkpoint_total_hands=final_hands,
    )
    if assignment_audit['tail_iteration'] != final_iteration:
        raise RuntimeError('terminal assignment tail is not the final iteration')
    if assignment_audit['pending_assignments'] is not None:
        raise RuntimeError('terminal run has an unused pending assignment')

    zero_replay_iterations = [
        int(row['iteration'])
        for row in metrics
        if int(row.get('ppo_replay_rows', 0)) == 0
    ]
    expected_zero = [1, args.expected_recovery_iteration + 1]
    if zero_replay_iterations != expected_zero:
        raise RuntimeError(
            f'unexpected zero-replay iterations: {zero_replay_iterations}'
        )
    cumulative_replay = [
        int(row.get('ppo_replay_cumulative_rows', 0)) for row in metrics
    ]
    if any(
        right < left
        for left, right in zip(cumulative_replay, cumulative_replay[1:])
    ):
        raise RuntimeError('cumulative replay rows decreased')
    boundaries = checkpoint.get('ppo_replay_recovery_boundaries') or []
    if [int(row.get('iteration', -1)) for row in boundaries] != [
        args.expected_recovery_iteration
    ]:
        raise RuntimeError('checkpoint replay recovery boundary mismatch')
    if len(checkpoint.get('ppo_replay_entries') or []) != int(
        config['ppo_replay_buffer_iterations']
    ):
        raise RuntimeError('terminal checkpoint replay buffer is incomplete')
    if checkpoint.get('ppo_replay_rng_state') is None:
        raise RuntimeError('terminal checkpoint has no replay RNG state')

    archive_rows = []
    checkpoint_dir = run_dir / 'checkpoints'
    for path in sorted(checkpoint_dir.glob('checkpoint_iter*_hands*.pt')):
        match = ARCHIVE_RE.match(path.name)
        if match:
            archive_rows.append({
                'iteration': int(match.group('iteration')),
                'hands': int(match.group('hands')),
                'path': str(path),
                'bytes': path.stat().st_size,
                'sha256': sha256_path(path),
            })
    archive_iterations = [row['iteration'] for row in archive_rows]
    if archive_iterations != [16, 32, 48, 64]:
        raise RuntimeError(
            f'unexpected archive checkpoint set: {archive_iterations}'
        )

    optimizer_states = (checkpoint.get('optimizer') or {}).get('state') or {}
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get('step', 0)
        optimizer_steps.append(
            int(step.item() if hasattr(step, 'item') else step)
        )
    result = {
        'schema': 'cardpilot.train_v5.replay_session_audit.v1',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': final_iteration,
        'actual_environment_hands': final_hands,
        'target_environment_hands': int(args.expected_target_hands),
        'metric_rows': len(metrics),
        'assignment_rows': len(assignments),
        'assignment_audit': assignment_audit,
        'zero_replay_iterations': zero_replay_iterations,
        'cumulative_replay_rows': cumulative_replay[-1],
        'replay_recovery_boundaries': boundaries,
        'serialized_replay_entry_iterations': [
            int(row['iteration'])
            for row in checkpoint.get('ppo_replay_entries') or []
        ],
        'optimizer_state_count': len(optimizer_states),
        'optimizer_step_min': min(optimizer_steps),
        'optimizer_step_max': max(optimizer_steps),
        'archives': archive_rows,
        'artifact_integrity': {
            'latest_checkpoint_sha256': sha256_path(checkpoint_path),
            'latest_checkpoint_bytes': checkpoint_path.stat().st_size,
            'manifest_sha256': sha256_path(manifest_path),
            'metrics_sha256': sha256_path(metrics_path),
            'assignments_sha256': sha256_path(assignments_path),
            'train_log_sha256': sha256_path(train_log_path),
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
