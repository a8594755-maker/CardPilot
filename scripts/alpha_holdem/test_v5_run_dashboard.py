#!/usr/bin/env python3
"""Focused tests for V5 run dashboard helpers."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_run_dashboard import summarize_eval_cadence_watch, summarize_internal_strength


class EvalCadenceWatchSummaryTest(unittest.TestCase):
    def test_summarize_eval_cadence_watch_includes_plan_preview(self):
        status = {
            "candidate_count": 0,
            "current_checkpoint_hands": 142753336,
            "current_checkpoint_iteration": 8700,
            "current_hands": 143393214,
            "launchable_key": None,
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
        }

        summary = summarize_eval_cadence_watch(status, Path("missing_status.json"))

        self.assertEqual(summary["candidate_count"], 0)
        self.assertIsNone(summary["launchable_key"])
        self.assertEqual(summary["checkpoint_iteration"], 8700)
        self.assertEqual(summary["checkpoint_hands"], 142753336)
        self.assertEqual(summary["live_hands"], 143393214)
        self.assertIsNone(summary["status_age_seconds"])
        preview = summary["next_external_plan_preview"]
        self.assertEqual(preview["status"], "WRITTEN")
        self.assertEqual(preview["overall"], "BLOCKED")
        self.assertEqual(preview["failed_checks"], ["training_hands"])
        self.assertEqual(preview["checkpoint_iteration"], 8700)
        self.assertEqual(preview["checkpoint_hands"], 142753336)


class InternalStrengthSummaryTest(unittest.TestCase):
    def test_summarize_internal_strength_exposes_selected_watcher_status_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            old_status = run_dir / "internal_strength_watch_status.json"
            new_status = run_dir / "internal_strength_watch_7200_9200_status.json"
            old_status.write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-05T16:32:03+00:00",
                        "completed": [6000],
                        "latest_probe": {
                            "checkpoint": {"iteration": 6000, "total_hands": 98450386},
                            "status": "PASS",
                            "target_iteration": 6000,
                        },
                        "targets": [6000],
                    }
                ),
                encoding="utf-8",
            )
            new_status.write_text(
                json.dumps(
                    {
                        "checked_at": "2026-07-06T13:04:36+00:00",
                        "completed": [7200, 7400, 7600, 7800, 8000, 8200, 8400, 8600],
                        "latest_probe": {
                            "checkpoint": {"iteration": 8600, "total_hands": 141112380},
                            "status": "PASS",
                            "target_iteration": 8600,
                        },
                        "latest_readiness": {
                            "checkpoint": {"iteration": 8700, "total_hands": 142753336},
                            "overall": "PENDING",
                            "target_iteration": 8800,
                        },
                        "targets": [7200, 7400, 7600, 7800, 8000, 8200, 8400, 8600, 8800],
                    }
                ),
                encoding="utf-8",
            )

            summary = summarize_internal_strength(run_dir)

        self.assertEqual(summary["latest_probe_target"], 8600)
        self.assertEqual(summary["next_target"], 8800)
        self.assertEqual(summary["next_overall"], "PENDING")
        self.assertEqual(summary["selected_status_path"], str(new_status))
        self.assertIn(str(old_status), summary["status_paths"])
        self.assertIn(str(new_status), summary["status_paths"])


if __name__ == "__main__":
    unittest.main()
