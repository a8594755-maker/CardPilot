from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_poker_research_review as review


def loss_artifact():
    return {
        "schema_version": "v5.loss_inference.audit.v1",
        "status": "PASS_DESCRIPTIVE_INFERENCE_AUDIT",
        "multiplicity_controlled_associations": [{"dimension": "terminal", "key": "hero_fold"}],
    }


def value_artifact():
    return {
        "status": "COMPLETED_REPORTING_ONLY",
        "decision": {
            "decision": "SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM",
            "route_pivot_exp_w1_eligible": True,
            "exp_w1_registration_authorized_now": False,
        },
    }


class PokerResearchReviewTest(unittest.TestCase):
    def test_descriptive_loss_does_not_authorize_action_tuning(self):
        result = review.build_review(loss=loss_artifact(), value=value_artifact())
        self.assertTrue(result["permissions"]["may_localize_loss"])
        self.assertFalse(result["permissions"]["may_claim_action_leak_causal"])
        self.assertFalse(result["permissions"]["may_register_action_specific_intervention"])
        self.assertFalse(result["permissions"]["route_pivot_exp_w1_eligible"])
        self.assertEqual(result["overall"], "CONTINUE_REGISTERED_PROGRAM_NO_NEW_BEHAVIOR_DECISION")

    def test_program_stop_unlocks_supported_w1_route_but_not_launch(self):
        result = review.build_review(
            loss=loss_artifact(),
            value=value_artifact(),
            asset={"status": "COMPLETED_REPORTING_ONLY", "decision": {"decision": "NO_COMPATIBLE_FULL_200BB_ASSET", "route_pivot_exp_w2_eligible": False}},
            program_state="EXP005C_FAIL_PROTOCOL_ABORT",
        )
        self.assertTrue(result["permissions"]["route_pivot_exp_w1_eligible"])
        self.assertFalse(result["permissions"]["route_pivot_exp_w2_eligible"])
        self.assertFalse(result["permissions"]["new_behavior_change_authorized_by_this_review"])
        self.assertEqual(result["overall"], "ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION")

    def test_incomplete_value_artifact_fails_closed(self):
        result = review.build_review(
            value={"decision": {"decision": "SUPPORTS_CRITIC_OR_REWARD_SCALE_PROBLEM", "route_pivot_exp_w1_eligible": True}},
            program_state="EXP005C_FAIL_PROTOCOL_ABORT",
        )
        self.assertFalse(result["permissions"]["route_pivot_exp_w1_eligible"])

    def test_protocol_abort_is_valid_ops_evidence_not_poker_effect(self):
        method = {
            "schema_version": "v5.exp005c.protocol_failure.v1",
            "immutable": True,
            "classification": "EXP005C_FAIL_PROTOCOL_ABORT",
            "design_lock": {
                "sha256": "2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007",
                "expected_sha256": "2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007",
            },
            "registered_gate": {"minimum_rows": 60, "abort_ratio_below": 0.85},
            "first_60_rows": {
                "control": {"row_count": 60},
                "treatment": {"row_count": 60},
                "treatment_over_control_ratio": 0.4141816,
                "threshold": 0.85,
                "gate_result": "FAIL",
            },
            "protocol_effect": {
                "authoritative_method_classification": "EXP005C_FAIL_PROTOCOL_ABORT",
                "classification": "POST_PROTOCOL_EXPLORATORY_ONLY",
            },
        }
        result = review.build_review(method=method, program_state="EXP005C_FAIL_PROTOCOL_ABORT")
        method_row = result["evidence_matrix"]["method_experiment"]
        self.assertEqual(method_row["status"], "VALID_PROTOCOL_ABORT")
        self.assertEqual(method_row["inference_scope"], "REGISTERED_PROTOCOL_ABORT_NO_POKER_EFFECT_ESTIMATE")
        self.assertFalse(method_row["single_model_candidate_decision_authorized"])
        self.assertFalse(method_row["general_method_claim_authorized"])

    def test_only_validated_counterfactual_artifact_supports_action_intervention(self):
        action_regret = {
            "schema_version": review.ACTION_REGRET_SCHEMA,
            "status": "PASS",
            "counterfactual_estimator_validated": True,
            "same_information_state": True,
            "legal_action_coverage_complete": True,
            "selection_preregistered": True,
            "uncertainty_validated": True,
            "identity_bound": True,
            "source_bundle_hash_verified": True,
            "artifact_audit": "PASS",
            "opponent_continuation_scope": "frozen_internal_policy",
            "rows": [{"state": "fixture", "regret_ci_lower_bb": 0.1}],
        }
        result = review.build_review(loss=loss_artifact(), action_regret=action_regret)
        self.assertTrue(result["permissions"]["may_claim_action_leak_causal"])
        self.assertTrue(result["permissions"]["may_register_action_specific_intervention"])
        self.assertFalse(result["permissions"]["new_behavior_change_authorized_by_this_review"])

    def test_single_seed_method_pass_is_conditioned_not_general(self):
        method = {
            "classification": "PASS",
            "same_start_controlled": True,
            "common_deal_endpoint_evaluation": True,
            "independent_training_seeds": 1,
        }
        result = review.build_review(method=method)
        method_row = result["evidence_matrix"]["method_experiment"]
        self.assertEqual(method_row["inference_scope"], "CONDITIONAL_SINGLE_SEED_METHOD_EFFECT")
        self.assertTrue(method_row["single_model_candidate_decision_authorized"])
        self.assertFalse(method_row["general_method_claim_authorized"])

    def test_formal_numbers_without_bundle_cannot_claim_strength(self):
        official = {
            "official": True,
            "evidence_class": "formal100k_official_greedy_direct",
            "result": {"hands": 100_000, "bb_per_100": 5.0, "ci_lower": 1.0, "ci_upper": 9.0},
        }
        result = review.build_review(official=official)
        self.assertFalse(result["permissions"]["may_claim_l5"])
        self.assertEqual(result["evidence_matrix"]["official_strength"]["status"], "MISSING_OR_INVALID")

    def test_valid_frozen_opponent_panel_is_generalization_not_slumbot_strength(self):
        panel = {
            "schema_version": review.OPPONENT_PANEL_SCHEMA,
            "status": "PASS",
            "full_hand_200bb": True,
            "policy_mode": "greedy",
            "selection_preregistered": True,
            "adaptive_opponent_selection": False,
            "identity_and_ci_audited": True,
            "opponents": ["historical", "aggressive", "passive"],
        }
        result = review.build_review(opponent_panel=panel)
        self.assertTrue(result["permissions"]["may_claim_general_200bb_panel_performance"])
        self.assertFalse(result["permissions"]["may_claim_l5"])


    def w1_failure_artifact(self):
        return {
            "schema_version": review.EXP_W1_FAILURE_SCHEMA,
            "immutable": True,
            "classification": "EXP_W1_FAIL_WARMUP_GATE",
            "program_stop": "FREEZE_TIER2_NO_2_7B_INERTIA",
            "design_lock": {"revision": 3, "sha256": review.EXP_W1_DESIGN_LOCK_SHA256},
            "treatment": {"normal_ppo_iterations_completed": 0, "endpoint_authority": "NONE"},
            "warmup_gate": {
                "status": "FAIL",
                "locked_failure_action": "ABORT_BEFORE_NORMAL_PPO",
                "relative_heldout_mse_reduction": 0.006853678110629593,
                "minimum_relative_heldout_mse_reduction": 0.02,
            },
            "downstream": {
                "primary100k": "FORBIDDEN",
                "promotion20k": "FORBIDDEN",
                "formal100k": "FORBIDDEN",
                "slumbot": "FORBIDDEN",
            },
        }

    def test_terminal_w1_failure_cannot_be_reopened_by_historical_value_audit(self):
        result = review.build_review(
            value=value_artifact(),
            method=self.w1_failure_artifact(),
            program_state="EXP_W1_FAIL_WARMUP_GATE",
        )
        self.assertEqual(result["evidence_matrix"]["method_experiment"]["status"], "VALID_WARMUP_ABORT")
        self.assertFalse(result["permissions"]["route_pivot_exp_w1_eligible"])
        self.assertEqual(result["overall"], "PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET")

    def test_newer_generic_method_evidence_preserves_terminal_w1_closure(self):
        method = {
            "classification": "FAIL",
            "same_start_controlled": True,
            "common_deal_endpoint_evaluation": True,
            "independent_training_seeds": 1,
            "terminal_experiments": ["EXP-W1", "EXP005-C", "H1"],
        }
        result = review.build_review(
            value=value_artifact(),
            method=method,
            program_state="TIER2_FROZEN_ROUTE_PIVOT",
        )
        row = result["evidence_matrix"]["method_experiment"]
        self.assertEqual(row["status"], "VALID")
        self.assertIn("EXP-W1", row["terminal_experiments"])
        self.assertFalse(result["permissions"]["route_pivot_exp_w1_eligible"])
        self.assertEqual(result["overall"], "PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET")
    def test_w1_failure_with_relaxed_threshold_is_rejected(self):
        method = self.w1_failure_artifact()
        method["warmup_gate"]["minimum_relative_heldout_mse_reduction"] = 0.005
        result = review.build_review(method=method, program_state="EXP_W1_FAIL_WARMUP_GATE")
        self.assertEqual(result["evidence_matrix"]["method_experiment"]["status"], "MISSING_OR_INVALID")

    def test_crossplay_schema_alone_does_not_unlock_cycle_claim(self):
        crossplay = {
            "schema_version": "v5.crossplay.cycle_audit.v1",
            "status": "SUPPORTED_NONTRANSITIVE_CYCLE",
            "matrix": {"complete": False},
            "errors": [],
            "claims": {
                "nontransitivity_supported": True,
                "temporal_self_play_cycle_supported": True,
                "behavior_change_authorized": False,
                "strength_claim_authorized": False,
            },
        }
        result = review.build_review(crossplay=crossplay)
        self.assertFalse(result["permissions"]["may_claim_panel_nontransitivity"])
        self.assertFalse(result["permissions"]["may_claim_temporal_self_play_cycle"])

if __name__ == "__main__":
    unittest.main()
