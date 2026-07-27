from __future__ import annotations

import hashlib
import sys
import shutil
import uuid
import json
import tempfile
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_cutover_design_lock_verify import sha256_path, verify


@contextmanager
def workspace_fixture_dir():
    root = SCRIPT_DIR.parents[1] / "reports" / f"test_v5_cutover_lock_{uuid.uuid4().hex}"
    root.mkdir(parents=True)
    try:
        yield str(root)
    finally:
        shutil.rmtree(root, ignore_errors=False)

class CutoverDesignLockVerifyTest(unittest.TestCase):
    def test_valid_lock_passes_and_config_tamper_fails(self):
        with workspace_fixture_dir() as tmp:
            root = Path(tmp)
            checkpoint = root / 'source.pt'
            trainer = root / 'train.py'
            verifier = root / 'verify.py'
            ledger = root / 'ledger.md'
            lock_path = root / 'lock.json'
            checkpoint.write_bytes(b'checkpoint')
            trainer.write_bytes(b'trainer')
            verifier.write_bytes(b'verifier')
            prefix = b'# ledger\n'
            event_id = 'design-lock-event'
            planned = {'opponent_assignment': 'per-iteration', 'workers': 22}
            lock = {
                'schema_version': 'v5.cutover_design_lock.v1',
                'design_id': 'EXP005-C',
                'status': 'LOCKED',
                'locked_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                'source_checkpoint': {'path': str(checkpoint), 'sha256': sha256_path(checkpoint), 'iteration': 31400, 'hands': 515989661},
                'trainer_sha256': sha256_path(trainer),
                'tool_sha256': [
                    {'path': str(checkpoint), 'sha256': sha256_path(checkpoint)},
                    {'path': str(trainer), 'sha256': sha256_path(trainer)},
                    {'path': str(verifier), 'sha256': sha256_path(verifier)},
                ],
                'arms': {'control': {'run_id': 'control', 'provenance_path': str(root / 'prov.jsonl'), 'expected_config': planned}},
                'assignment_provenance': {'required': True},
                'numerical_gates': {'primary_100k_paired': {'pairs': 100000, 'alpha': 0.05, 'ci_formula': 'mean +/- 1.96*sample_sd/sqrt(n)', 'pass_ci_lower_gt_bb100': 0.0, 'max_ci_halfwidth_bb100': 15.0}, 'abort': {}},
                'rollback': {},
                'program_stop_rule': {},
                'tests': {'overall': 'PASS', 'results': [{'name': 'suite', 'status': 'PASS'}]},
                'ledger_binding': {'prefix_bytes': len(prefix), 'prefix_sha256': hashlib.sha256(prefix).hexdigest(), 'event_id': event_id},
            }
            lock_path.write_text(json.dumps(lock), encoding='utf-8')
            lock_sha = sha256_path(lock_path)
            ledger.write_bytes(prefix + f'| event {lock_sha} [event_id={event_id}] |\n'.encode())
            passed = verify(lock_path=lock_path, expected_lock_sha256=lock_sha, ledger_path=ledger,
                            source_checkpoint=checkpoint, trainer_script=trainer, new_run_id='control',
                            design_arm='control', provenance_path=root / 'prov.jsonl', planned_config=planned,
                            require_read_only=False)
            self.assertEqual(passed['overall'], 'PASS')
            failed = verify(lock_path=lock_path, expected_lock_sha256=lock_sha, ledger_path=ledger,
                            source_checkpoint=checkpoint, trainer_script=trainer, new_run_id='control',
                            design_arm='control', provenance_path=root / 'prov.jsonl',
                            planned_config={'opponent_assignment': 'per-group', 'workers': 22},
                            require_read_only=False)
            self.assertEqual(failed['overall'], 'FAIL')
            self.assertEqual(next(c for c in failed['checks'] if c['name'] == 'planned_config')['status'], 'FAIL')

    def test_exp_w1_requires_exact_single_variable(self):
        with workspace_fixture_dir() as tmp:
            root = Path(tmp)
            checkpoint = root / 'source.pt'
            trainer = root / 'train.py'
            verifier = root / 'verify.py'
            ledger = root / 'ledger.md'
            lock_path = root / 'lock.json'
            checkpoint.write_bytes(b'checkpoint')
            trainer.write_bytes(b'trainer')
            verifier.write_bytes(b'verifier')
            prefix = b'# ledger' + bytes([10])
            common = {
                'opponent_assignment': 'per-iteration',
                'workers': 22,
                'exp_w1_value_warmup_at_iteration': 31401,
                'exp_w1_value_warmup_heldout_fraction': 0.20,
                'exp_w1_value_warmup_min_relative_mse_reduction': 0.02,
                'exp_w1_value_warmup_split_seed': 2026071101,
                'exp_w1_value_warmup_report': str(root / 'warmup.json'),
            }
            control = dict(common, exp_w1_value_warmup_epochs=0)
            treatment = dict(common, exp_w1_value_warmup_epochs=8)
            event_id = 'exp-w1-lock'
            lock = {
                'schema_version': 'v5.cutover_design_lock.v1',
                'design_id': 'EXP-W1',
                'status': 'LOCKED',
                'locked_at': (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
                'source_checkpoint': {'path': str(checkpoint), 'sha256': sha256_path(checkpoint), 'iteration': 31400, 'hands': 515989661},
                'trainer_sha256': sha256_path(trainer),
                'tool_sha256': [
                    {'path': str(checkpoint), 'sha256': sha256_path(checkpoint)},
                    {'path': str(trainer), 'sha256': sha256_path(trainer)},
                    {'path': str(verifier), 'sha256': sha256_path(verifier)},
                ],
                'arms': {
                    'control': {'run_id': 'control', 'provenance_path': str(root / 'control.jsonl'), 'expected_config': control},
                    'treatment': {'run_id': 'treatment', 'provenance_path': str(root / 'treatment.jsonl'), 'expected_config': treatment},
                },
                'assignment_provenance': {'required': True},
                'method': {
                    'treatment': 'VALUE_HEAD_ONLY_FIRST_ROLLOUT_WARMUP',
                    'warmup_at_iteration': 31401,
                    'treatment_epochs': 8,
                    'control_epochs': 0,
                    'whole_hand_heldout_fraction': 0.20,
                    'minimum_relative_mse_reduction': 0.02,
                    'reward_semantics': 'UNCHANGED',
                    'policy_and_trunk_update': 'FORBIDDEN',
                    'optimizer_state': 'SOURCE_PRESERVED_VALUE_HEAD_EXTRA_STEPS_ONLY',
                },
                'route_evidence': {
                    'review_overall': 'ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION',
                    'exp_w1_eligible': True,
                    'exp_w2_eligible': False,
                    'new_behavior_authorized_by_review': False,
                    'researcher_review_sha256': 'a' * 64,
                    'preregistration_review_sha256': 'b' * 64,
                },
                'numerical_gates': {'primary_100k_paired': {'pairs': 100000, 'alpha': 0.05, 'ci_formula': 'mean +/- 1.96*sample_sd/sqrt(n)', 'pass_ci_lower_gt_bb100': 0.0, 'max_ci_halfwidth_bb100': 15.0}, 'abort': {}},
                'rollback': {},
                'program_stop_rule': {},
                'tests': {'overall': 'PASS', 'results': [{'name': 'suite', 'status': 'PASS'}]},
                'ledger_binding': {'prefix_bytes': len(prefix), 'prefix_sha256': hashlib.sha256(prefix).hexdigest(), 'event_id': event_id},
            }
            lock_path.write_text(json.dumps(lock), encoding='utf-8')
            lock_sha = sha256_path(lock_path)
            ledger.write_bytes(prefix + f'| lock {lock_sha} [event_id={event_id}] |'.encode() + bytes([10]))
            passed = verify(
                lock_path=lock_path, expected_lock_sha256=lock_sha, ledger_path=ledger,
                source_checkpoint=checkpoint, trainer_script=trainer, new_run_id='control',
                design_arm='control', provenance_path=root / 'control.jsonl',
                planned_config=control, require_read_only=False,
            )
            self.assertEqual(passed['overall'], 'PASS')
            lock['arms']['treatment']['expected_config']['lr'] = 1e-5
            lock_path.write_text(json.dumps(lock), encoding='utf-8')
            tampered_sha = sha256_path(lock_path)
            ledger.write_bytes(prefix + f'| lock {tampered_sha} [event_id={event_id}] |'.encode() + bytes([10]))
            failed = verify(
                lock_path=lock_path, expected_lock_sha256=tampered_sha, ledger_path=ledger,
                source_checkpoint=checkpoint, trainer_script=trainer, new_run_id='control',
                design_arm='control', provenance_path=root / 'control.jsonl',
                planned_config=control, require_read_only=False,
            )
            self.assertEqual(
                next(c for c in failed['checks'] if c['name'] == 'exp_w1_single_behavior_variable')['status'],
                'FAIL',
            )


if __name__ == '__main__':
    unittest.main()
