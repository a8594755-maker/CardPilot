#!/usr/bin/env python3
"""Safety tests for exact-checkpoint V5 gate evaluation."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_gate_sequence_watch as sequence_watch
import v5_gate_watch as gate_watch
import v5_next_action_queue as queue_module


class ExactCheckpointGateTest(unittest.TestCase):
    @staticmethod
    def _checkpoint(iteration: int) -> dict:
        return {
            "iteration": iteration,
            "total_hands": 409_058_520,
            "pool_snapshots": [{"hands": 409_058_520}],
            "version": "v5.zero",
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "starting_stack_bb": 200.0,
            "actual_hand_accounting": True,
            "resume": None,
            "config": {},
        }

    def _evaluate(self, *, target: int, checkpoint_iteration: int) -> dict:
        checkpoint = self._checkpoint(checkpoint_iteration)

        def fake_load_json(path: Path) -> dict:
            if path.name == "run_manifest.json":
                return {"run_id": "test-v5", "config": {}}
            if path.name == "health_status.json":
                return {"overall": "PASS"}
            return {}

        with (
            patch("v5_gate_watch.load_json", side_effect=fake_load_json),
            patch("v5_gate_watch.parse_log", return_value=[{"iteration": checkpoint_iteration, "hands": 409_058_520}]),
            patch("v5_gate_watch.load_checkpoint", return_value=checkpoint),
            patch("v5_gate_watch.file_age_seconds", return_value=0.0),
        ):
            return gate_watch.evaluate_gate(
                run_dir=Path("unused"),
                target_iteration=target,
                expected_pool_snapshots=1,
                expected_env_version="v55",
                expected_obs_version="v55",
                expected_action_space_version="9slot_v5",
                expected_stack_bb=200.0,
                expected_opponent_assignment="",
                expected_pool_strategy="",
                checkpoint_load_grace_seconds=0.0,
                require_current_pool_snapshot=False,
            )

    def test_exact_checkpoint_is_the_only_pass_eligible_checkpoint(self):
        summary = self._evaluate(target=24_900, checkpoint_iteration=24_900)

        self.assertEqual(summary["overall"], "PASS")
        self.assertTrue(summary["checkpoint_exact_target"])
        self.assertFalse(summary["checkpoint_advanced_past_target"])
        self.assertTrue(summary["pass_eligible"])
        self.assertTrue(gate_watch.summary_is_exact_gate_pass(summary, 24_900))

    def test_later_checkpoint_is_terminal_stale_not_pass(self):
        summary = self._evaluate(target=24_900, checkpoint_iteration=25_000)

        self.assertEqual(summary["overall"], gate_watch.STALE_CHECKPOINT)
        self.assertFalse(summary["checkpoint_exact_target"])
        self.assertTrue(summary["checkpoint_advanced_past_target"])
        self.assertFalse(summary["pass_eligible"])
        checkpoint_check = next(check for check in summary["checks"] if check["name"] == "checkpoint_iteration")
        self.assertEqual(checkpoint_check["status"], gate_watch.STALE_CHECKPOINT)
        self.assertFalse(gate_watch.summary_is_exact_gate_pass(summary, 24_900))

    def test_non_integer_checkpoint_identity_fails_closed_and_cannot_forge_pass(self):
        for raw_iteration in (24_900.9, True, "24900.9", "invalid"):
            with self.subTest(raw_iteration=raw_iteration):
                summary = self._evaluate(target=24_900, checkpoint_iteration=raw_iteration)
                checkpoint_check = next(check for check in summary["checks"] if check["name"] == "checkpoint_iteration")
                forged_pass = dict(summary)
                forged_pass["overall"] = "PASS"
                forged_pass["checkpoint_iteration"] = raw_iteration
                forged_pass["checkpoint"] = {"iteration": raw_iteration}

                self.assertEqual(summary["overall"], "FAIL")
                self.assertEqual(checkpoint_check["status"], "FAIL")
                self.assertIsNone(summary["checkpoint_iteration"])
                self.assertEqual(summary["checkpoint_iteration_raw"], raw_iteration)
                self.assertFalse(summary["pass_eligible"])
                self.assertFalse(gate_watch.summary_is_exact_gate_pass(summary, 24_900))
                self.assertFalse(gate_watch.summary_is_exact_gate_pass(forged_pass, 24_900))

    def test_checkpoint_load_error_before_live_target_is_transient_pending(self):
        def fake_load_json(path: Path) -> dict:
            if path.name == "run_manifest.json":
                return {"run_id": "test-v5", "config": {}}
            if path.name == "health_status.json":
                return {"overall": "PASS"}
            return {}

        with (
            patch("v5_gate_watch.load_json", side_effect=fake_load_json),
            patch("v5_gate_watch.parse_log", return_value=[{"iteration": 24_800, "hands": 1}]),
            patch("v5_gate_watch.load_checkpoint", return_value={"_load_error": "concurrent write"}),
            patch("v5_gate_watch.file_age_seconds", return_value=99.0),
        ):
            summary = gate_watch.evaluate_gate(
                run_dir=Path("unused"), target_iteration=24_900, expected_pool_snapshots=1,
                expected_env_version="v55", expected_obs_version="v55",
                expected_action_space_version="9slot_v5", expected_stack_bb=200.0,
                expected_opponent_assignment="", expected_pool_strategy="",
                checkpoint_load_grace_seconds=0.0, require_current_pool_snapshot=False,
            )
        checkpoint_check = next(check for check in summary["checks"] if check["name"] == "checkpoint_load")
        self.assertEqual(summary["overall"], "PENDING")
        self.assertEqual(checkpoint_check["status"], "PENDING")

    def test_checkpoint_load_error_after_live_target_and_grace_fails_closed(self):
        def fake_load_json(path: Path) -> dict:
            if path.name == "run_manifest.json":
                return {"run_id": "test-v5", "config": {}}
            if path.name == "health_status.json":
                return {"overall": "PASS"}
            return {}

        with (
            patch("v5_gate_watch.load_json", side_effect=fake_load_json),
            patch("v5_gate_watch.parse_log", return_value=[{"iteration": 24_900, "hands": 1}]),
            patch("v5_gate_watch.load_checkpoint", return_value={"_load_error": "persistent corruption"}),
            patch("v5_gate_watch.file_age_seconds", return_value=99.0),
        ):
            summary = gate_watch.evaluate_gate(
                run_dir=Path("unused"), target_iteration=24_900, expected_pool_snapshots=1,
                expected_env_version="v55", expected_obs_version="v55",
                expected_action_space_version="9slot_v5", expected_stack_bb=200.0,
                expected_opponent_assignment="", expected_pool_strategy="",
                checkpoint_load_grace_seconds=0.0, require_current_pool_snapshot=False,
            )
        checkpoint_check = next(check for check in summary["checks"] if check["name"] == "checkpoint_load")
        self.assertEqual(summary["overall"], "FAIL")
        self.assertEqual(checkpoint_check["status"], "FAIL")

    def test_stale_status_cannot_append_report_or_enter_pass_gate_selection(self):
        summary = self._evaluate(target=24_900, checkpoint_iteration=25_000)
        forged_pass = dict(summary)
        forged_pass["overall"] = "PASS"
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            report = run_dir / "launch_report.md"
            report.write_text("# report\n", encoding="utf-8")

            gate_watch.write_outputs(run_dir, 24_900, summary)
            stored = json.loads((run_dir / "gate_24900_status.json").read_text(encoding="utf-8"))

            self.assertEqual(stored["overall"], gate_watch.STALE_CHECKPOINT)
            self.assertFalse(gate_watch.append_report_if_pass(report, 24_900, summary))
            self.assertFalse(gate_watch.append_report_if_pass(report, 24_900, forged_pass))
            self.assertEqual(report.read_text(encoding="utf-8"), "# report\n")
            # Queue ingestion remains fail-closed even if an external caller
            # tried to overwrite the terminal stale record as PASS.
            gate_watch.write_outputs(run_dir, 24_900, forged_pass)
            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, 1)
            self.assertEqual(eligible, [])
            self.assertEqual(len(quarantined), 1)
            self.assertEqual(quarantined[0]["status"], "QUARANTINED")

    def test_sequence_advances_stale_target_without_appending_a_pass_report(self):
        stale_summary = {
            "overall": gate_watch.STALE_CHECKPOINT,
            "latest": {"iteration": 25_000},
            "checkpoint": {"iteration": 25_000, "pool_snapshots": 5},
            "checks": [],
        }
        args = Namespace(
            run_dir="unused",
            snapshot_every=200,
            k_best=5,
            expected_pool_snapshots=5,
            require_current_pool_snapshot_on_snapshot_gates=False,
            expected_pool_strategy="",
            refresh_health=False,
            python=sys.executable,
            expected_env_version="v55",
            expected_obs_version="v55",
            expected_action_space_version="9slot_v5",
            expected_stack_bb=200.0,
            expected_opponent_assignment="",
            checkpoint_load_grace_seconds=0.0,
            timeout_seconds=0.0,
            poll_seconds=0.0,
            append_report="unused.md",
        )
        with (
            patch("v5_gate_sequence_watch.evaluate_gate", return_value=stale_summary),
            patch("v5_gate_sequence_watch.write_outputs") as write_outputs,
            patch("v5_gate_sequence_watch.append_report_if_pass") as append_report,
            patch("builtins.print"),
        ):
            result = sequence_watch.run_gate(args, 24_900)

        self.assertEqual(result, gate_watch.STALE_CHECKPOINT)
        write_outputs.assert_called_once()
        append_report.assert_not_called()

        with (
            patch("v5_gate_sequence_watch.run_gate", side_effect=[gate_watch.STALE_CHECKPOINT, "PASS"]) as run_gate,
            patch.object(sys, "argv", [
                "v5_gate_sequence_watch.py",
                "--run-dir",
                "unused",
                "--start-iteration",
                "24900",
                "--max-iteration",
                "25000",
                "--step",
                "100",
            ]),
            patch("builtins.print"),
        ):
            exit_code = sequence_watch.main()

        self.assertEqual(exit_code, 0)
        self.assertEqual([call.args[1] for call in run_gate.call_args_list], [24_900, 25_000])


if __name__ == "__main__":
    unittest.main()
