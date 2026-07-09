#!/usr/bin/env python3
"""Focused tests for V5 eval cadence watcher status helpers."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_eval_cadence_watch import build_progress_aliases, plan_preview_paths, summarize_plan_preview


class ProgressAliasTest(unittest.TestCase):
    def test_build_progress_aliases_includes_live_and_checkpoint_names(self):
        cadence = {
            "checkpoint_hands": 142753336,
            "checkpoint_iteration": 8700,
            "current_hands": 142851779,
        }

        aliases = build_progress_aliases(cadence)

        self.assertEqual(aliases["current_hands"], 142851779)
        self.assertEqual(aliases["current_live_hands"], 142851779)
        self.assertEqual(aliases["live_hands"], 142851779)
        self.assertEqual(aliases["checkpoint_hands"], 142753336)
        self.assertEqual(aliases["current_checkpoint_hands"], 142753336)
        self.assertEqual(aliases["checkpoint_iteration"], 8700)
        self.assertEqual(aliases["current_checkpoint_iteration"], 8700)


class PlanPreviewTest(unittest.TestCase):
    def test_plan_preview_paths_use_stage_and_target(self):
        out_json, out_md = plan_preview_paths(Path("run"), "quick5k", 150_000_000)

        self.assertEqual(out_json, Path("run") / "slumbot_cadence_quick5k_150M_plan_preview.json")
        self.assertEqual(out_md, Path("run") / "slumbot_cadence_quick5k_150M_plan_preview.md")

    def test_summarize_plan_preview_reports_blocking_checks(self):
        summary = {
            "checked_at": "2026-07-06T12:33:01+00:00",
            "checkpoint": {"iteration": 8700, "total_hands": 142753336},
            "checks": [
                {"name": "training_hands", "status": "FAIL"},
                {"name": "quality_gate", "status": "PASS"},
            ],
            "min_training_hands": 150_000_000,
            "overall": "BLOCKED",
            "stage": "quick5k",
        }

        status = summarize_plan_preview(
            key="quick5k_150M",
            tag="v5_run_150M_quick5k_cadence",
            out_json=Path("preview.json"),
            out_md=Path("preview.md"),
            summary=summary,
        )

        self.assertEqual(status["status"], "WRITTEN")
        self.assertEqual(status["overall"], "BLOCKED")
        self.assertEqual(status["failed_checks"], ["training_hands"])
        self.assertEqual(status["checkpoint_iteration"], 8700)
        self.assertEqual(status["checkpoint_hands"], 142753336)


if __name__ == "__main__":
    unittest.main()
