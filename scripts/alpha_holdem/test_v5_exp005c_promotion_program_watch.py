import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from v5_exp005c_promotion_program_watch import combined_strong


class PromotionProgramTests(unittest.TestCase):
    def test_strong_requires_pipeline_builtin_and_relative(self):
        with tempfile.TemporaryDirectory() as td:
            checkpoint = Path(td) / 'c.pt'; checkpoint.write_bytes(b'x')
            import hashlib
            sha = hashlib.sha256(b'x').hexdigest()
            pipeline = {'state': 'PASS', 'benchmark_result': {'artifact_audit': {'overall': 'PASS'}}}
            gate = {'overall': 'PASS', 'decisions': {'promotion_20k_strong': True}, 'checkpoint_path': str(checkpoint)}
            relative = {'overall': 'PASS', 'relative_v4_pass': True}
            self.assertTrue(combined_strong(pipeline_status=pipeline, promotion_gate=gate, relative=relative, expected_checkpoint_sha=sha)[0])
            relative['relative_v4_pass'] = False
            self.assertFalse(combined_strong(pipeline_status=pipeline, promotion_gate=gate, relative=relative, expected_checkpoint_sha=sha)[0])

    def test_built_in_false_blocks_formal(self):
        with tempfile.TemporaryDirectory() as td:
            checkpoint = Path(td) / 'c.pt'; checkpoint.write_bytes(b'x')
            import hashlib
            sha = hashlib.sha256(b'x').hexdigest()
            strong, blockers = combined_strong(
                pipeline_status={'state': 'PASS', 'benchmark_result': {'artifact_audit': {'overall': 'PASS'}}},
                promotion_gate={'overall': 'PASS', 'decisions': {'promotion_20k_strong': False}, 'checkpoint_path': str(checkpoint)},
                relative={'overall': 'PASS', 'relative_v4_pass': True}, expected_checkpoint_sha=sha)
            self.assertFalse(strong)
            self.assertIn('built-in promotion_20k_strong false', blockers)

    def test_source_contract_gates_launch_and_pins_policy(self):
        source = Path(__file__).with_name('v5_exp005c_promotion_program_watch.py').read_text(encoding='utf-8')
        self.assertIn("primary.get('decision') != 'PASS'", source)
        self.assertIn("'policy': 'greedy-direct'", source)
        self.assertIn("'priority': 'BelowNormal'", source)
        self.assertIn("'sessions': 12", source)
        self.assertIn("'hands_per_session': 1700", source)
        self.assertIn("'sessions': 20", source)
        self.assertIn("'hands_per_session': 5000", source)
        self.assertIn("if not strong:", source)
        self.assertIn("'--policy-mode', 'greedy'", source)
        self.assertNotIn("'--no-direct-low-priority'", source)


if __name__ == '__main__':
    unittest.main()
