from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from train_v5 import build_assignment_provenance_record
from v5_assignment_provenance_audit import audit


class AssignmentProvenanceAuditTest(unittest.TestCase):
    def test_valid_per_group_chain_passes_and_tamper_fails(self):
        snapshots = [{'id': i + 1, 'hands': 1000 + i, 'iteration': i} for i in range(4)]
        groups = [
            {'group_id': 0, 'workers': [0], 'opponent_id': -1},
            {'group_id': 1, 'workers': [1], 'opponent_id': 0},
            {'group_id': 2, 'workers': [2], 'opponent_id': 1},
            {'group_id': 3, 'workers': [3], 'opponent_id': 2},
            {'group_id': 4, 'workers': [4], 'opponent_id': 3},
        ]
        first = build_assignment_provenance_record(
            run_id='treatment', applies_to_iteration=11, total_hands=100,
            assignment_mode='per-group', assignments=[-1, 0, 1, 2, 3],
            pool_snapshots=snapshots, group_metadata=groups, worker_seed_base=77,
        )
        second = build_assignment_provenance_record(
            run_id='treatment', applies_to_iteration=12, total_hands=200,
            assignment_mode='per-group', assignments=[-1, 0, 1, 2, 3],
            pool_snapshots=snapshots, group_metadata=groups, worker_seed_base=77,
            previous_record_sha256=first['record_sha256'],
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'assignments.jsonl'
            path.write_text('\n'.join(json.dumps(row) for row in (first, second)) + '\n', encoding='utf-8')
            passed = audit(path, expected_run_id='treatment', expected_mode='per-group',
                           expected_workers=5, expected_groups=5, expected_worker_seed_base=77,
                           expected_first_iteration=11, expected_last_iteration=12)
            self.assertEqual(passed['overall'], 'PASS')
            second['workers'][1]['opponent']['snapshot_id'] = 999
            path.write_text('\n'.join(json.dumps(row) for row in (first, second)) + '\n', encoding='utf-8')
            failed = audit(path, expected_run_id='treatment', expected_mode='per-group',
                           expected_workers=5, expected_groups=5, expected_worker_seed_base=77,
                           expected_first_iteration=11, expected_last_iteration=12)
            self.assertEqual(failed['overall'], 'FAIL')
            self.assertTrue(any('record_sha256 mismatch' in error for error in failed['errors']))


if __name__ == '__main__':
    unittest.main()
