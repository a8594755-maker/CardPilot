#!/usr/bin/env python3
"""Focused tests for V5 next-action queue Slumbot loss-trend gating."""

from __future__ import annotations

import sys
import json
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_next_action_queue import (
    EXP003_CUTOVER_HANDS,
    EXP003_MIRROR_PAIRS,
    EXP003_MIRROR_POLICY_MODE,
    EXP003_MIRROR_SEED,
    EXP003_NATIVE_ANCHOR_HANDS,
    EXP003_NATIVE_MIRROR_TARGET_HANDS,
    EXP003_NATIVE_SHA256,
    EXP003_PRE_SHA256,
    build_slumbot_loss_trend_item,
    claim_reference_from_strength,
    exp003_mirror_bundle_status,
    external_eval_descriptor,
    latest_promotion20k_prerequisite,
    throughput_queue_policy,
)


CI_PATH = Path("models/bench_v55_example_100M_quick5k_ci_summary.json")
POST_SHA256 = "ab" * 32


def complete_loss_row(**overrides):
    row = {
        "artifact_audit_overall": "PASS",
        "bb_per_100": -85.037,
        "ci_path": str(CI_PATH),
        "delta_vs_previous": {"bb_per_100": -13.575},
        "hand_review_exists": True,
        "loss_report_exists": True,
        "position": {"sb_bb100": -115.046, "bb_bb100": -55.028},
        "terminal": {"hero_fold_bb100": -167.737, "showdown_bb100": -10.629},
        "worst_first_preflop_decisions": [
            {"key": "sb_open_c"},
            {"key": "bb_vs_open_lt2.5bb_f"},
            {"key": "sb_open_raise_lt2.5bb"},
        ],
    }
    row.update(overrides)
    return row


class SlumbotLossTrendQueueItemTest(unittest.TestCase):
    def test_claim_reference_falls_back_to_trend_latest_official(self):
        reference = claim_reference_from_strength(
            {"hands": 0, "bb_per_100": None, "ci_lower": None},
            {
                "hands": 5000,
                "bb_per_100": -94.9,
                "lower_bound_bb_per_100": -124.555,
            },
        )

        self.assertEqual(reference["hands"], 5000)
        self.assertEqual(reference["bb_per_100"], -94.9)
        self.assertEqual(reference["ci_lower"], -124.555)

    def test_complete_loss_trend_is_watch(self):
        trend = {"official_slumbot_loss_trend": [complete_loss_row(bb_per_100=-71.462), complete_loss_row()]}

        item = build_slumbot_loss_trend_item(trend_ledger=trend, latest_ci_path=CI_PATH)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["key"], "slumbot_loss_trend_latest")
        self.assertEqual(item["status"], "WATCH")
        self.assertFalse(item["blocks_strength_claim"])
        self.assertIn("official loss-trend rows=2", item["reason"])
        self.assertIn("delta_vs_previous=-13.575", item["reason"])
        self.assertIn("sb_open_c", item["reason"])

    def test_missing_hand_review_requires_review(self):
        trend = {"official_slumbot_loss_trend": [complete_loss_row(hand_review_exists=False)]}

        item = build_slumbot_loss_trend_item(trend_ledger=trend, latest_ci_path=CI_PATH)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["status"], "REVIEW")
        self.assertTrue(item["blocks_strength_claim"])
        self.assertIn("hand_review", item["reason"])

    def test_missing_loss_trend_requires_review(self):
        item = build_slumbot_loss_trend_item(trend_ledger={}, latest_ci_path=CI_PATH)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["status"], "REVIEW")
        self.assertTrue(item["blocks_strength_claim"])
        self.assertIn("official_slumbot_loss_trend", item["reason"])

    def test_ci_mismatch_requires_review(self):
        trend = {"official_slumbot_loss_trend": [complete_loss_row(ci_path="models/bench_v55_old_ci_summary.json")]}

        item = build_slumbot_loss_trend_item(trend_ledger=trend, latest_ci_path=CI_PATH)

        self.assertIsNotNone(item)
        assert item is not None
        self.assertEqual(item["status"], "REVIEW")
        self.assertTrue(item["blocks_strength_claim"])
        self.assertIn("latest_loss_trend_ci_mismatch", item["reason"])

    def test_no_latest_ci_has_no_queue_item(self):
        self.assertIsNone(build_slumbot_loss_trend_item(trend_ledger={}, latest_ci_path=None))


