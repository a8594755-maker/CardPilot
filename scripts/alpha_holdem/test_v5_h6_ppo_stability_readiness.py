from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_h6_ppo_stability_readiness as audit


class H6PPOStabilityReadinessTest(unittest.TestCase):
    def test_parser_and_registered_threshold_summary(self):
        rows = audit.parse_rows(
            "[1] hands=1,000 ent=1.2 kl=0.0200 clipfrac=0.100 r50=1 rmax=2.0\n"
            "[2] hands=2,000 ent=1.1 kl=0.0400 clipfrac=0.200 r50=1 rmax=5.0\n"
        )
        result = audit.summarize(rows)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["approx_kl"]["rows_above_threshold"], 1)
        self.assertAlmostEqual(result["approx_kl"]["fraction_above_threshold"], 0.5)

    def test_empty_log_fails_closed(self):
        with self.assertRaises(ValueError):
            audit.summarize([])


if __name__ == "__main__":
    unittest.main()
