#!/usr/bin/env python3
"""Focused safety tests for the V5 throughput sweep planner."""

from __future__ import annotations

import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_throughput_sweep_plan as planner


def active_config(**overrides):
    config = {
        "workers": 22,
        "hands_per_iter": 16_384,
        "total_hands": 2_700_000_000,
        "starting_stack": 200.0,
        "env_version": "v55",
        "lr": 3e-4,
        "gamma": 0.999,
        "delta1": 3.0,
        "entropy_coef": 0.05,
        "entropy_floor": 0.3,
        "postflop_action_prior_coef": 0.02,
        "preflop_action_prior_coef": 0.01,
        "k_best": 5,
        "pool_strategy": "loss-kbest",
        "pool_history_limit": 200,
        "self_play_fraction": 0.2,
        "opponent_assignment": "per-iteration",
        "snapshot_every": 200,
        "save_interval": 100,
        "rollout_mode": "multi",
        "rollout_envs_per_worker": 16,
        "inference_min_batch_slots": 256,
        "inference_batch_deadline_us": 1000.0,
        "mirror_self_play_deals": True,
        "allin_runout_ev": True,
        "allin_runout_ev_max_runouts": 200,
    }
    config.update(overrides)
    return config


def planner_args(source_run_dir: Path, output_root: Path, **overrides):
    values = {
        "source_run_dir": str(source_run_dir),
        "checkpoint": "",
        "output_root": str(output_root),
        "workers": "22",
        "hands_per_iter": "",
        "allow_hands_per_iter_change": False,
        "max_runtime_seconds": 900.0,
        "device": "cuda",
        "python": "python",
        "total_hands": 2_700_000_000,
        "postflop_action_prior_coef": None,
        "postflop_action_prior_target": "",
        "preflop_action_prior_coef": None,
        "preflop_action_prior_target": "",
        "compare_tail": 20,
        "min_baseline_rows": 20,
        "min_candidate_rows": 20,
        "min_hps_ratio": 1.05,
        "min_inf_bs_ratio": 1.0,
        "min_candidate_inf_bs": 12.0,
        "out_json": "",
        "out_md": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def checkpoint(config):
    return {
        "version": "v5.zero",
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
        "actual_hand_accounting": True,
        "fresh_from_zero_lineage": True,
        "iteration": 24_000,
        "total_hands": 394_254_129,
        "run_id": "active_exp003_run",
        "config": config,
    }


class TrainCommandInheritanceTest(unittest.TestCase):
    def build_command(self, config):
        args = argparse.Namespace(
            python="python",
            device="cuda",
            total_hands=2_700_000_000,
            max_runtime_seconds=900.0,
        )
        return planner.build_train_command(
            args=args,
            checkpoint_path=Path("source.pt"),
            config=config,
            run_id="candidate",
            run_dir=Path("candidate"),
            workers=22,
            hands_per_iter=16_384,
        )

    def test_active_exp002_exp003_flags_are_inherited(self):
        command = self.build_command(active_config())

        self.assertIn("--rollout-mode multi", command)
        self.assertIn("--rollout-envs-per-worker 16", command)
        self.assertIn("--inference-min-batch-slots 256", command)
        self.assertIn("--inference-batch-deadline-us 1000.0", command)
        self.assertIn("--mirror-self-play-deals", command)
        self.assertIn("--allin-runout-ev", command)
        self.assertIn("--allin-runout-ev-max-runouts 200", command)

    def test_disabled_boolean_flags_stay_disabled_and_zero_is_preserved(self):
        command = self.build_command(
            active_config(
                mirror_self_play_deals=False,
                allin_runout_ev=False,
                allin_runout_ev_max_runouts=0,
                inference_min_batch_slots=0,
                inference_batch_deadline_us=0.0,
            )
        )

        tokens = command.split()
        self.assertNotIn("--mirror-self-play-deals", tokens)
        self.assertNotIn("--allin-runout-ev", tokens)
        self.assertIn("--allin-runout-ev-max-runouts 0", command)
        self.assertIn("--inference-min-batch-slots 0", command)
        self.assertIn("--inference-batch-deadline-us 0.0", command)


class PlannerSafetyGateTest(unittest.TestCase):
    def evaluate(self, args, config):
        with patch.object(planner, "load_checkpoint", return_value=checkpoint(config)), patch.object(
            planner, "is_process_alive", return_value=False
        ):
            return planner.evaluate(args)

    def test_default_preserves_source_hpi_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            summary = self.evaluate(planner_args(source, root / "out"), active_config())

        self.assertEqual(summary["overall"], "READY")
        self.assertEqual([row["hands_per_iter"] for row in summary["variants"]], [16_384])
        self.assertTrue(summary["variants"][0]["min_batch_capacity_ok"])

    def test_hpi_change_without_opt_in_is_blocked_and_not_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            args = planner_args(source, root / "out", hands_per_iter="16384,32768")
            summary = self.evaluate(args, active_config())

        self.assertEqual(summary["overall"], "BLOCKED")
        self.assertEqual([row["hands_per_iter"] for row in summary["variants"]], [16_384])
        check = next(
            row for row in summary["checks"] if row["name"] == "hands_per_iter_change_authorization"
        )
        self.assertEqual(check["status"], "FAIL")

    def test_hpi_change_with_explicit_opt_in_is_emitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            args = planner_args(
                source,
                root / "out",
                hands_per_iter="16384,32768",
                allow_hands_per_iter_change=True,
            )
            summary = self.evaluate(args, active_config())

        self.assertEqual(summary["overall"], "READY")
        self.assertEqual(
            [row["hands_per_iter"] for row in summary["variants"]],
            [16_384, 32_768],
        )

    def test_min_batch_capacity_failure_blocks_and_omits_commands(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            source.mkdir()
            args = planner_args(source, root / "out", workers="8")
            summary = self.evaluate(args, active_config())
            markdown_path = root / "plan.md"
            planner.write_markdown(markdown_path, summary)
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(summary["overall"], "BLOCKED")
        variant = summary["variants"][0]
        self.assertEqual(variant["inference_capacity_slots"], 128)
        self.assertFalse(variant["min_batch_capacity_ok"])
        self.assertIsNone(variant["train_command"])
        self.assertIsNone(variant["compare_command"])
        self.assertIn("NOT EMITTED (min-batch capacity gate failed)", markdown)
        check = next(
            row for row in summary["checks"] if row["name"] == "variant_min_batch_capacity"
        )
        self.assertEqual(check["status"], "FAIL")


if __name__ == "__main__":
    unittest.main()
