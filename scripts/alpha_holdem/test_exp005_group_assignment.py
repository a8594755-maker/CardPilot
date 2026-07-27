#!/usr/bin/env python3
"""Focused EXP-005 group-opponent assignment invariants."""

import random
import unittest

import numpy as np

from train_v5 import (
    HERO_MODEL_ID,
    build_assignment_provenance_record,
    build_group_opponent_assignments,
    fixed_training_deck,
)


class GroupOpponentAssignmentTests(unittest.TestCase):
    def test_five_balanced_groups_one_self_play_and_distinct_pool(self):
        assignments, meta = build_group_opponent_assignments(
            worker_count=22,
            pool_size=5,
            group_count=5,
            self_play_fraction=0.2,
            rng=random.Random(20260710),
        )
        self.assertEqual(assignments.shape, (22,))
        self.assertEqual(meta['group_count'], 5)
        self.assertEqual(meta['self_play_group_count'], 1)
        self.assertIn(meta['self_play_worker_count'], (4, 5))
        self.assertEqual(meta['distinct_pool_opponents'], 4)

        sizes = sorted(len(group['workers']) for group in meta['groups'])
        self.assertEqual(sizes, [4, 4, 4, 5, 5])
        seen_workers = []
        for group in meta['groups']:
            seen_workers.extend(group['workers'])
            values = {int(assignments[w]) for w in group['workers']}
            self.assertEqual(values, {group['opponent_id']})
        self.assertEqual(sorted(seen_workers), list(range(22)))

    def test_seeded_assignment_is_reproducible(self):
        a1, m1 = build_group_opponent_assignments(22, 5, 5, 0.2, random.Random(7))
        a2, m2 = build_group_opponent_assignments(22, 5, 5, 0.2, random.Random(7))
        np.testing.assert_array_equal(a1, a2)
        self.assertEqual(m1, m2)

    def test_different_iterations_reshuffle_membership(self):
        _, m1 = build_group_opponent_assignments(22, 5, 5, 0.2, random.Random(7))
        _, m2 = build_group_opponent_assignments(22, 5, 5, 0.2, random.Random(8))
        memberships1 = [g['workers'] for g in m1['groups']]
        memberships2 = [g['workers'] for g in m2['groups']]
        self.assertNotEqual(memberships1, memberships2)

    def test_fraction_extremes(self):
        a0, m0 = build_group_opponent_assignments(10, 5, 5, 0.0, random.Random(1))
        self.assertTrue(np.all(a0 >= 0))
        self.assertEqual(m0['self_play_group_count'], 0)

        a1, m1 = build_group_opponent_assignments(10, 5, 5, 1.0, random.Random(1))
        self.assertTrue(np.all(a1 == HERO_MODEL_ID))
        self.assertEqual(m1['self_play_group_count'], 5)

    def test_invalid_inputs_fail_closed(self):
        with self.assertRaises(ValueError):
            build_group_opponent_assignments(0, 5)
        with self.assertRaises(ValueError):
            build_group_opponent_assignments(5, 0)
        with self.assertRaises(ValueError):
            build_group_opponent_assignments(5, 5, group_count=0)
        with self.assertRaises(ValueError):
            build_group_opponent_assignments(5, 5, self_play_fraction=1.1)

    def test_assignment_provenance_resolves_pool_identity_and_chains(self):
        snapshots = [
            {'id': 10, 'hands': 1000, 'iteration': 1},
            {'id': 11, 'hands': 2000, 'iteration': 2},
        ]
        first = build_assignment_provenance_record(
            run_id='arm', applies_to_iteration=3, total_hands=2000,
            assignment_mode='per-group', assignments=[HERO_MODEL_ID, 1],
            pool_snapshots=snapshots,
            group_metadata=[
                {'group_id': 0, 'workers': [0], 'opponent_id': HERO_MODEL_ID},
                {'group_id': 1, 'workers': [1], 'opponent_id': 1},
            ],
            worker_seed_base=7,
        )
        second = build_assignment_provenance_record(
            run_id='arm', applies_to_iteration=4, total_hands=2100,
            assignment_mode='per-group', assignments=[0, HERO_MODEL_ID],
            pool_snapshots=snapshots,
            group_metadata=[
                {'group_id': 0, 'workers': [0], 'opponent_id': 0},
                {'group_id': 1, 'workers': [1], 'opponent_id': HERO_MODEL_ID},
            ],
            worker_seed_base=7,
            previous_record_sha256=first['record_sha256'],
        )
        self.assertEqual(first['workers'][1]['opponent']['snapshot_id'], 11)
        self.assertEqual(second['previous_record_sha256'], first['record_sha256'])

    def test_assignment_provenance_rejects_invalid_local_pool_index(self):
        with self.assertRaises(ValueError):
            build_assignment_provenance_record(
                run_id='arm', applies_to_iteration=1, total_hands=0,
                assignment_mode='per-iteration', assignments=[2],
                pool_snapshots=[{'id': 10, 'hands': 1000, 'iteration': 1}],
            )

    def test_fixed_training_deal_stream_is_stable_and_partitioned(self):
        first = fixed_training_deck(73000, 3, 99)
        self.assertEqual(first, fixed_training_deck(73000, 3, 99))
        self.assertEqual(sorted(first), list(range(52)))
        self.assertNotEqual(first, fixed_training_deck(73000, 4, 99))
        self.assertNotEqual(first, fixed_training_deck(73000, 3, 100))


if __name__ == '__main__':
    unittest.main()
