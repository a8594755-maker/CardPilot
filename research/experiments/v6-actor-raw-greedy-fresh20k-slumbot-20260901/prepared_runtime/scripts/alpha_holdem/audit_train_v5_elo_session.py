"""Fail-closed audit of a completed train_v5 elo-kbest session."""

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
    elo_match_seed,
    hash_chained_elo_records,
    restore_group_assignment_rng_from_evidence,
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--run-dir', type=Path, required=True)
    parser.add_argument('--expected-target-hands', type=int, required=True)
    parser.add_argument('--expected-final-iteration', type=int, required=True)
    parser.add_argument('--expected-initial-pool-size', type=int, required=True)
    parser.add_argument('--expected-final-pool-size', type=int, required=True)
    parser.add_argument('--expected-snapshot-every', type=int, required=True)
    parser.add_argument('--expected-tournament-pairs', type=int, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    paths = {
        'checkpoint': run_dir / 'latest.pt',
        'manifest': run_dir / 'run_manifest.json',
        'metrics': run_dir / 'h1_training_metrics.jsonl',
        'assignments': run_dir / 'opponent_assignments.jsonl',
        'elo_tournaments': run_dir / 'elo_tournaments.jsonl',
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
    elo_records = load_jsonl(paths['elo_tournaments'])
    checkpoint_history = checkpoint.get('elo_tournament_history') or []
    config = checkpoint.get('config') or {}

    if config.get('pool_strategy') != 'elo-kbest':
        raise RuntimeError('checkpoint is not an elo-kbest run')
    if int(config.get('save_interval', -1)) != 1:
        raise RuntimeError('elo-kbest save interval is not one')
    if int(config.get('snapshot_every', -1)) != args.expected_snapshot_every:
        raise RuntimeError('unexpected snapshot cadence')
    if int(config.get('elo_tournament_pairs', -1)) != args.expected_tournament_pairs:
        raise RuntimeError('unexpected tournament pair count')

    expected_iterations = list(range(1, args.expected_final_iteration + 1))
    iterations = [int(row['iteration']) for row in metrics]
    hands = [int(row['hands']) for row in metrics]
    if iterations != expected_iterations:
        raise RuntimeError('training metric iterations are not exactly contiguous')
    if any(right <= left for left, right in zip(hands, hands[1:])):
        raise RuntimeError('training hand counter is not strictly increasing')
    final_hands = hands[-1]
    final_iteration = iterations[-1]
    if final_hands < args.expected_target_hands:
        raise RuntimeError('actual final hands are below target')
    for source, label in ((checkpoint, 'checkpoint'), (manifest, 'manifest')):
        if int(source.get('total_hands', -1)) != final_hands:
            raise RuntimeError(f'{label}/metric final hand mismatch')
        if int(source.get('iteration', -1)) != final_iteration:
            raise RuntimeError(f'{label}/metric final iteration mismatch')
    if manifest.get('status') != 'finished':
        raise RuntimeError('run manifest is not terminal finished')

    if len(assignments) != final_iteration:
        raise RuntimeError('assignment evidence does not cover every iteration')
    terminal_assignment_ids = [
        int(row['snapshot_id'])
        for row in assignments[-1].get('pool_snapshot_refs', [])
    ]
    assignment_audit = restore_group_assignment_rng_from_evidence(
        assignments,
        metrics,
        rng=random.Random(0),
        seed=int(config['seed']),
        worker_count=int(config['workers']),
        pool_size=len(terminal_assignment_ids),
        pool_snapshot_ids=terminal_assignment_ids,
        group_count=int(config['opponent_groups']),
        self_play_fraction=float(config['self_play_fraction']),
        checkpoint_iteration=final_iteration,
        checkpoint_total_hands=final_hands,
    )
    if assignment_audit['tail_iteration'] != final_iteration:
        raise RuntimeError('terminal assignment tail is not the final iteration')
    if assignment_audit['pending_assignments'] is not None:
        raise RuntimeError('terminal run has an unused pending assignment')

    expected_tournaments = final_iteration // args.expected_snapshot_every
    if len(checkpoint_history) != expected_tournaments:
        raise RuntimeError('checkpoint tournament count is incomplete')
    expected_records = hash_chained_elo_records(checkpoint_history)
    if elo_records != expected_records:
        raise RuntimeError('JSONL tournament evidence differs from checkpoint history')

    previous_selected = [
        int(row['snapshot_id'])
        for row in assignments[0].get('pool_snapshot_refs', [])
    ]
    if len(previous_selected) != args.expected_initial_pool_size:
        raise RuntimeError('unexpected initial pool size in assignment evidence')
    tournament_eval_hands = 0
    membership_changes = []
    for expected_index, tournament in enumerate(checkpoint_history, start=1):
        if int(tournament.get('tournament_index', -1)) != expected_index:
            raise RuntimeError('tournament indices are not contiguous')
        if int(tournament.get('total_ood_nodes', -1)) != 0:
            raise RuntimeError('tournament contains OOD decisions')
        if [int(value) for value in tournament['active_ids_before']] != previous_selected:
            raise RuntimeError('tournament input membership chain mismatch')
        competitors = tournament.get('competitors') or []
        competitor_ids = [int(row['id']) for row in competitors]
        candidate_id = int(tournament['candidate_id'])
        if competitor_ids != sorted(previous_selected + [candidate_id]):
            raise RuntimeError('tournament competitor identity mismatch')
        matches = tournament.get('matches') or []
        expected_match_count = len(competitor_ids) * (len(competitor_ids) - 1) // 2
        if len(matches) != expected_match_count:
            raise RuntimeError('tournament round robin is incomplete')
        seen_pairs = []
        for match in matches:
            a_id = int(match['competitor_a_id'])
            b_id = int(match['competitor_b_id'])
            seen_pairs.append((a_id, b_id))
            if int(match['pairs']) != args.expected_tournament_pairs:
                raise RuntimeError('match pair count differs from preregistration')
            if int(match['seed']) != elo_match_seed(
                int(tournament['base_seed']), expected_index, a_id, b_id
            ):
                raise RuntimeError('match seed is not reproducible')
            outcomes = (
                int(match['a_pair_wins'])
                + int(match['pair_draws'])
                + int(match['a_pair_losses'])
            )
            if outcomes != args.expected_tournament_pairs:
                raise RuntimeError('match outcome accounting is incomplete')
            if int(match.get('ood_nodes', -1)) != 0:
                raise RuntimeError('match contains OOD decisions')
        expected_pairs = [
            (competitor_ids[left], competitor_ids[right])
            for left in range(len(competitor_ids))
            for right in range(left + 1, len(competitor_ids))
        ]
        if seen_pairs != expected_pairs:
            raise RuntimeError('round-robin match ordering differs from contract')
        eval_hands = int(tournament['evaluation_hands'])
        if eval_hands != expected_match_count * args.expected_tournament_pairs * 2:
            raise RuntimeError('tournament evaluation-hand accounting mismatch')
        tournament_eval_hands += eval_hands
        selected = [int(value) for value in tournament['selected_ids']]
        if len(selected) != min(args.expected_final_pool_size, len(competitor_ids)):
            raise RuntimeError('tournament survivor count mismatch')
        if len(selected) != len(set(selected)) or not set(selected) <= set(competitor_ids):
            raise RuntimeError('tournament survivor identities are invalid')
        ratings = {int(key): float(value) for key, value in tournament['ratings'].items()}
        removed = set(competitor_ids) - set(selected)
        if removed and min(ratings[value] for value in selected) < max(
            ratings[value] for value in removed
        ) - 1e-12:
            raise RuntimeError('survivor set is not rating-maximal')
        if selected != previous_selected:
            membership_changes.append({
                'tournament_index': expected_index,
                'from_snapshot_ids': previous_selected,
                'to_snapshot_ids': selected,
            })
        previous_selected = selected

    final_pool = checkpoint.get('pool_snapshots') or []
    final_pool_ids = [int(row['id']) for row in final_pool]
    if len(final_pool_ids) != args.expected_final_pool_size:
        raise RuntimeError('unexpected final pool size')
    if final_pool_ids != previous_selected:
        raise RuntimeError('checkpoint pool differs from terminal tournament survivors')
    final_ratings = {
        int(key): float(value)
        for key, value in checkpoint_history[-1]['ratings'].items()
    }
    for snapshot in final_pool:
        expected_rating = final_ratings[int(snapshot['id'])]
        if abs(float(snapshot['selection_score']) - expected_rating) > 1e-12:
            raise RuntimeError(
                f'checkpoint rating mismatch for snapshot {snapshot["id"]}: '
                f'{snapshot["selection_score"]} != {expected_rating}'
            )
    if int(checkpoint.get('elo_tournament_evaluation_hands', -1)) != tournament_eval_hands:
        raise RuntimeError('checkpoint cumulative tournament hand count mismatch')

    candidate_history = checkpoint.get('pool_candidate_history') or []
    if len(candidate_history) != args.expected_initial_pool_size + expected_tournaments:
        raise RuntimeError('candidate history does not cover every seed/snapshot')
    adaptive_lengths = [
        len(checkpoint.get(key) or [])
        for key in (
            'adaptive_opponent_ema_rewards',
            'adaptive_opponent_weights',
            'adaptive_opponent_observations',
        )
    ]
    if adaptive_lengths != [len(final_pool)] * 3:
        raise RuntimeError('adaptive state does not match final pool membership')

    optimizer_states = (checkpoint.get('optimizer') or {}).get('state') or {}
    if not optimizer_states:
        raise RuntimeError('optimizer state is empty')

    archive_interval = int(config.get('archive_checkpoint_every', 0))
    expected_archive_iterations = (
        list(range(archive_interval, final_iteration + 1, archive_interval))
        if archive_interval > 0
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
        archive_checkpoint = torch.load(
            archive_path, map_location='cpu', weights_only=False
        )
        if int(archive_checkpoint.get('iteration', -1)) != archive_iteration:
            raise RuntimeError('archive filename/internal iteration mismatch')
        if int(archive_checkpoint.get('total_hands', -1)) != archive_hands:
            raise RuntimeError('archive filename/internal hand mismatch')
        if hands[archive_iteration - 1] != archive_hands:
            raise RuntimeError('archive/metric hand boundary mismatch')
        if archive_checkpoint.get('run_id') != checkpoint.get('run_id'):
            raise RuntimeError('archive run identity mismatch')
        if archive_checkpoint.get('pool_strategy') != 'elo-kbest':
            raise RuntimeError('archive pool strategy mismatch')
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
        'schema': 'cardpilot.train_v5.elo_session_audit.v1',
        'status': 'PASS',
        'run_id': checkpoint.get('run_id'),
        'final_iteration': final_iteration,
        'actual_environment_hands': final_hands,
        'target_environment_hands': int(args.expected_target_hands),
        'metric_rows': len(metrics),
        'assignment_rows': len(assignments),
        'assignment_audit': assignment_audit,
        'initial_pool_snapshot_ids': [
            int(row['snapshot_id'])
            for row in assignments[0].get('pool_snapshot_refs', [])
        ],
        'terminal_training_assignment_snapshot_ids': terminal_assignment_ids,
        'final_pool_snapshot_ids': final_pool_ids,
        'candidate_history_rows': len(candidate_history),
        'tournament_count': len(checkpoint_history),
        'tournament_evaluation_hands': tournament_eval_hands,
        'total_ood_nodes': sum(
            int(row['total_ood_nodes']) for row in checkpoint_history
        ),
        'membership_changes': membership_changes,
        'optimizer_state_count': len(optimizer_states),
        'archives': archive_rows,
        'artifact_integrity': {
            name: {
                'bytes': path.stat().st_size,
                'sha256': sha256_path(path),
            }
            for name, path in paths.items()
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
