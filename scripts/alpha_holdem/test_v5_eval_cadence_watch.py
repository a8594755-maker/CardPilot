#!/usr/bin/env python3
"""Focused tests for V5 eval cadence watcher status helpers."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_eval_cadence_watch import (
    build_progress_aliases,
    command_for_launch,
    exp003_bundle_mutex_status,
    launch_due,
    plan_preview_paths,
    runnable_plan,
    summarize_plan_preview,
)


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


class Exp003BundleMutexTest(unittest.TestCase):
    def test_lock_or_running_status_blocks_cadence_launch(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "v5_exp003_bundle_watch.lock").write_text("reserved", encoding="utf-8")
            self.assertTrue(exp003_bundle_mutex_status(run_dir)["busy"])
            (run_dir / "v5_exp003_bundle_watch.lock").unlink()
            (run_dir / "v5_exp003_bundle_watch_status.json").write_text(
                json.dumps({"overall": "RUNNING"}), encoding="utf-8"
            )
            self.assertTrue(exp003_bundle_mutex_status(run_dir)["busy"])

    def test_launch_due_rechecks_mutex_and_never_spawns_child(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            (run_dir / "v5_exp003_bundle_watch.lock").write_text("reserved", encoding="utf-8")
            args = argparse.Namespace(
                run_dir=str(run_dir),
                python="python",
                output_dir="models",
                child_sleep_seconds=60,
                append_report="report.md",
            )
            with patch(
                "v5_eval_cadence_watch.subprocess.run",
                side_effect=AssertionError("cadence child must not launch"),
            ):
                result = launch_due(
                    args,
                    {"stage": "promotion20k", "target_hands": 500_000_000},
                    "tag",
                )
            self.assertEqual(result["status"], "DEFERRED_EXP003_BUNDLE_MUTEX")
            self.assertIsNone(result["returncode"])


class FormalCheckpointProvenanceTest(unittest.TestCase):
    def test_runnable_formal_plan_uses_same_target_promotion_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            run_id = "run_a"
            gate_path = output_dir / "bench_v55_v5_run_a_500M_promotion20k_cadence_promotion_gate.json"
            gate_path.write_text(
                json.dumps({"checkpoint_path": "frozen_500m.pt"}),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                run_dir="run",
                output_dir=str(output_dir),
                max_health_age_seconds=600,
            )
            with patch("v5_eval_cadence_watch.evaluate_benchmark_plan", side_effect=lambda value: vars(value)):
                plan = runnable_plan(
                    args,
                    {"stage": "formal100k", "target_hands": 500_000_000},
                    "v5_run_a_500M_formal100k_cadence",
                    run_id,
                )
            self.assertEqual(plan["checkpoint"], "frozen_500m.pt")
            self.assertEqual(plan["promotion_gate_json"], str(gate_path))

    def test_formal_launch_command_pins_checkpoint_and_gate(self):
        args = argparse.Namespace(
            python="python",
            output_dir="models",
            child_sleep_seconds=60,
            append_report="report.md",
        )
        cmd = command_for_launch(
            args,
            stage="formal100k",
            target_hands=500_000_000,
            tag="formal_tag",
            run_dir=Path("run"),
            plan={
                "checkpoint_path": "frozen_500m.pt",
                "promotion20k_prerequisite": {"path": "promotion_500m.json"},
            },
        )
        self.assertEqual(cmd[cmd.index("--checkpoint") + 1], "frozen_500m.pt")
        self.assertEqual(cmd[cmd.index("--promotion-gate-json") + 1], "promotion_500m.json")


if __name__ == "__main__":
    unittest.main()
