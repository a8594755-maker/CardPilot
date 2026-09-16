import random
import sys
from pathlib import Path

import pytest
import torch

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    OpponentPool,
    build_assignment_provenance_record,
    build_group_opponent_assignments,
    reconcile_adaptive_league_state,
    restore_group_assignment_rng_from_evidence,
)


def test_reconcile_adaptive_state_tracks_snapshot_identity_not_local_index():
    rewards, observations = reconcile_adaptive_league_state(
        [10, 11, 12],
        [12, 10, 13],
        [1.5, -2.0, 0.25],
        [100, 200, 300],
    )
    assert rewards == [0.25, 1.5, 0.0]
    assert observations == [300, 100, 0]


def test_reconcile_adaptive_state_rejects_duplicate_snapshot_ids():
    with pytest.raises(ValueError, match='unique'):
        reconcile_adaptive_league_state(
            [1, 1], [1], [0.0, 0.0], [0, 0]
        )


def test_loss_kbest_keeps_seeded_anchors_and_best_learned_candidates():
    pool = OpponentPool(k=5, strategy='loss-kbest')
    state = {'weight': torch.tensor([1.0])}
    for _ in range(3):
        pool.add(state, selection_loss=0.0)
    for loss in (3.0, 1.0, 2.0):
        pool.add(state, selection_loss=loss)
    assert set(pool.active_ids()) == {0, 1, 2, 4, 5}
    assert [row['selection_loss'] for row in pool.active_metadata()] == [
        0.0,
        0.0,
        0.0,
        1.0,
        2.0,
    ]


def test_pool_resume_advances_identity_past_rejected_candidate_history():
    pool = OpponentPool(k=1, strategy='loss-kbest')
    state = {'weight': torch.tensor([1.0])}
    pool.add(state, hands=0, iteration=0, selection_loss=0.0)
    pool.add(state, hands=10, iteration=1, selection_loss=2.0)
    pool.add(state, hands=20, iteration=2, selection_loss=3.0)
    assert pool.active_ids() == [0]
    assert [row['id'] for row in pool.candidate_history] == [0, 1, 2]
    assert [row['selected'] for row in pool.candidate_history] == [True, False, False]

    resumed = OpponentPool(k=1, strategy='loss-kbest')
    resumed.load_from_checkpoint(
        pool.snapshots,
        candidate_history=pool.candidate_history,
    )
    candidate = resumed.add(
        state,
        hands=30,
        iteration=3,
        selection_loss=4.0,
    )
    assert candidate['id'] == 3
    assert [row['id'] for row in resumed.candidate_history] == [0, 1, 2, 3]


def test_pool_resume_ignores_malformed_history_ids_without_reusing_valid_ids():
    state = {'weight': torch.tensor([1.0])}
    resumed = OpponentPool(k=1, strategy='loss-kbest')
    resumed.load_from_checkpoint(
        [{
            'state_dict': state,
            'id': 2,
            'hands': 0,
            'iteration': 0,
            'selection_loss': 0.0,
        }],
        candidate_history=[
            {'id': 2, 'selected': True},
            {'id': 'bad', 'selected': False},
            {'selected': False},
            {'id': 7, 'selected': False},
        ],
    )
    assert resumed.add(state, selection_loss=1.0)['id'] == 8


