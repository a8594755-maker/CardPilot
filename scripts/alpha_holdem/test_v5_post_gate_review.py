#!/usr/bin/env python3
"""Focused identity tests for V5 post-gate internal-probe evidence."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_post_gate_review import build_review, summarize_gate, summarize_internal_probe


class TargetInternalProbeIdentityTest(unittest.TestCase):
    target = 100

    def write_json(self, run_dir: Path, name: str, payload: dict) -> None:
        (run_dir / name).write_text(json.dumps(payload), encoding="utf-8")

    def prepare_run(self, run_dir: Path, *, gate_checkpoint_iteration: int | None = None) -> None:
        gate_checkpoint = self.target if gate_checkpoint_iteration is None else gate_checkpoint_iteration
        self.write_json(
            run_dir,
            "gate_100_status.json",
            {
                "overall": "PASS",
                "target_iteration": self.target,
                "checkpoint_iteration": gate_checkpoint,
                "checkpoint_hands": 1_000,
                "live_iteration": self.target,
            },
        )
        self.write_json(
            run_dir,
            "internal_strength_watch_status.json",
            {
                "checked_at": "2026-07-10T01:00:00+00:00",
                "targets": [self.target],
                "completed": [self.target],
                "latest_readiness": {"target_iteration": self.target, "overall": "READY"},
            },
        )
        self.write_json(
            run_dir,
            "v5_l6_status_brief.json",
            {
                "claims": {"can_claim_l5": False},
                "score_progression": {"latest_internal_probe_iteration": self.target},
            },
        )

    def write_probe(self, run_dir: Path, checkpoint_iteration: int, *, suffix: str = "200h") -> None:
        self.write_json(
            run_dir,
            f"internal_strength_probe_iter{self.target}_{suffix}.json",
            {
                "checked_at": "2026-07-10T01:01:00+00:00",
                "checkpoint": {"iteration": checkpoint_iteration, "total_hands": 1_000},
                "hands_per_match": 200,
                "results": [
                    {
                        "candidate_kind": "checkpoint_latest",
                        "candidate_iteration": self.target,
                        "opponent": "fixed",
                        "bb100": 1.0,
                        "ci95_bb100": 2.0,
                        "hands": 200,
                        "wins": 100,
                        "losses": 100,
                        "draws": 0,
                    }
                ],
                "trends": {},
            },
        )

    def test_mismatched_filename_checkpoint_is_quarantined_and_cannot_complete_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.prepare_run(run_dir)
            self.write_probe(run_dir, 200)

            internal = summarize_internal_probe(run_dir, self.target)
            review = build_review(run_dir, self.target)

        self.assertEqual(internal["state"], "QUARANTINED_TARGET_CHECKPOINT_MISMATCH")
        self.assertEqual(internal["target_probe_identity"], "QUARANTINED_TARGET_CHECKPOINT_MISMATCH")
        self.assertEqual(len(internal["quarantined_target_probes"]), 1)
        self.assertEqual(review["overall"], "QUARANTINED_INTERNAL_PROBE_IDENTITY")
        self.assertNotEqual(review["internal_probe"]["state"], "COMPLETED")
        self.assertTrue(any(row["name"] == "internal_probe_identity" for row in review["blockers"]))

    def test_exact_checkpoint_artifact_can_complete_gate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.prepare_run(run_dir)
            self.write_probe(run_dir, self.target)

            internal = summarize_internal_probe(run_dir, self.target)
            review = build_review(run_dir, self.target)

        self.assertEqual(internal["state"], "COMPLETED")
        self.assertEqual(internal["target_probe_identity"], "VALID")
        self.assertEqual(review["overall"], "REVIEW_REQUIRED_NO_AUTO_RESTART")

    def test_stale_l6_aggregate_cannot_complete_or_relabel_target_probe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.prepare_run(run_dir)
            self.write_probe(run_dir, self.target)
            self.write_json(
                run_dir,
                "v5_l6_status_brief.json",
                {
                    "claims": {"can_claim_l5": False},
                    "score_progression": {
                        "latest_internal_probe_iteration": self.target - 1,
                        "latest_internal_probe_hands": 900,
                        "latest_internal_verdict": "STALE_VERDICT",
                        "latest_internal_delta_mean_bb100": 123.0,
                        "latest_internal_delta_lower_bb100": 45.0,
                    },
                },
            )

            internal = summarize_internal_probe(run_dir, self.target)
            review = build_review(run_dir, self.target)

        self.assertEqual(internal["state"], "PENDING_L6_AGGREGATE_IDENTITY")
        self.assertEqual(internal["latest_l6_identity"], "STALE_OR_MISSING")
        self.assertIsNone(internal["latest_l6_verdict"])
        self.assertIsNone(internal["latest_l6_delta_mean_bb100"])
        self.assertEqual(review["overall"], "DUE_EVIDENCE_REFRESH")

    def test_raw_pass_gate_with_later_checkpoint_is_quarantined(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.prepare_run(run_dir, gate_checkpoint_iteration=200)
            self.write_probe(run_dir, self.target)

            gate = summarize_gate(run_dir, self.target)
            review = build_review(run_dir, self.target)

        self.assertEqual(gate["artifact_overall"], "PASS")
        self.assertEqual(gate["overall"], "QUARANTINED_GATE_IDENTITY")
        self.assertIn("does not match filename target", gate["identity"]["reason"])
        self.assertEqual(review["overall"], "QUARANTINED_GATE_IDENTITY")
        self.assertTrue(any(row["name"] == "gate_identity" for row in review["blockers"]))

    def test_valid_artifact_is_not_poisoned_by_separate_quarantined_history(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.prepare_run(run_dir)
            self.write_probe(run_dir, 200, suffix="100h")
            self.write_probe(run_dir, self.target, suffix="200h")

            internal = summarize_internal_probe(run_dir, self.target)

        self.assertEqual(internal["state"], "COMPLETED")
        self.assertEqual(internal["target_probe_identity"], "VALID")
        self.assertEqual(len(internal["quarantined_target_probes"]), 1)


if __name__ == "__main__":
    unittest.main()
