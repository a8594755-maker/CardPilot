import unittest

from v5_hybrid_route_review_001 import h2_trigger, select_next


class TestRouteReview(unittest.TestCase):
    def test_h2_pass_does_not_trigger(self):
        self.assertEqual(h2_trigger({"overall": "PASS"})[0], "NOT_TRIGGERED")

    def test_h2_fail_triggers(self):
        judgment = {"overall": "FAIL", "classification": "H2_FAIL_REGISTERED_GUARD", "route_review_required": True}
        self.assertEqual(h2_trigger(judgment)[0], "TRIGGERED")

    def test_fixed_sample_inconclusive_triggers(self):
        judgment = {"overall": "INCONCLUSIVE", "classification": "H2_INCONCLUSIVE_FIXED_SAMPLE", "route_review_required": True}
        self.assertEqual(h2_trigger(judgment)[0], "TRIGGERED")

    def test_missing_evidence_is_not_terminal(self):
        judgment = {"overall": "INCONCLUSIVE", "classification": "FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE"}
        self.assertEqual(h2_trigger(judgment)[0], "WAITING_FAIL_CLOSED")

    def test_pending_h3_selects_engineering_only(self):
        selected, authorized = select_next(None)
        self.assertIn("ENGINEERING_PREREQUISITES_ONLY", selected)
        self.assertFalse(authorized)

    def test_complete_h3_bridge_allows_preregistration_only(self):
        selected, authorized = select_next({
            "overall": "PASS_H3_ACTOR_POLICY_BRIDGE_READY", "qa_complete_boards": 600,
            "exact_v55_roundtrip": True, "legal_9_action_mass_mapping": True,
        })
        self.assertIn("PREREGISTRATION", selected)
        self.assertTrue(authorized)


if __name__ == "__main__":
    unittest.main()
