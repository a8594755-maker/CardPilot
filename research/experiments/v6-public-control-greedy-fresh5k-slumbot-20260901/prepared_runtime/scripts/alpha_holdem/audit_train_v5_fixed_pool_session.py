"""Fail-closed audit of a completed fixed-opponent train_v5 session."""

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

from train_v5 import (
    restore_group_assignment_rng_from_evidence,
    validate_environment_hand_accounting,
)


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


def resolve_checkpoint(path_text: str, workspace: Path) -> Path:
    path = Path(path_text)
    if not path.is_absolute():
        path = workspace / path
    return path.resolve()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--expected-target-hands', type=int, required=True)
    parser.add_argument('--expected-target-environment-hands', type=int, default=0)
    parser.add_argument('--expected-final-iteration', type=int, required=True)
    parser.add_argument('--expected-pool-size', type=int, required=True)
    parser.add_argument('--expected-archive-every', type=int, required=True)
    parser.add_argument('--expected-normalization', required=True)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    workspace = args.workspace.resolve()
    paths = {
        'checkpoint': run_dir / 'latest.pt',
        'manifest': run_dir / 'run_manifest.json',
        'metrics': run_dir / 'h1_training_metrics.jsonl',
        'assignments': run_dir / 'opponent_assignments.jsonl',
        'train_log': run_dir / 'latest_train.log',
    }
    for path in paths.values():
        if not path.is_file():
            raise FileNotFoundError(path)

    checkpoint = torch.load(
        paths['checkpoint'], map_location='cpu', weights_only=False
    )
    manifest = json.loads(paths['manifest'].read_text(encoding='utf-8'))
    metrics = load_jsonl(paths['metrics'])
    assignments = load_jsonl(paths['assignments'])
    config = checkpoint.get('config') or {}

    if config.get('pool_strategy') != 'latest':
        raise RuntimeError('checkpoint does not use the fixed-pool latest strategy')
    if int(config.get('save_interval', -1)) != 1:
        raise RuntimeError('save interval is not one')
    if int(config.get('archive_checkpoint_every', -1)) != args.expected_archive_every:
        raise RuntimeError('archive cadence differs from preregistration')
    if config.get('policy_advantage_normalization') != args.expected_normalization:
        raise RuntimeError('checkpoint normalization differs from preregistration')

    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    iterations = [int(row['iteration']) for row in metrics]
    hands = [int(row['hands']) for row in metrics]
    if iterations != expected_iterations:
        raise RuntimeError('training metric iterations are not exactly contiguous')
    if any(right <= left for left, right in zip(hands, hands[1:])):
        raise RuntimeError('training hand counter is not strictly increasing')
    if any(
        row.get('policy_advantage_normalization') != args.expected_normalization
        for row in metrics
    ):
        raise RuntimeError('metric normalization changed during the session')
    if any(row.get('run_id') != checkpoint.get('run_id') for row in metrics):
        raise RuntimeError('metric run identity changed during the session')

    final_hands = hands[-1]
    final_iteration = iterations[-1]
    if args.expected_target_environment_hands <= 0 and final_hands < args.expected_target_hands:
        raise RuntimeError('final transition-bearing hands are below legacy target')
    for source, label in ((checkpoint, 'checkpoint'), (manifest, 'manifest')):
        if int(source.get('total_hands', -1)) != final_hands:
            raise RuntimeError(f'{label}/metric final hand mismatch')
        if int(source.get('iteration', -1)) != final_iteration:
            raise RuntimeError(f'{label}/metric final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('run manifest is not terminal finished')

    environment_accounting = checkpoint.get('environment_hand_accounting')
    if environment_accounting is not None:
        validate_environment_hand_accounting(environment_accounting)
        manifest_accounting = manifest.get('environment_hand_accounting') or {}
        validate_environment_hand_accounting(manifest_accounting)
        for field in ('completed_hands', 'no_trainable_decision_hands', 'prefix_complete'):
            if environment_accounting[field] != manifest_accounting[field]:
                raise RuntimeError(f'checkpoint/manifest environment accounting mismatch: {field}')
        physical_rows = [row['environment_hand_accounting'] for row in metrics
                         if row.get('environment_hand_accounting') is not None]
        for row in physical_rows:
            validate_environment_hand_accounting(row)
        physical_counts = [int(row['completed_hands']) for row in physical_rows]
        if any(right < left for left, right in zip(physical_counts, physical_counts[1:])):
            raise RuntimeError('physical environment counter decreased')
        if physical_counts and physical_counts[-1] > int(environment_accounting['completed_hands']):
            raise RuntimeError('final checkpoint physical count is behind metrics')
    if args.expected_target_environment_hands > 0:
        if int(config.get('total_environment_hands', 0)) != args.expected_target_environment_hands:
            raise RuntimeError('configured physical target differs from preregistration')
        if not environment_accounting or not environment_accounting['prefix_complete']:
            raise RuntimeError('physical target has no complete environment-hand prefix')
        if int(environment_accounting['completed_hands']) < args.expected_target_environment_hands:
            raise RuntimeError('physical completed-environment hands are below target')

    final_pool = checkpoint.get('pool_snapshots') or []
    final_pool_ids = [int(row['id']) for row in final_pool]
    if len(final_pool) != args.expected_pool_size:
        raise RuntimeError('unexpected final fixed-pool size')
    if len(final_pool_ids) != len(set(final_pool_ids)):
        raise RuntimeError('fixed-pool ids are not unique')
    if any(
        (row.get('score_components') or {}).get('kind')
        != 'fixed_external_opponent'
        for row in final_pool
    ):
        raise RuntimeError('pool contains a non-fixed opponent')

    configured_paths = [
        resolve_checkpoint(value, workspace)
        for value in config.get('fixed_opponent_checkpoints') or []
    ]
    pool_paths = [
        resolve_checkpoint(
            str((row.get('score_components') or {}).get('checkpoint', '')),
            workspace,
        )
        for row in final_pool
    ]
    if configured_paths != pool_paths:
        raise RuntimeError('fixed-pool membership/order differs from configuration')
    fixed_opponents = []
    for path, row in zip(pool_paths, final_pool):
        if not path.is_file():
            raise FileNotFoundError(path)
        actual_sha256 = sha256_path(path)
        recorded_sha256 = str(
            (row.get('score_components') or {}).get('checkpoint_sha256', '')
        )
        if actual_sha256 != recorded_sha256:
            raise RuntimeError(f'fixed opponent hash mismatch: {path}')
        fixed_opponents.append({
            'snapshot_id': int(row['id']),
            'path': str(path),
            'bytes': path.stat().st_size,
            'sha256': actual_sha256,
        })

    if len(assignments) != final_iteration:
        raise RuntimeError('assignment evidence does not cover every iteration')
    membership_by_iteration = [
        [int(ref['snapshot_id']) for ref in row.get('pool_snapshot_refs', [])]
        for row in assignments
    ]
    if any(ids != final_pool_ids for ids in membership_by_iteration):
        raise RuntimeError('fixed-pool membership changed during the session')
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

    candidate_history = checkpoint.get('pool_candidate_history') or []
    if len(candidate_history) != args.expected_pool_size:
        raise RuntimeError('fixed pool unexpectedly accumulated candidates')
    adaptive_rewards = checkpoint.get('adaptive_opponent_ema_rewards') or []
    adaptive_weights = checkpoint.get('adaptive_opponent_weights') or []
    adaptive_observations = checkpoint.get('adaptive_opponent_observations') or []
    if [len(adaptive_rewards), len(adaptive_weights), len(adaptive_observations)] != [
        args.expected_pool_size
    ] * 3:
        raise RuntimeError('adaptive state does not match fixed-pool membership')
    if abs(sum(float(value) for value in adaptive_weights) - 1.0) > 1e-9:
        raise RuntimeError('adaptive opponent weights do not sum to one')

    optimizer_states = (checkpoint.get('optimizer') or {}).get('state') or {}
    if not optimizer_states:
        raise RuntimeError('optimizer state is empty')
    optimizer_steps = []
    for state in optimizer_states.values():
        step = state.get('step', 0)
        optimizer_steps.append(int(step.item() if hasattr(step, 'item') else step))

    expected_archive_iterations = (
        list(
            range(
                args.expected_archive_every,
                final_iteration + 1,
                args.expected_archive_every,
            )
        )
        if args.expected_archive_every > 0
        else []
    )
    archive_rows = []
    checkpoint_dir = run_dir / 'checkpoints'
    archive_paths = sorted(
        checkpoint_dir.glob('checkpoint_iter*_hands*.pt')
    ) if checkpoint_dir.is_dir() else []
    for archive_path in archive_paths:
        match = ARCHIVE_RE.match(archive_path.name)
        if match is None:
            raise RuntimeError(f'invalid archive filename: {archive_path.name}')
        archive_iteration = int(match.group('iteration'))
        archive_hands = int(match.group('hands'))
        archive = torch.load(archive_path, map_location='cpu', weights_only=False)
        if int(archive.get('iteration', -1)) != archive_iteration:
            raise RuntimeError('archive filename/internal iteration mismatch')
        if int(archive.get('total_hands', -1)) != archive_hands:
            raise RuntimeError('archive filename/internal hand mismatch')
        if hands[archive_iteration - 1] != archive_hands:
            raise RuntimeError('archive/metric hand boundary mismatch')
        if archive.get('run_id') != checkpoint.get('run_id'):
            raise RuntimeError('archive run identity mismatch')
        if archive.get('pool_strategy') != 'latest':
            raise RuntimeError('archive pool strategy mismatch')
        archive_pool_ids = [int(row['id']) for row in archive.get('pool_snapshots') or []]
        if archive_pool_ids != final_pool_ids:
            raise RuntimeError('archive fixed-pool membership mismatch')
        archive_rows.append({
            'iteration': archive_iteration,
            'hands': archive_hands,
            'path': str(archive_path),
            'bytes': archive_path.stat().st_size,
            'sha256': sha256_path(archive_path),
        })
    if [row['iteration'] for row in archive_rows] != expected_archive_iterations:
        raise RuntimeError('archive checkpoint set differs from configured cadence')

    result = {
        'schema': 'cardpilot.train_v5.fixed_pool_session_audit.v2',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': final_iteration,
        'legacy_training_marker_hands': final_hands,
        'target_training_marker_hands': int(args.expected_target_hands),
        'actual_environment_hands': (
            int(environment_accounting['completed_hands'])
            if environment_accounting and environment_accounting['prefix_complete'] else None
        ),
        'target_environment_hands': int(args.expected_target_environment_hands) or None,
        'environment_hand_accounting': environment_accounting,
        'metric_rows': len(metrics),
        'assignment_rows': len(assignments),
        'assignment_audit': assignment_audit,
        'fixed_opponents': fixed_opponents,
        'pool_snapshot_ids': final_pool_ids,
        'candidate_history_rows': len(candidate_history),
        'adaptive_state_lengths': {
            'ema_rewards': len(adaptive_rewards),
            'weights': len(adaptive_weights),
            'observations': len(adaptive_observations),
        },
        'optimizer_state_count': len(optimizer_states),
        'optimizer_step_min': min(optimizer_steps),
        'optimizer_step_max': max(optimizer_steps),
        'normalization': args.expected_normalization,
        'kl_early_stop_count': sum(
            bool(row.get('kl_early_stop_triggered')) for row in metrics
        ),
        'max_reference_policy_kl': max(
            float(row.get('reference_policy_kl', 0.0)) for row in metrics
        ),
        'max_clip_fraction': max(float(row.get('clip_frac', 0.0)) for row in metrics),
        'archives': archive_rows,
        'artifact_integrity': {
            name: {'bytes': path.stat().st_size, 'sha256': sha256_path(path)}
            for name, path in paths.items()
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(
        json.dumps(result, indent=2, sort_keys=True) + '\n', encoding='utf-8'
    )
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