class Promotion20kPrerequisiteTest(unittest.TestCase):
    def test_formal_prerequisite_blocks_non_strong_promotion_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = output_dir / "bench_v55_v5_run_250M_promotion20k_promotion_gate.json"
            path.write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-09T17:10:00+00:00",
                        "checkpoint": {"total_hands": 364_643_371},
                        "decisions": {
                            "promotion_20k_candidate": False,
                            "promotion_20k_strong": False,
                        },
                    }
                ),
                encoding="utf-8",
            )

            prereq = latest_promotion20k_prerequisite(output_dir, "v5_run")

        self.assertEqual(prereq["status"], "BLOCKED")
        self.assertFalse(prereq["promotion_20k_candidate"])
        self.assertFalse(prereq["promotion_20k_strong"])

    def test_formal_prerequisite_passes_strong_promotion_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            path = output_dir / "bench_v55_v5_run_250M_promotion20k_promotion_gate.json"
            path.write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-09T17:10:00+00:00",
                        "checkpoint": {"total_hands": 364_643_371},
                        "decisions": {
                            "promotion_20k_candidate": True,
                            "promotion_20k_strong": True,
                        },
                    }
                ),
                encoding="utf-8",
            )

            prereq = latest_promotion20k_prerequisite(output_dir, "v5_run")

        self.assertEqual(prereq["status"], "PASS")
        self.assertTrue(prereq["promotion_20k_candidate"])
        self.assertTrue(prereq["promotion_20k_strong"])


def write_exp003_mirror(
    run_dir: Path,
    name: str,
    *,
    candidate_hands: int,
    anchor_hands: int,
    pairs: int = EXP003_MIRROR_PAIRS,
    seed: int = EXP003_MIRROR_SEED,
    policy_mode: str = EXP003_MIRROR_POLICY_MODE,
    ci_ok: bool = True,
    ood_ok: bool = True,
) -> Path:
    path = run_dir / f"v5_mirror_eval_exp003_{name}.json"
    post_archive = run_dir / "exp003_judgment_archives" / "post.pt"
    post_archive.parent.mkdir(parents=True, exist_ok=True)
    post_archive.write_bytes(b"frozen-post")
    if candidate_hands >= EXP003_NATIVE_MIRROR_TARGET_HANDS:
        candidate_path = post_archive
        candidate_sha256 = POST_SHA256
        candidate_iteration = 24900
        gate_path = run_dir / "gate_24900_status.json"
        gate_path.write_text(
            json.dumps(
                {
                    "overall": "PASS",
                    "health_overall": "PASS",
                    "checkpoint_iteration": candidate_iteration,
                    "checkpoint_hands": candidate_hands,
                }
            ),
            encoding="utf-8",
        )
        (run_dir / "exp003_judgment_freeze_status.json").write_text(
            json.dumps(
                {
                    "overall": "PASS",
                    "target_hands": EXP003_NATIVE_MIRROR_TARGET_HANDS,
                    "selected_gate": {
                        "path": str(gate_path),
                        "iteration": candidate_iteration,
                        "checkpoint_hands": candidate_hands,
                        "overall": "PASS",
                    },
                    "archive": {
                        "path": str(post_archive),
                        "sha256": POST_SHA256,
                        "checkpoint": {
                            "iteration": candidate_iteration,
                            "total_hands": candidate_hands,
                            "run_id": "test",
                        },
                    },
                }
            ),
            encoding="utf-8",
        )
    else:
        candidate_path = run_dir / "pre.pt"
        candidate_path.write_bytes(b"pre")
        candidate_sha256 = EXP003_PRE_SHA256
        candidate_iteration = 21800
    if anchor_hands == EXP003_NATIVE_ANCHOR_HANDS:
        anchor_path = run_dir / "native.pt"
        anchor_path.write_bytes(b"native")
        anchor_sha256 = EXP003_NATIVE_SHA256
        anchor_iteration = 4600
    else:
        anchor_path = run_dir / "pre.pt"
        anchor_path.write_bytes(b"pre")
        anchor_sha256 = EXP003_PRE_SHA256
        anchor_iteration = 21800
    execution = {
        "status": "COMPLETED",
        "torch_threads": 1,
        "torch_interop_threads": 1,
        "priority": {"applied": True, "actual_label": "BelowNormal"},
    }
    path.write_text(
        json.dumps(
            {
                "checked_at": f"2026-07-09T22:00:{len(name):02d}+00:00",
                "candidate": {
                    "path": str(candidate_path),
                    "sha256": candidate_sha256,
                    "checkpoint": {"iteration": candidate_iteration, "total_hands": candidate_hands},
                },
                "anchors": [
                    {
                        "anchor_path": str(anchor_path),
                        "anchor_sha256": anchor_sha256,
                        "anchor_checkpoint": {"iteration": anchor_iteration, "total_hands": anchor_hands},
                        "anchor_ood_node_rate": 0.01 if ood_ok else 0.20,
                        "anchor_ood_valid_threshold": 0.15,
                        "anchor_ood_valid": ood_ok,
                        "policy_mode": policy_mode,
                        "candidate_bb100": 20.0,
                        "candidate_ci95_bb100": 10.0,
                    }
                ],
                "gate": {
                    "passes_ci_gate": ci_ok,
                    "all_anchors_pass_ood_gate": ood_ok,
                    "passes_internal_signal_gate": ci_ok and ood_ok,
                },
                "pairs": pairs,
                "policy_mode": policy_mode,
                "seed": seed,
                "starting_stack": 200.0,
                "device": "cpu",
                "execution": execution,
            }
        ),
        encoding="utf-8",
    )
    stem = str(path)[:-5]
    Path(stem + ".md").write_text("mirror\n", encoding="utf-8")
    Path(stem + ".stdout.log").write_text("", encoding="utf-8")
    Path(stem + ".stderr.log").write_text("", encoding="utf-8")
    Path(stem + ".execution.json").write_text(json.dumps(execution), encoding="utf-8")
    return path


