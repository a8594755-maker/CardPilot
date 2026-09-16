import random
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from scripts.alpha_holdem.train_v5 import (
    build_assignment_provenance_record,
    build_group_opponent_assignments,
    fixed_training_deck,
    restore_group_assignment_rng_from_evidence,
    sample_replay_hand_blocks,
    split_complete_hand_blocks,
    validate_stream_message,
)


def transition(*, done=False, marker=False, reward=0.0):
    scalar = np.zeros(1, dtype=np.float32)
    return (
        scalar.copy(),
        scalar.copy(),
        scalar.copy(),
        scalar.copy(),
        1,
        0.0,
        float(reward),
        0.0,
        float(done),
        1.0,
        1.0,
        float(marker),
        float('nan'),
        0,
    )


def modern_rollout():
    return [
        transition(),
        transition(done=True, marker=True, reward=1.0),
        transition(),
        transition(done=True, reward=-1.0),
        transition(done=True, marker=True, reward=0.5),
    ]


def test_split_complete_hand_blocks_keeps_self_play_trajectories_together():
    blocks = split_complete_hand_blocks(modern_rollout())
    assert [len(block) for block in blocks] == [4, 1]
    assert sum(len(block) for block in blocks) == 5
    for block in blocks:
        validate_stream_message(block)


def test_split_complete_hand_blocks_rejects_incomplete_tail():
    with pytest.raises(ValueError, match='incomplete trajectory'):
        split_complete_hand_blocks([transition()])


def test_sample_replay_uses_whole_blocks_and_is_deterministic():
    blocks = split_complete_hand_blocks(modern_rollout())
    entries = [
        {'iteration': 3, 'blocks': [blocks[0]]},
        {'iteration': 4, 'blocks': [blocks[1]]},
    ]
    first, first_info = sample_replay_hand_blocks(
        entries, target_rows=3, rng=random.Random(17)
    )
    second, second_info = sample_replay_hand_blocks(
        entries, target_rows=3, rng=random.Random(17)
    )
    assert first_info == second_info
    assert [id(row) for row in first] == [id(row) for row in second]
    assert first_info['rows'] == len(first)
    assert first_info['hands'] in (1, 2)
    assert first_info['available_rows'] == 5
    validate_stream_message(first)


def test_zero_replay_returns_no_rows_without_consuming_rng():
    rng = random.Random(23)
    state = rng.getstate()
    rows, info = sample_replay_hand_blocks([], target_rows=10, rng=rng)
    assert rows == []
    assert info['rows'] == 0
    assert rng.getstate() == state


def test_assignment_rng_resume_replays_chain_and_recovers_pending_row():
    seed = 9182
    generator = random.Random(seed)
    weights_by_iteration = {
        1: [1 / 3, 1 / 3, 1 / 3],
        2: [0.2, 0.3, 0.5],
        3: [0.4, 0.4, 0.2],
    }
    records = []
    previous_sha = None
    for iteration in (1, 2, 3):
        assignments, group_summary = build_group_opponent_assignments(
            worker_count=6,
            pool_size=3,
            group_count=3,
            self_play_fraction=1 / 3,
            rng=generator,
            pool_weights=weights_by_iteration[iteration],
        )
        record = build_assignment_provenance_record(
            run_id='resume-test',
            applies_to_iteration=iteration,
            total_hands=200 * (iteration - 1),
            assignment_mode='per-group',
            assignments=assignments.tolist(),
            pool_snapshots=[
                {'id': i, 'hands': 0, 'iteration': 0}
                for i in range(3)
            ],
            group_metadata=group_summary['groups'],
            worker_seed_base=700,
            previous_record_sha256=previous_sha,
        )
        records.append(record)
        previous_sha = record['record_sha256']
    metrics = [
        {
            'iteration': iteration,
            'adaptive_opponent_league': [
                {
                    'opponent_id': opponent_id,
                    'next_sampling_probability': probability,
                }
                for opponent_id, probability in enumerate(
                    weights_by_iteration[iteration + 1]
                )
            ],
        }
        for iteration in (1, 2)
    ]
    restored_rng = random.Random(0)
    result = restore_group_assignment_rng_from_evidence(
        records,
        metrics,
        rng=restored_rng,
        seed=seed,
        worker_count=6,
        pool_size=3,
        group_count=3,
        self_play_fraction=1 / 3,
        checkpoint_iteration=2,
        checkpoint_total_hands=400,
    )
    assert result['records_verified'] == 3
    assert result['tail_iteration'] == 3
    assert result['pending_assignments'] == [
        row['opponent']['local_index'] for row in records[-1]['workers']
    ]
    assert restored_rng.getstate() == generator.getstate()


def test_assignment_rng_resume_rejects_corrupted_hash_chain():
    assignments = [0, -1]
    record = build_assignment_provenance_record(
        run_id='resume-test',
        applies_to_iteration=1,
        total_hands=0,
        assignment_mode='per-group',
        assignments=assignments,
        pool_snapshots=[{'id': 0, 'hands': 0, 'iteration': 0}],
        group_metadata=[],
        worker_seed_base=700,
    )
    record['workers'][0]['opponent']['local_index'] = -1
    with pytest.raises(ValueError, match='record hash mismatch'):
        restore_group_assignment_rng_from_evidence(
            [record],
            [],
            rng=random.Random(0),
            seed=1,
            worker_count=2,
            pool_size=1,
            group_count=2,
            self_play_fraction=0.5,
            checkpoint_iteration=0,
            checkpoint_total_hands=0,
        )


def test_fixed_training_deal_resume_offset_prevents_deck_overlap():
    earlier = {
        tuple(fixed_training_deck(42, 0, index))
        for index in range(10)
    }
    resumed = {
        tuple(fixed_training_deck(42, 0, index))
        for index in range(10, 20)
    }
    assert earlier.isdisjoint(resumed)
