from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_crossplay_cycle_audit as audit


HASH = "a" * 64


def match(row: str, column: str, mean: float, lower: float, upper: float, pairs: int = 10_000):
    return {
        "row": row,
        "column": column,
        "pairs": pairs,
        "mean_bb100": mean,
        "ci_lower_bb100": lower,
        "ci_upper_bb100": upper,
        "common_deal": True,
        "seats_swapped": True,
        "policy_mode": "greedy",
        "result_path": f"reports/{row}_vs_{column}.json",
        "result_sha256": HASH,
    }


def player(identifier: str, iteration: int):
    return {
        "id": identifier,
        "iteration": iteration,
        "checkpoint_path": f"models/{identifier}.pt",
        "checkpoint_sha256": HASH,
    }


def base_payload():
    return {
        "schema_version": audit.INPUT_SCHEMA_VERSION,
        "design_id": "fixture",
        "ordered_training_snapshots": True,
        "stack_bb": 200.0,
        "policy_mode": "greedy",
        "deal_stream_id": "fixture-common-deals-v1",
        "players": [player("A", 100), player("B", 200), player("C", 300)],
    }


class CrossplayCycleAuditTest(unittest.TestCase):
    def test_supported_temporal_cycle_requires_complete_precise_matrix(self):
        payload = base_payload()
        payload["matches"] = [
                match("A", "B", 12.0, 3.0, 21.0),
                match("B", "C", 11.0, 2.0, 20.0),
                match("C", "A", 14.0, 4.0, 24.0),
            ]
        result = audit.build_audit(payload)
        self.assertEqual(result["status"], "SUPPORTED_NONTRANSITIVE_CYCLE")
        self.assertTrue(result["claims"]["nontransitivity_supported"])
        self.assertTrue(result["claims"]["temporal_self_play_cycle_supported"])
        self.assertFalse(result["claims"]["global_nonconvergence_proven"])
        self.assertFalse(result["claims"]["behavior_change_authorized"])

    def test_incomplete_matrix_cannot_prove_cycle(self):
        payload = base_payload()
        payload["matches"] = [match("A", "B", 12.0, 3.0, 21.0)]
        result = audit.build_audit(payload)
        self.assertEqual(result["status"], "INCOMPLETE_MATRIX")
        self.assertFalse(result["claims"]["temporal_self_play_cycle_supported"])

    def test_non_common_deal_match_fails_closed(self):
        bad = match("A", "B", 10.0, 1.0, 19.0)
        bad["common_deal"] = False
        payload = base_payload()
        payload["matches"] = [bad, match("A", "C", 1.0, -2.0, 4.0), match("B", "C", 1.0, -2.0, 4.0)]
        result = audit.build_audit(payload)
        self.assertEqual(result["status"], "INVALID_FAIL_CLOSED")


if __name__ == "__main__":
    unittest.main()
