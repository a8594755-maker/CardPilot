from __future__ import annotations

import copy
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_pool_selection_measurement as measurement


def signed_design() -> dict:
    panel = [
        {"id": i, "state_sha256": f"{i:064x}"[-64:], "selection_loss": float(i), "active_at_gate31400": i < 5}
        for i in range(8)
    ]
    design = {
        "schema_version": measurement.DESIGN_SCHEMA,
        "immutable": True,
        "panel": panel,
        "measurement": {
            "pairs_per_edge": 2000,
            "seat_order": [0, 1],
            "policy_mode": measurement.POLICY_MODE,
            "starting_stack_bb": 200.0,
            "env_version": "v55",
            "no_adaptive_extension": True,
        },
        "decision_rule": {
            "meaningful_inversion_margin_bb100": 10.0,
            "familywise_alpha": 0.05,
            "multiplicity": "holm_bonferroni_active_vs_excluded",
        },
        "authority": "REPORTING_ONLY_NO_LAUNCH",
    }
    design["design_payload_sha256"] = measurement.payload_hash(design, "design_payload_sha256")
    return design


class PoolSelectionMeasurementTest(unittest.TestCase):
    def test_design_contract_accepts_exact_frozen_shape(self):
        self.assertEqual(measurement.validate_design(signed_design()), [])

    def test_design_tamper_fails_hash(self):
        design = signed_design()
        design["measurement"]["pairs_per_edge"] = 2001
        errors = measurement.validate_design(design)
        self.assertIn("design payload hash mismatch", errors)
        self.assertIn("pairs_per_edge is not frozen at 2000", errors)

    def test_supported_inversions_grant_candidate_permission_only(self):
        design = signed_design()
        edges = []
        for active in range(5):
            for excluded in range(5, 8):
                mean_a = -30.0 if excluded == 5 and active in {0, 1} else 0.0
                edges.append({"a_id": active, "b_id": excluded, "mean_a_bb100": mean_a, "se_a_bb100": 1.0})
        verdict, comparisons = measurement.classify_result(design, edges)
        self.assertEqual(verdict, "PASS_EXP007_CANDIDATE_PERMISSION_NO_LAUNCH")
        self.assertTrue(any(row["holm_reject"] for row in comparisons))


if __name__ == "__main__":
    unittest.main()
