from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_h5_resolver_readiness_audit as audit


class H5ResolverReadinessAuditTest(unittest.TestCase):
    def test_current_shape_fails_closed(self):
        result = audit.analyze_sources(
            "srp_50bb srp_100bb 3bet_50bb 3bet_100bb",
            "def play_hand(): pass",
            "PIPELINE_SRP_V3_200BB_CONFIG",
            [{"pass": True}, {"pass": True}],
        )
        self.assertEqual(result["overall"], "FAIL_CLOSED_H5_PREREQUISITES_INCOMPLETE")
        self.assertFalse(result["gates"]["exact_200bb_realtime_scenario"])
        self.assertFalse(result["gates"]["slumbot_harness_integration"])

    def test_typecheck_failure_is_terminal_readiness_failure(self):
        result = audit.analyze_sources(
            "srp_200bb 3bet_200bb limp 4bet",
            "resolver integration",
            "PIPELINE_SRP_V3_200BB_CONFIG",
            [{"pass": False}],
        )
        self.assertFalse(result["gates"]["typescript_typechecks_pass"])
        self.assertEqual(result["overall"], "FAIL_CLOSED_H5_PREREQUISITES_INCOMPLETE")


if __name__ == "__main__":
    unittest.main()
