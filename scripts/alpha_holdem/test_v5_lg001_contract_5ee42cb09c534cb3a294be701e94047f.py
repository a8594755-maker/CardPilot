#!/usr/bin/env python3
"""Zero-output deterministic contract tests for the registered LG001 implementation."""
from __future__ import annotations

import hashlib
import json
import os
import sys
import unittest
from collections import Counter
from pathlib import Path

os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
SCRIPTS = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(SCRIPTS))

import torch
import train_v5_hybrid_h1 as trainer


class LG001ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.checkpoint = torch.load(
            trainer.LG001_SOURCE_CHECKPOINT, map_location='cpu', weights_only=False,
        )
        cls.members = trainer.lg001_validate_frozen_pool(cls.checkpoint['pool_snapshots'])

    def test_registered_constants(self):
        self.assertEqual(trainer.LG001_REGISTRATION_TOKEN, '5ee42cb09c534cb3a294be701e94047f')
        self.assertEqual(trainer.LG001_ASSIGNMENT_SEED, 2026072201)
        self.assertEqual(trainer.LG001_MEMBER_ORDER, (103, 109, 115, 120, 129))
        self.assertEqual(trainer.LG001_SOURCE_HANDS, 576_021_901)
        self.assertEqual(trainer.LG001_STAGE_TARGETS, {'stage_a': 581_021_901, 'stage_b': 596_021_901})

    def test_source_and_preregistration_hashes(self):
        self.assertEqual(
            trainer.lg001_file_sha256(trainer.LG001_PREREGISTRATION_PATH),
            trainer.LG001_PREREGISTRATION_SHA256,
        )
        self.assertEqual(
            trainer.lg001_file_sha256(trainer.LG001_SOURCE_CHECKPOINT),
            trainer.LG001_SOURCE_SHA256,
        )

    def test_checkpoint_identity(self):
        self.assertEqual(self.checkpoint['iteration'], 35051)
        self.assertEqual(self.checkpoint['total_hands'], 576_021_901)
        self.assertEqual(self.checkpoint['env_version'], 'v55')
        self.assertEqual(self.checkpoint['obs_version'], 'v55')
        self.assertEqual(self.checkpoint['action_space_version'], '9slot_v5')
        self.assertIn('optimizer', self.checkpoint)

    def test_exact_frozen_members(self):
        by_id = {row['member_id']: row for row in self.members}
        self.assertEqual(tuple(by_id), trainer.LG001_MEMBER_ORDER)
        for member_id, spec in trainer.LG001_MEMBER_SPECS.items():
            self.assertEqual(by_id[member_id]['iteration'], spec['iteration'])
            self.assertEqual(by_id[member_id]['hands'], spec['hands'])
            self.assertEqual(by_id[member_id]['state_sha256'], spec['state_sha256'])

    def test_weight_vectors(self):
        self.assertEqual(trainer.LG001_SELF_WEIGHT, 0.20)
        for arm, weights in trainer.LG001_CONDITIONAL_WEIGHTS.items():
            self.assertEqual(set(weights), set(trainer.LG001_MEMBER_ORDER), arm)
            self.assertAlmostEqual(sum(weights.values()), 1.0, places=15)
            self.assertAlmostEqual(
                trainer.LG001_SELF_WEIGHT
                + (1.0 - trainer.LG001_SELF_WEIGHT) * sum(weights.values()),
                1.0, places=15,
            )

    def test_frozen_draw_vectors_and_common_random_numbers(self):
        expected = {
            1: ('15795398218888474127', 129, 129),
            35052: ('12283327240195496576', 115, 120),
            35053: ('13598814580292817450', 120, 120),
            40000: ('8085857689248910196', 109, 109),
            999999: ('12421208189863669480', 115, 120),
        }
        for iteration, (draw, control_member, treatment_member) in expected.items():
            control = trainer.lg001_select_opponent(
                'control_uniform', iteration, [], validated_members=self.members,
            )
            treatment = trainer.lg001_select_opponent(
                'treatment_diversity', iteration, [], validated_members=self.members,
            )
            self.assertEqual(control['draw_u64'], draw)
            self.assertEqual(treatment['draw_u64'], draw)
            self.assertEqual(control['member_id'], control_member)
            self.assertEqual(treatment['member_id'], treatment_member)

    def test_empirical_distribution(self):
        n = 100_000
        for arm in trainer.LG001_CONDITIONAL_WEIGHTS:
            counts = Counter()
            for iteration in range(1, n + 1):
                row = trainer.lg001_select_opponent(
                    arm, iteration, [], validated_members=self.members,
                )
                counts[row['member_id'] if row['kind'] == 'pool_snapshot' else 'self'] += 1
            self.assertLess(abs(counts['self'] / n - 0.20), 0.006)
            for member_id, conditional_weight in trainer.LG001_CONDITIONAL_WEIGHTS[arm].items():
                expected = 0.8 * conditional_weight
                self.assertLess(abs(counts[member_id] / n - expected), 0.006)

    def test_unknown_arm_and_pool_fail_closed(self):
        with self.assertRaises(ValueError):
            trainer.lg001_select_opponent('unknown', 1, [], validated_members=self.members)
        with self.assertRaises(RuntimeError):
            trainer.lg001_validate_frozen_pool(self.checkpoint['pool_snapshots'][:-1])

    def test_stage_contract(self):
        self.assertEqual(trainer.lg001_stage_for_args('control_uniform', 581_021_901), 'stage_a')
        self.assertEqual(trainer.lg001_stage_for_args('treatment_diversity', 581_021_901), 'stage_a')
        self.assertEqual(trainer.lg001_stage_for_args('treatment_diversity', 596_021_901), 'stage_b')
        with self.assertRaises(ValueError):
            trainer.lg001_stage_for_args('control_uniform', 596_021_901)

    def test_provenance_record_is_hash_chained_and_embeds_lg001(self):
        assignment = trainer.lg001_select_opponent(
            'treatment_diversity', 35052, self.checkpoint['pool_snapshots'],
            validated_members=self.members,
        )
        workers = [assignment['local_index']] * 22
        record = trainer.build_assignment_provenance_record(
            run_id='contract-test',
            applies_to_iteration=35052,
            total_hands=576_021_901,
            assignment_mode='per-iteration',
            assignments=workers,
            pool_snapshots=self.checkpoint['pool_snapshots'],
            group_metadata=None,
            worker_seed_base=73000,
            previous_record_sha256='0' * 64,
            lg001_assignment=assignment,
        )
        claimed = record.pop('record_sha256')
        canonical = json.dumps(record, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        self.assertEqual(claimed, hashlib.sha256(canonical.encode('utf-8')).hexdigest())
        self.assertEqual(record['previous_record_sha256'], '0' * 64)
        self.assertEqual(record['lg001']['member_id'], 120)
        self.assertTrue(all(row['opponent']['local_index'] == assignment['local_index'] for row in record['workers']))


if __name__ == '__main__':
    unittest.main(verbosity=2)
