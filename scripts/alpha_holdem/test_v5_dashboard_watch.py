#!/usr/bin/env python3
"""Focused tests for V5 dashboard watcher status helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_dashboard_watch import (
    build_eval_cadence_watch_aliases,
    build_gate_aliases,
    build_slumbot_analysis_coverage_aliases,
    build_slumbot_loss_trend_aliases,
    latest_completed_post_gate_review,
)


class LatestCompletedPostGateReviewTest(unittest.TestCase):
    def write_review(self, run_dir: Path, target: int, overall: str) -> None:
        payload = {
            "checked_at": f"2026-07-06T11:{target % 60:02d}:00+00:00",
            "gate": {"overall": "PASS"},
            "internal_probe": {"state": "COMPLETED"},
            "overall": overall,
            "recommendation": f"review {target}",
            "target_iteration": target,
        }
        (run_dir / f"v5_post_gate_review_{target}.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def test_returns_latest_non_pending_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_review(run_dir, 8500, "REVIEW_REQUIRED_NO_AUTO_RESTART")
            self.write_review(run_dir, 8600, "REVIEW_REQUIRED_NO_AUTO_RESTART")
            self.write_review(run_dir, 8700, "PENDING_EVIDENCE")

            review = latest_completed_post_gate_review(run_dir)

        self.assertEqual(review["target_iteration"], 8600)
        self.assertEqual(review["overall"], "REVIEW_REQUIRED_NO_AUTO_RESTART")
        self.assertEqual(review["recommendation"], "review 8600")

    def test_returns_empty_when_no_completed_review_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            self.write_review(run_dir, 8700, "PENDING_EVIDENCE")

            review = latest_completed_post_gate_review(run_dir)

        self.assertEqual(review, {})


class GateAliasTest(unittest.TestCase):
    def test_build_gate_aliases_prefers_status_detail(self):
        summary = {
            "age_seconds": 12.5,
            "checkpoint_hands": 141112380,
            "checkpoint_iteration": 8600,
            "overall": "PENDING",
            "target_iteration": 8700,
        }
        detail = {
            "checkpoint_hands": 141112380,
            "checkpoint_iteration": 8600,
            "health_overall": "PASS",
            "live_hands": 141719650,
            "live_iteration": 8637,
            "overall": "PENDING",
            "remaining_checkpoint_iterations": 100,
            "remaining_live_iterations": 63,
            "target_iteration": 8700,
        }

        aliases = build_gate_aliases("next_gate", summary, detail)

        self.assertEqual(aliases["next_gate_target_iteration"], 8700)
        self.assertEqual(aliases["next_gate_overall"], "PENDING")
        self.assertEqual(aliases["next_gate_health_overall"], "PASS")
        self.assertEqual(aliases["next_gate_live_iteration"], 8637)
        self.assertEqual(aliases["next_gate_remaining_live_iterations"], 63)
        self.assertEqual(aliases["next_gate_remaining_checkpoint_iterations"], 100)
        self.assertEqual(aliases["next_gate_age_seconds"], 12.5)


class SlumbotLossTrendAliasTest(unittest.TestCase):
    def test_build_slumbot_loss_trend_aliases_includes_short_and_long_bb100_names(self):
        item = {
            "blocks_strength_claim": False,
            "reason": "loss trend ready",
            "status": "WATCH",
        }
        rows = [
            {
                "bb_per_100": -85.037,
                "delta_vs_previous": {"bb_per_100": -13.575},
                "position": {"bb_bb100": -55.028, "sb_bb100": -115.046},
                "terminal": {"hero_fold_bb100": -167.737, "showdown_bb100": -10.629},
            }
        ]

        aliases = build_slumbot_loss_trend_aliases(item, rows)

        self.assertEqual(aliases["slumbot_loss_trend_status"], "WATCH")
        self.assertEqual(aliases["slumbot_loss_trend_rows"], 1)
        self.assertEqual(aliases["slumbot_loss_trend_latest_bb100"], -85.037)
        self.assertEqual(aliases["slumbot_loss_trend_latest_bb_per_100"], -85.037)
        self.assertEqual(aliases["slumbot_loss_trend_latest_delta_bb100"], -13.575)
        self.assertEqual(aliases["slumbot_loss_trend_latest_delta_bb_per_100"], -13.575)
        self.assertEqual(aliases["slumbot_loss_trend_latest_sb_bb100"], -115.046)
        self.assertEqual(aliases["slumbot_loss_trend_latest_showdown_bb100"], -10.629)


class SlumbotAnalysisCoverageAliasTest(unittest.TestCase):
    def test_build_slumbot_analysis_coverage_aliases_mirrors_counts_and_latest(self):
        trend_ledger = {
            "slumbot_analysis_coverage": {
                "complete_count": 2,
                "incomplete_count": 5,
                "latest": {
                    "analysis_complete": True,
                    "milestone_m": 100,
                    "missing_parts": [],
                    "stage": "quick5k",
                },
                "latest_complete": {
                    "bb_per_100": -85.037,
                    "milestone_m": 100,
                    "stage": "quick5k",
                },
                "overall": "WARN_HISTORICAL_INCOMPLETE",
                "total_count": 7,
            }
        }

        aliases = build_slumbot_analysis_coverage_aliases(trend_ledger)

        self.assertEqual(aliases["slumbot_analysis_coverage_overall"], "WARN_HISTORICAL_INCOMPLETE")
        self.assertEqual(aliases["slumbot_analysis_coverage_complete_count"], 2)
        self.assertEqual(aliases["slumbot_analysis_coverage_total_count"], 7)
        self.assertEqual(aliases["slumbot_analysis_coverage_incomplete_count"], 5)
        self.assertEqual(aliases["slumbot_analysis_coverage_latest_milestone_m"], 100)
        self.assertTrue(aliases["slumbot_analysis_coverage_latest_complete"])
        self.assertEqual(aliases["slumbot_analysis_coverage_latest_complete_bb100"], -85.037)


class EvalCadenceWatchAliasTest(unittest.TestCase):
    def test_build_eval_cadence_watch_aliases_mirrors_plan_preview(self):
        status = {
            "checked_at": "2026-07-06T12:37:51+00:00",
            "current_checkpoint_hands": 142753336,
            "current_checkpoint_iteration": 8700,
            "live_hands": 143229082,
            "next_external_plan_preview": {
                "checkpoint_hands": 142753336,
                "checkpoint_iteration": 8700,
                "failed_checks": ["training_hands"],
                "key": "quick5k_150M",
                "out_json": "preview.json",
                "out_md": "preview.md",
                "overall": "BLOCKED",
                "status": "WRITTEN",
                "tag": "v5_run_150M_quick5k_cadence",
            },
            "state": "WAITING_FOR_TARGET",
        }

        aliases = build_eval_cadence_watch_aliases(status)

        self.assertEqual(aliases["eval_cadence_watch_state"], "WAITING_FOR_TARGET")
        self.assertEqual(aliases["eval_cadence_watch_checkpoint_iteration"], 8700)
        self.assertEqual(aliases["eval_cadence_watch_checkpoint_hands"], 142753336)
        self.assertEqual(aliases["eval_cadence_watch_live_hands"], 143229082)
        self.assertEqual(aliases["next_external_plan_preview_status"], "WRITTEN")
        self.assertEqual(aliases["next_external_plan_preview_overall"], "BLOCKED")
        self.assertEqual(aliases["next_external_plan_preview_failed_checks"], ["training_hands"])
        self.assertEqual(aliases["next_external_plan_preview_json"], "preview.json")


if __name__ == "__main__":
    unittest.main()