class Exp003CausalMirrorBundleTest(unittest.TestCase):
    def test_candidate_only_is_not_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "INCOMPLETE")
        self.assertIn("pre_vs_native", status["detail"])
        self.assertIn("post_vs_pre_direct", status["detail"])

    def test_three_matching_roles_are_review_ready_not_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW_READY")
        self.assertEqual(status["candidate_checkpoint_hands"], post_hands)
        self.assertEqual(status["freeze"]["archive_sha256"], POST_SHA256)
        self.assertEqual(status["first_eligible_gate"]["hands"], post_hands)
        self.assertIn("not an ADOPT/ROLLBACK decision", status["detail"])

    def test_protocol_mismatch_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                seed=EXP003_MIRROR_SEED + 1,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("protocol mismatch", status["detail"])

    def test_more_than_registered_pairs_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                pairs=EXP003_MIRROR_PAIRS + 1,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("pre_vs_native", status["detail"])

    def test_missing_execution_proof_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            pre_path = write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            pre = json.loads(pre_path.read_text(encoding="utf-8"))
            pre["execution"]["priority"]["actual_label"] = "Normal"
            pre_path.write_text(json.dumps(pre), encoding="utf-8")
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("pre_vs_native", status["detail"])

    def test_ood_failure_requires_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                ood_ok=False,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("post_vs_native", status["detail"])

    def test_explicit_judgment_is_required_for_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )
            (run_dir / "v5_exp003_judgment.json").write_text(
                json.dumps({"candidate_checkpoint_hands": post_hands, "decision": "ADOPT"}),
                encoding="utf-8",
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW_READY")
        self.assertNotIn("judgment", status)

    def test_schema_valid_consistent_judgment_is_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )
            (run_dir / "v5_exp003_judgment.json").write_text(
                json.dumps(
                    {
                        "schema_version": "v5.exp003.judgment.v1",
                        "checked_at": "2026-07-09T23:00:00+00:00",
                        "measurement_status": "REVIEW_READY",
                        "decision": "ADOPT",
                        "decision_valid": True,
                        "candidate_checkpoint_hands": post_hands,
                        "candidate_checkpoint_sha256": POST_SHA256,
                        "effects": {
                            "native_axis": {"status": "PASS"},
                            "direct_causal": {"status": "PASS"},
                        },
                        "hard_guards": {"status": "PASS"},
                        "method_support": {
                            "value_loss": {"status": "PASS"},
                            "postflop_raise_plus_allin": {"status": "PASS"},
                        },
                        "mirror_artifact_sha256": {
                            "pre_vs_native": {},
                            "post_vs_native": {},
                            "post_vs_pre_direct": {},
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "ADOPT_CLOSED")
        self.assertEqual(status["judgment"]["decision"], "ADOPT")


class ExternalEvalDescriptorTest(unittest.TestCase):
    def test_promotion_is_not_mislabeled_quick5k_or_guarded_policy(self):
        descriptor = external_eval_descriptor("promotion20k", 500_000_000)

        self.assertEqual(descriptor["key"], "slumbot_promotion20k_500000000")
        self.assertIn("greedy-direct promotion20k", descriptor["noun"])
        self.assertNotIn("guarded", descriptor["action"])


class ThroughputQueuePolicyTest(unittest.TestCase):
    def test_open_exp003_window_blocks_sweep_execution(self):
        status, reason, action = throughput_queue_policy(
            run_id="v5_exp003_boundedk_run",
            exp003_mirror_status="MISSING",
            throughput_overall="WARN",
            effective_hps=1800.0,
        )

        self.assertEqual(status, "BLOCKED")
        self.assertIn("sole open behavior window", reason)
        self.assertIn("Do not execute", action)

    def test_inconclusive_exp003_does_not_open_throughput_window(self):
        status, reason, _ = throughput_queue_policy(
            run_id="v5_exp003_boundedk_run",
            exp003_mirror_status="INCONCLUSIVE_BLOCKED",
            throughput_overall="PASS",
            effective_hps=1800.0,
        )
        self.assertEqual(status, "BLOCKED")
        self.assertIn("INCONCLUSIVE_BLOCKED", reason)

    def test_adopt_closed_allows_normal_throughput_policy(self):
        status, _, _ = throughput_queue_policy(
            run_id="v5_exp003_boundedk_run",
            exp003_mirror_status="ADOPT_CLOSED",
            throughput_overall="PASS",
            effective_hps=1800.0,
        )
        self.assertEqual(status, "PASS")


if __name__ == "__main__":
    unittest.main()
