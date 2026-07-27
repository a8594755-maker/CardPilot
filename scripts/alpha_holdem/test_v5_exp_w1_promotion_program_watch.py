from __future__ import annotations

import hashlib
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_exp_w1_promotion_program_watch import combined_strong


class ExpW1PromotionProgramTests(unittest.TestCase):
    def setUp(self):
        self.checkpoint = SCRIPT_DIR.parents[1] / "reports" / "test_exp_w1_promotion_checkpoint.pt"
        self.checkpoint.write_bytes(b"x")
        self.sha = hashlib.sha256(b"x").hexdigest()

    def tearDown(self):
        self.checkpoint.unlink(missing_ok=True)

    def test_strong_requires_full_pipeline_builtin_and_relative_v4_ci(self):
        pipeline = {"state": "PASS", "benchmark_result": {"artifact_audit": {"overall": "PASS"}}}
        gate = {
            "overall": "PASS",
            "decisions": {"promotion_20k_strong": True},
            "checkpoint_path": str(self.checkpoint),
        }
        relative = {"overall": "PASS", "relative_v4_pass": True}
        strong, _ = combined_strong(
            pipeline_status=pipeline,
            promotion_gate=gate,
            relative=relative,
            expected_checkpoint_sha=self.sha,
        )
        self.assertTrue(strong)
        relative["relative_v4_pass"] = False
        self.assertFalse(combined_strong(
            pipeline_status=pipeline,
            promotion_gate=gate,
            relative=relative,
            expected_checkpoint_sha=self.sha,
        )[0])

    def test_source_is_design_locked_and_greedy_direct(self):
        source = (SCRIPT_DIR / "v5_exp_w1_promotion_program_watch.py").read_text(encoding="utf-8")
        for marker in (
            "--design-lock",
            "--expected-lock-sha256",
            "lock.get('design_id') != 'EXP-W1'",
            "primary.get('decision') != 'PASS'",
            "'policy': 'greedy-direct'",
            "'priority': 'BelowNormal'",
            "'sessions': 12",
            "'hands_per_session': 1700",
            "'sessions': 20",
            "'hands_per_session': 5000",
            "relative_v4_pass",
        ):
            self.assertIn(marker, source)


if __name__ == "__main__":
    unittest.main()