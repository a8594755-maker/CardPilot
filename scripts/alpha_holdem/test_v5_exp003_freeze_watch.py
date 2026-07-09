#!/usr/bin/env python3
"""Focused tests for the EXP-003 first-eligible-PASS freeze watcher."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

import torch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_exp003_freeze_watch import DEFAULT_TARGET_HANDS, freeze_once


RUN_ID = "v5_test_exp003"


def write_checkpoint(path: Path, iteration: int, hands: int, *, run_id: str = RUN_ID) -> None:
    torch.save(
        {
            "iteration": iteration,
            "total_hands": hands,
            "run_id": run_id,
            "version": "v5.zero",
            "env_version": "v55",
            "obs_version": "v55",
            "action_space_version": "9slot_v5",
            "starting_stack_bb": 200.0,
            "actual_hand_accounting": True,
            "fresh_from_zero_lineage": True,
            "pool_snapshots": [],
        },
        path,
    )


def write_gate(
    run_dir: Path,
    target_iteration: int,
    checkpoint_hands: int,
    *,
    overall: str = "PASS",
    checkpoint_iteration: int | None = None,
) -> Path:
    checkpoint_iteration = target_iteration if checkpoint_iteration is None else checkpoint_iteration
    path = run_dir / f"gate_{target_iteration}_status.json"
    path.write_text(
        json.dumps(
            {
                "overall": overall,
                "target_iteration": target_iteration,
                "checkpoint_iteration": checkpoint_iteration,
                "checkpoint_hands": checkpoint_hands,
                "run_id": RUN_ID,
            }
        ),
        encoding="utf-8",
    )
    return path


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Exp003FreezeWatchTest(unittest.TestCase):
    def test_waits_before_any_eligible_pass_gate(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            write_checkpoint(run_dir / "latest.pt", 24_800, DEFAULT_TARGET_HANDS - 1)
            write_gate(run_dir, 24_800, DEFAULT_TARGET_HANDS - 1)

            result = freeze_once(run_dir, retries=1)

            self.assertEqual(result["overall"], "WAITING")
            self.assertEqual(result["state"], "WAITING_FOR_FIRST_ELIGIBLE_PASS")
            self.assertIsNone(result["selected_gate"])
            self.assertFalse((run_dir / "exp003_judgment_archives").exists())

    def test_freezes_exact_first_eligible_pass_with_required_schema_and_sha(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            hands = DEFAULT_TARGET_HANDS + 900_000
            gate_path = write_gate(run_dir, 24_900, hands)
            write_checkpoint(run_dir / "latest.pt", 24_900, hands)

            result = freeze_once(run_dir, retries=1)
            persisted = json.loads((run_dir / "exp003_judgment_freeze_status.json").read_text(encoding="utf-8"))

            self.assertEqual(result["overall"], "PASS")
            self.assertEqual(result["target_hands"], DEFAULT_TARGET_HANDS)
            self.assertEqual(
                result["selected_gate"],
                {
                    "path": str(gate_path),
                    "iteration": 24_900,
                    "target_iteration": 24_900,
                    "checkpoint_hands": hands,
                    "overall": "PASS",
                },
            )
            archive = result["archive"]
            archive_path = Path(archive["path"])
            self.assertTrue(archive_path.is_file())
            self.assertEqual(archive["sha256"], digest(archive_path))
            self.assertEqual(
                archive["checkpoint"],
                {"iteration": 24_900, "total_hands": hands, "run_id": RUN_ID},
            )
            self.assertEqual(persisted["overall"], "PASS")
            self.assertEqual(persisted["archive"], archive)
            self.assertEqual(list((run_dir / "exp003_judgment_archives").glob("*.pt")), [archive_path])

    def test_missed_first_pass_fails_and_never_substitutes_later_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            first_hands = DEFAULT_TARGET_HANDS + 500_000
            later_hands = DEFAULT_TARGET_HANDS + 2_000_000
            write_gate(run_dir, 24_900, first_hands)
            write_gate(run_dir, 25_000, later_hands)
            write_checkpoint(run_dir / "latest.pt", 25_000, later_hands)

            first = freeze_once(run_dir, retries=1)
            # Even if the first gate artifact later disappears, the terminal FAIL
            # must remain sticky rather than selecting gate 25000.
            (run_dir / "gate_24900_status.json").unlink()
            second = freeze_once(run_dir, retries=1)

            self.assertEqual(first["overall"], "FAIL")
            self.assertEqual(first["state"], "MISSED_FIRST_ELIGIBLE_PASS")
            self.assertEqual(first["selected_gate"]["iteration"], 24_900)
            self.assertEqual(second["overall"], "FAIL")
            self.assertEqual(second["selected_gate"]["iteration"], 24_900)
            self.assertFalse((run_dir / "exp003_judgment_archives").exists())

    def test_same_iteration_with_different_hands_fails_exact_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            gate_hands = DEFAULT_TARGET_HANDS + 500_000
            write_gate(run_dir, 24_900, gate_hands)
            write_checkpoint(run_dir / "latest.pt", 24_900, gate_hands + 1)

            result = freeze_once(run_dir, retries=1)

            self.assertEqual(result["overall"], "FAIL")
            self.assertEqual(result["state"], "MISSED_FIRST_ELIGIBLE_PASS")
            self.assertIn("exact match required", result["reason"])

    def test_failed_gate_is_not_eligible_and_next_exact_pass_can_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            failed_hands = DEFAULT_TARGET_HANDS + 500_000
            pass_hands = DEFAULT_TARGET_HANDS + 2_000_000
            write_gate(run_dir, 24_900, failed_hands, overall="FAIL")
            pass_path = write_gate(run_dir, 25_000, pass_hands)
            write_checkpoint(run_dir / "latest.pt", 25_000, pass_hands)

            result = freeze_once(run_dir, retries=1)

            self.assertEqual(result["overall"], "PASS")
            self.assertEqual(result["selected_gate"]["path"], str(pass_path))
            self.assertEqual(result["selected_gate"]["iteration"], 25_000)

    def test_late_gate_artifact_cannot_label_a_newer_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            hands = DEFAULT_TARGET_HANDS + 2_000_000
            write_gate(run_dir, 24_900, hands, checkpoint_iteration=25_000)
            write_checkpoint(run_dir / "latest.pt", 25_000, hands)

            result = freeze_once(run_dir, retries=1)

            self.assertEqual(result["overall"], "FAIL")
            self.assertEqual(result["state"], "MISSED_FIRST_ELIGIBLE_PASS")
            self.assertIn("refusing to substitute", result["reason"])

    def test_filename_and_json_target_mismatch_cannot_freeze(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            hands = DEFAULT_TARGET_HANDS + 2_000_000
            path = run_dir / "gate_24900_status.json"
            path.write_text(
                json.dumps(
                    {
                        "overall": "PASS",
                        "target_iteration": 25_000,
                        "checkpoint_iteration": 25_000,
                        "checkpoint_hands": hands,
                        "run_id": RUN_ID,
                    }
                ),
                encoding="utf-8",
            )
            write_checkpoint(run_dir / "latest.pt", 25_000, hands)

            result = freeze_once(run_dir, retries=1)

            self.assertNotEqual(result["overall"], "PASS")
            self.assertIn("disagrees", result["gate_artifact_errors"][0]["error"])
            self.assertFalse((run_dir / "exp003_judgment_archives").exists())

    def test_verified_pass_is_idempotent_after_latest_advances(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            hands = DEFAULT_TARGET_HANDS + 500_000
            write_gate(run_dir, 24_900, hands)
            write_checkpoint(run_dir / "latest.pt", 24_900, hands)
            first = freeze_once(run_dir, retries=1)
            write_checkpoint(run_dir / "latest.pt", 25_000, hands + 2_000_000)

            second = freeze_once(run_dir, retries=1)

            self.assertEqual(first["overall"], "PASS")
            self.assertEqual(second["overall"], "PASS")
            self.assertEqual(second["selected_gate"]["iteration"], 24_900)
            self.assertEqual(second["archive"]["sha256"], first["archive"]["sha256"])


if __name__ == "__main__":
    unittest.main()
