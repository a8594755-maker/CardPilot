"""Audit a completed seeded dynamic-K-best train_v5 session."""

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
    parser.add_argument('--expected-initial-pool-size', type=int, required=True)
    parser.add_argument('--expected-final-pool-size', type=int, required=True)
    parser.add_argument('--expected-snapshot-every', type=int, required=True)
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
    if final_hands < args.expected_target_hands:
        raise RuntimeError('actual final hands are below target')
    if final_iteration != args.expected_final_iteration:
        raise RuntimeError('unexpected final iteration')
    for source, label in ((checkpoint, 'checkpoint'), (manifest, 'manifest')):
        if int(source.get('total_hands', -1)) != final_hands:
            raise RuntimeError(f'{label}/metric final hand mismatch')
        if int(source.get('iteration', -1)) != final_iteration:
            raise RuntimeError(f'{label}/metric final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('run manifest is not terminal finished')

    final_pool = checkpoint.get('pool_snapshots') or []
    final_pool_ids = [int(row['id']) for row in final_pool]
    if len(final_pool) != args.expected_final_pool_size:
        raise RuntimeError('unexpected final pool size')
    if len(final_pool_ids) != len(set(final_pool_ids)):
        raise RuntimeError('final pool ids are not unique')
    seed_rows = [
        row for row in final_pool
        if (row.get('score_components') or {}).get('kind')
        == 'initial_external_opponent'
    ]
    learned_rows = [
        row for row in final_pool
        if (row.get('score_components') or {}).get('kind')
        != 'initial_external_opponent'
    ]
    if len(seed_rows) != args.expected_initial_pool_size:
        raise RuntimeError('seeded anchors were not retained exactly')
    if len(learned_rows) != (
        args.expected_final_pool_size - args.expected_initial_pool_size
    ):
        raise RuntimeError('unexpected learned-snapshot survivor count')

    adaptive_rewards = checkpoint.get('adaptive_opponent_ema_rewards') or []
    adaptive_weights = checkpoint.get('adaptive_opponent_weights') or []
    adaptive_observations = checkpoint.get('adaptive_opponent_observations') or []
    if not (
        len(adaptive_rewards)
        == len(adaptive_weights)
        == len(adaptive_observations)
        == len(final_pool)
    ):
        raise RuntimeError('final adaptive state does not match final membership')
    if abs(sum(float(value) for value in adaptive_weights) - 1.0) > 1e-9:
        raise RuntimeError('final adaptive weights do not sum to one')

    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config['seed']),
        worker_count=int(config['workers']),
        pool_size=len(final_pool),
        pool_snapshot_ids=final_pool_ids,
        group_count=int(config['opponent_groups']),
        self_play_fraction=float(config['self_play_fraction']),
        checkpoint_iteration=final_iteration,
        checkpoint_total_hands=final_hands,
    )
    if assignment_audit['tail_iteration'] != final_iteration:
        raise RuntimeError('terminal assignment tail is not the final iteration')
    if assignment_audit['pending_assignments'] is not None:
        raise RuntimeError('terminal run has an unused pending assignment')

    membership_by_iteration = {
        int(row['applies_to_iteration']): [
            int(ref['snapshot_id'])
            for ref in (row.get('pool_snapshot_refs') or [])
        ]
        for row in assignments
    }
    if len(membership_by_iteration[1]) != args.expected_initial_pool_size:
        raise RuntimeError('iteration 1 does not use the seeded initial pool')
    membership_changes = []
    previous_ids = None
    for iteration in expected_iterations:
        ids = membership_by_iteration[iteration]
        if previous_ids is not None and ids != previous_ids:
            membership_changes.append({
                'applies_to_iteration': iteration,
                'from_snapshot_ids': previous_ids,
                'to_snapshot_ids': ids,
            })
            if (iteration - 1) % args.expected_snapshot_every != 0:
                raise RuntimeError('pool membership changed off snapshot cadence')
        previous_ids = ids

    candidate_history = checkpoint.get('pool_candidate_history') or []
    expected_snapshot_count = (
        args.expected_final_iteration // args.expected_snapshot_every
    )
    if len(candidate_history) != (
        args.expected_initial_pool_size + expected_snapshot_count
    ):
        raise RuntimeError('candidate history does not cover every seed/snapshot')

    archive_rows = []
    for path in sorted((run_dir / 'checkpoints').glob('checkpoint_iter*_hands*.pt')):
        match = ARCHIVE_RE.match(path.name)
        if match:
            archive_rows.append({
                'iteration': int(match.group('iteration')),
                'hands': int(match.group('hands')),
                'path': str(path),
                'bytes': path.stat().st_size,
                'sha256': sha256_path(path),
            })
    if [row['iteration'] for row in archive_rows] != [16, 32, 48, 64]:
        raise RuntimeError('unexpected archive checkpoint set')

    optimizer_states = (checkpoint.get('optimizer') or {}).get('state') or {}
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get('step', 0)
        optimizer_steps.append(
            int(step.item() if hasattr(step, 'item') else step)
        )
    if not optimizer_steps:
        raise RuntimeError('optimizer state is empty')

    result = {
        'schema': 'cardpilot.train_v5.dynamic_pool_session_audit.v1',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': final_iteration,
        'actual_environment_hands': final_hands,
        'target_environment_hands': int(args.expected_target_hands),
        'metric_rows': len(metrics),
        'assignment_rows': len(assignments),
        'assignment_audit': assignment_audit,
        'initial_pool_size': int(args.expected_initial_pool_size),
        'final_pool_size': len(final_pool),
        'final_pool_snapshot_ids': final_pool_ids,
        'learned_survivor_snapshot_ids': [int(row['id']) for row in learned_rows],
        'candidate_history_rows': len(candidate_history),
        'membership_changes': membership_changes,
        'adaptive_state_lengths': {
            'ema_rewards': len(adaptive_rewards),
            'weights': len(adaptive_weights),
            'observations': len(adaptive_observations),
        },
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