def test_assignment_rng_resume_supports_dynamic_pool_membership():
    seed = 4417
    generator = random.Random(seed)
    memberships = [
        [10, 11, 12],
        [10, 11, 12, 13],
        [10, 11, 12, 13, 14],
    ]
    weights = [
        [0.2, 0.3, 0.5],
        [0.1, 0.2, 0.3, 0.4],
        [0.05, 0.10, 0.15, 0.30, 0.40],
    ]
    records = []
    previous_sha = None
    for iteration, (snapshot_ids, probabilities) in enumerate(
        zip(memberships, weights), start=1
    ):
        assignments, group_summary = build_group_opponent_assignments(
            worker_count=8,
            pool_size=len(snapshot_ids),
            group_count=4,
            self_play_fraction=0.25,
            rng=generator,
            pool_weights=probabilities,
        )
        record = build_assignment_provenance_record(
            run_id='dynamic-resume-test',
            applies_to_iteration=iteration,
            total_hands=4096 * (iteration - 1),
            assignment_mode='per-group',
            assignments=assignments.tolist(),
            pool_snapshots=[
                {'id': snapshot_id, 'hands': 0, 'iteration': 0}
                for snapshot_id in snapshot_ids
            ],
            group_metadata=group_summary['groups'],
            pool_sampling_weights=probabilities,
            worker_seed_base=900,
            previous_record_sha256=previous_sha,
        )
        records.append(record)
        previous_sha = record['record_sha256']

    restored_rng = random.Random(0)
    result = restore_group_assignment_rng_from_evidence(
        records,
        [],
        rng=restored_rng,
        seed=seed,
        worker_count=8,
        pool_size=5,
        pool_snapshot_ids=memberships[-1],
        group_count=4,
        self_play_fraction=0.25,
        checkpoint_iteration=2,
        checkpoint_total_hands=8192,
    )
    assert result['records_verified'] == 3
    assert result['pending_assignments'] == [
        row['opponent']['local_index'] for row in records[-1]['workers']
    ]
    assert restored_rng.getstate() == generator.getstate()


def test_assignment_rng_resume_rejects_wrong_tail_membership():
    generator = random.Random(9)
    assignments, group_summary = build_group_opponent_assignments(
        worker_count=4,
        pool_size=2,
        group_count=2,
        self_play_fraction=0.5,
        rng=generator,
        pool_weights=[0.5, 0.5],
    )
    record = build_assignment_provenance_record(
        run_id='membership-test',
        applies_to_iteration=1,
        total_hands=0,
        assignment_mode='per-group',
        assignments=assignments.tolist(),
        pool_snapshots=[
            {'id': 20, 'hands': 0, 'iteration': 0},
            {'id': 21, 'hands': 0, 'iteration': 0},
        ],
        group_metadata=group_summary['groups'],
        pool_sampling_weights=[0.5, 0.5],
    )
    with pytest.raises(ValueError, match='tail pool membership mismatch'):
        restore_group_assignment_rng_from_evidence(
            [record],
            [],
            rng=random.Random(0),
            seed=9,
            worker_count=4,
            pool_size=2,
            pool_snapshot_ids=[20, 99],
            group_count=2,
            self_play_fraction=0.5,
            checkpoint_iteration=0,
            checkpoint_total_hands=0,
        )


def test_consumed_assignment_can_precede_checkpoint_pool_replacement():
    seed = 29
    generator = random.Random(seed)
    assignments, group_summary = build_group_opponent_assignments(
        worker_count=4,
        pool_size=1,
        group_count=2,
        self_play_fraction=0.5,
        rng=generator,
        pool_weights=[1.0],
    )
    record = build_assignment_provenance_record(
        run_id='post-snapshot-checkpoint-test',
        applies_to_iteration=1,
        total_hands=0,
        assignment_mode='per-group',
        assignments=assignments.tolist(),
        pool_snapshots=[{'id': 10, 'hands': 0, 'iteration': 0}],
        group_metadata=group_summary['groups'],
        pool_sampling_weights=[1.0],
    )
    restored = restore_group_assignment_rng_from_evidence(
        [record],
        [],
        rng=random.Random(0),
        seed=seed,
        worker_count=4,
        pool_size=2,
        pool_snapshot_ids=[10, 11],
        group_count=2,
        self_play_fraction=0.5,
        checkpoint_iteration=1,
        checkpoint_total_hands=200,
    )
    assert restored['tail_iteration'] == 1
    assert restored['pending_assignments'] is None
