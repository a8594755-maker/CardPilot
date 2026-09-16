"""Read-only resume-contract audit for interrupted train_v5 replay runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from train_v5 import restore_group_assignment_rng_from_evidence


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
    parser.add_argument('--checkpoint', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--metrics', type=Path, required=True)
    parser.add_argument('--assignments', type=Path, required=True)
    parser.add_argument('--source-policy-reference', type=Path, required=True)
    parser.add_argument('--deal-start-index', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    checkpoint_path = args.checkpoint.resolve()
    manifest_path = args.manifest.resolve()
    metrics_path = args.metrics.resolve()
    assignments_path = args.assignments.resolve()
    source_reference_path = args.source_policy_reference.resolve()
    for path in (
        checkpoint_path,
        manifest_path,
        metrics_path,
        assignments_path,
        source_reference_path,
    ):
        if not path.is_file():
            raise FileNotFoundError(path)

    checkpoint = torch.load(
        checkpoint_path, map_location='cpu', weights_only=False
    )
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    metrics = load_jsonl(metrics_path)
    assignments = load_jsonl(assignments_path)
    total_hands = int(checkpoint.get('total_hands', -1))
    iteration = int(checkpoint.get('iteration', -1))
    config = checkpoint.get('config') or {}
    if total_hands <= 0 or iteration <= 0:
        raise RuntimeError('checkpoint has no inherited hand/iteration state')
    if int(manifest.get('total_hands', -1)) != total_hands:
        raise RuntimeError('manifest/checkpoint hand count mismatch')
    if int(manifest.get('iteration', -1)) != iteration:
        raise RuntimeError('manifest/checkpoint iteration mismatch')
    if not metrics:
        raise RuntimeError('training metrics are empty')
    metric_tail = metrics[-1]
    if (
        int(metric_tail.get('hands', -1)) != total_hands
        or int(metric_tail.get('iteration', -1)) != iteration
    ):
        raise RuntimeError('metric tail/checkpoint boundary mismatch')
    optimizer = checkpoint.get('optimizer') or {}
    optimizer_states = optimizer.get('state') or {}
    if not optimizer_states:
        raise RuntimeError('checkpoint optimizer state is empty')
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get('step', 0)
        optimizer_steps.append(
            int(step.item() if hasattr(step, 'item') else step)
        )
    original_resume = Path(str(checkpoint.get('resume') or '')).resolve()
    if original_resume != source_reference_path:
        raise RuntimeError(
            'requested source-policy reference is not the original run anchor'
        )
    if float(config.get('source_policy_kl_coef', 0.0)) <= 0.0:
        raise RuntimeError('source-policy KL is not enabled in source config')
    source_deal_start_index = int(
        config.get('fixed_training_deal_start_index', 0)
    )
    worker_counts = (
        (checkpoint.get('environment_hand_accounting') or {}).get(
            'session_worker_counts'
        )
        or []
    )
    first_unused_deal_indices = [
        source_deal_start_index + int(row['completed_hands'])
        for row in worker_counts
    ]
    conservative_first_unused_deal_index = max(
        first_unused_deal_indices,
        default=source_deal_start_index + total_hands,
    )
    if args.deal_start_index < conservative_first_unused_deal_index:
        raise RuntimeError(
            'deal start index cannot prove non-overlap with prior worker streams: '
            f'{args.deal_start_index} < '
            f'{conservative_first_unused_deal_index}'
        )

    pool_snapshots = checkpoint.get('pool_snapshots') or []
    if pool_snapshots:
        pool_size = len(pool_snapshots)
        pool_snapshot_ids = [int(row['id']) for row in pool_snapshots]
    else:
        pool_size = len(config['fixed_opponent_checkpoints'])
        pool_snapshot_ids = None

    assignment_resume = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config['seed']),
        worker_count=int(config['workers']),
        pool_size=pool_size,
        pool_snapshot_ids=pool_snapshot_ids,
        group_count=int(config['opponent_groups']),
        self_play_fraction=float(config['self_play_fraction']),
        checkpoint_iteration=iteration,
        checkpoint_total_hands=total_hands,
    )
    if assignment_resume['pending_assignments'] is None:
        raise RuntimeError('no pending next-iteration assignment was recovered')

    serialized_replay = checkpoint.get('ppo_replay_entries')
    replay_limitation = None
    if serialized_replay is None:
        replay_limitation = {
            'kind': 'legacy_checkpoint_missing_complete_hand_replay_state',
            'required_recovery': (
                'explicit cold-start acknowledgement; first resumed update '
                'has zero historical replay rows'
            ),
            'model_optimizer_hand_counter_continuity': True,
        }
    result = {
        'schema': 'cardpilot.train_v5.replay_resume_preflight.v1',
        'status': 'PASS',
        'checkpoint': {
            'path': str(checkpoint_path),
            'sha256': sha256_path(checkpoint_path),
            'bytes': checkpoint_path.stat().st_size,
            'iteration': iteration,
            'hands': total_hands,
            'target_hands': int(config['total_hands']),
            'run_id': checkpoint.get('run_id'),
        },
        'continuity': {
            'model_state_present': bool(checkpoint.get('model')),
            'optimizer_state_count': len(optimizer_states),
            'optimizer_step_min': min(optimizer_steps),
            'optimizer_step_max': max(optimizer_steps),
            'resume_requires_no_reset_optimizer': True,
            'resume_requires_inherited_hand_counter': True,
            'adaptive_league_state_present': all(
                checkpoint.get(key) is not None
                for key in (
                    'adaptive_opponent_ema_rewards',
                    'adaptive_opponent_weights',
                    'adaptive_opponent_observations',
                )
            ),
        },
        'source_policy_reference': {
            'path': str(source_reference_path),
            'sha256': sha256_path(source_reference_path),
            'matches_original_resume_anchor': True,
        },
        'fixed_deal_recovery': {
            'worker_seed_base': int(config['worker_seed_base']),
            'source_deal_start_index': source_deal_start_index,
            'conservative_first_unused_deal_index': (
                conservative_first_unused_deal_index
            ),
            'deal_start_index': int(args.deal_start_index),
            'provably_above_every_prior_per_worker_cursor': True,
        },
        'opponent_pool_recovery': {
            'pool_size': pool_size,
            'snapshot_ids': pool_snapshot_ids,
            'dynamic_pool_restored_from_checkpoint': bool(pool_snapshots),
        },
        'assignment_recovery': assignment_resume,
        'replay_state_serialized': serialized_replay is not None,
        'replay_limitation': replay_limitation,
        'evidence': {
            'manifest_sha256': sha256_path(manifest_path),
            'metrics_sha256': sha256_path(metrics_path),
            'assignments_sha256': sha256_path(assignments_path),
            'metric_rows': len(metrics),
            'assignment_rows': len(assignments),
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
