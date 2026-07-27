from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_hybrid_h1_preregistration_audit as h1


PREREG = Path("reports/v5_hybrid_h1_preregistration_20260711.json")


class H1PreregistrationAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = json.loads(PREREG.read_text(encoding="utf-8"))

    def result(self, payload=None):
        return h1.audit(copy.deepcopy(payload or self.payload))

    def test_authoritative_preregistration_passes(self):
        result = self.result()
        self.assertEqual(result["status"], "PASS_REGISTERED_NO_LAUNCH")
        self.assertEqual(result["failed"], 0)

    def test_reward_scale_tamper_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["arms"]["treatment"]["fixed_effective_stack_divisor"] = 100.0
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_popart_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["arms"]["treatment"]["popart"] = True
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_shared_trunk_gradient_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["arms"]["treatment"]["value_gradient_to_shared_trunk"] = True
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_value_coefficient_tamper_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["arms"]["treatment"]["value_coef"] = 0.5
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_policy_identity_relaxation_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["cutover_invariants"]["pretraining_policy_logits_max_abs_delta"] = 1e-8
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_adaptive_extension_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["statistics"]["no_adaptive_extension"] = False
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_holdout_training_use_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["calibration_dataset"]["training_use"] = "ALLOWED"
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_official_hands_fail(self):
        payload = copy.deepcopy(self.payload)
        payload["authority"]["official_slumbot_hands"] = 5000
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_reopening_w1_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["terminal_experiment_exclusions"]["exp_w1"] = "REOPEN"
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")

    def test_launch_authority_fails(self):
        payload = copy.deepcopy(self.payload)
        payload["authority"]["control_or_treatment_launch"] = "AUTHORIZED"
        self.assertEqual(self.result(payload)["status"], "FAIL_CLOSED")


    def test_current_goal_alias_can_advance_with_ledger_authority(self):
        result = h1.audit(copy.deepcopy(self.payload), repo=Path(".").resolve())
        self.assertEqual(result["status"], "PASS_REGISTERED_NO_LAUNCH")
        chain = next(row for row in result["checks"] if row["name"] == "goal_authority_chain")
        self.assertTrue(chain["pass"])

if __name__ == "__main__":
    unittest.main()
