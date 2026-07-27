#!/usr/bin/env python3
"""Fail-closed control-plane tests for official V5 Slumbot benchmarks."""

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

from v5_slumbot_benchmark_plan import evaluate_promotion20k_prerequisite, sha256_file, validate_terminal_endpoint_evidence
from v5_slumbot_benchmark_watch import promotion_gate_artifact_acceptable, run_benchmark_direct
from v5_slumbot_promotion_gate import validate_terminal_endpoint_health


class PromotionCheckpointIdentityTest(unittest.TestCase):
    def test_strong_gate_must_match_exact_formal_checkpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            gate_path = output_dir / "gate.json"
            gate_path.write_text(
                json.dumps(
                    {
                        "checkpoint": {"run_id": "run_a", "iteration": 10, "total_hands": 500_100_000},
                        "decisions": {"promotion_20k_strong": True, "promotion_20k_candidate": True},
                        "slumbot": {"hands": 20_400, "bb_per_100": 1.0, "lower_bound_bb_per_100": 0.1},
                    }
                ),
                encoding="utf-8",
            )
            args = argparse.Namespace(
                stage="formal100k",
                no_require_promotion20k=False,
                promotion_gate_json=str(gate_path),
            )
            mismatch = evaluate_promotion20k_prerequisite(
                args,
                output_dir,
                "run_a",
                {"run_id": "run_a", "iteration": 11, "total_hands": 501_700_000},
            )
            self.assertEqual(mismatch["status"], "FAIL")
            self.assertFalse(mismatch["promotion_gate"]["checkpoint_identity_matches"])

            match = evaluate_promotion20k_prerequisite(
                args,
                output_dir,
                "run_a",
                {"run_id": "run_a", "iteration": 10, "total_hands": 500_100_000},
            )
            self.assertEqual(match["status"], "PASS")
            self.assertTrue(match["promotion_gate"]["checkpoint_identity_matches"])


class TerminalEndpointHealthTest(unittest.TestCase):
    def test_exact_terminal_endpoint_and_protocol_pass(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint_path = root / "endpoint.pt"
            checkpoint_path.write_bytes(b"frozen-checkpoint")
            checkpoint = {"run_id": "run_terminal", "iteration": 42, "total_hands": 123456}
            manifest = {"status": "finished", "iteration": 42, "total_hands": 123456}
            endpoint_path = root / "endpoint.json"
            protocol_path = root / "protocol.json"
            endpoint_path.write_text(
                json.dumps(
                    {
                        "overall": "PASS",
                        "state": "ARM_ENDPOINT_FROZEN",
                        "arm": "treatment",
                        "checkpoint_path": str(checkpoint_path),
                        "checkpoint_sha256": sha256_file(checkpoint_path),
                        "iteration": 42,
                        "hands": 123456,
                        "run_id": "run_terminal",
                    }
                ),
                encoding="utf-8",
            )
            protocol_path.write_text(
                json.dumps({"overall": "PASS", "state": "ARM_FINISHED_GUARDS_PASS", "arm": "treatment"}),
                encoding="utf-8",
            )
            ok, detail, payload = validate_terminal_endpoint_evidence(
                checkpoint_path=checkpoint_path,
                checkpoint=checkpoint,
                manifest=manifest,
                endpoint_status_path=endpoint_path,
                protocol_status_path=protocol_path,
            )
            self.assertTrue(ok, detail)
            self.assertEqual(payload["checkpoint_sha256"], sha256_file(checkpoint_path))

    def test_terminal_checkpoint_hash_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            checkpoint_path = root / "endpoint.pt"
            checkpoint_path.write_bytes(b"frozen-checkpoint")
            checkpoint = {"run_id": "run_terminal", "iteration": 42, "total_hands": 123456}
            manifest = {"status": "finished", "iteration": 42, "total_hands": 123456}
            endpoint_path = root / "endpoint.json"
            protocol_path = root / "protocol.json"
            endpoint_path.write_text(
                json.dumps(
                    {
                        "overall": "PASS",
                        "state": "ARM_ENDPOINT_FROZEN",
                        "arm": "treatment",
                        "checkpoint_path": str(checkpoint_path),
                        "checkpoint_sha256": "0" * 64,
                        "iteration": 42,
                        "hands": 123456,
                        "run_id": "run_terminal",
                    }
                ),
                encoding="utf-8",
            )
            protocol_path.write_text(
                json.dumps({"overall": "PASS", "state": "ARM_FINISHED_GUARDS_PASS", "arm": "treatment"}),
                encoding="utf-8",
            )
            ok, detail, _ = validate_terminal_endpoint_evidence(
                checkpoint_path=checkpoint_path,
                checkpoint=checkpoint,
                manifest=manifest,
                endpoint_status_path=endpoint_path,
                protocol_status_path=protocol_path,
            )
            self.assertFalse(ok)
            self.assertIn("SHA256 mismatch", detail)

    def test_frozen_benchmark_copy_matches_terminal_endpoint(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "run"
            run_dir.mkdir()
            endpoint_checkpoint = run_dir / "endpoint.pt"
            endpoint_checkpoint.write_bytes(b"same-frozen-checkpoint")
            benchmark_checkpoint = root / "benchmark.pt"
            benchmark_checkpoint.write_bytes(endpoint_checkpoint.read_bytes())
            checkpoint = {"run_id": "run_terminal", "iteration": 42, "total_hands": 123456}
            (run_dir / "run_manifest.json").write_text(
                json.dumps({"status": "finished", "run_id": "run_terminal", "iteration": 42, "total_hands": 123456}),
                encoding="utf-8",
            )
            endpoint_path = run_dir / "endpoint.json"
            protocol_path = run_dir / "protocol.json"
            endpoint_path.write_text(
                json.dumps(
                    {
                        "overall": "PASS",
                        "state": "ARM_ENDPOINT_FROZEN",
                        "arm": "treatment",
                        "checkpoint_path": str(endpoint_checkpoint),
                        "checkpoint_sha256": sha256_file(endpoint_checkpoint),
                        "iteration": 42,
                        "hands": 123456,
                        "run_id": "run_terminal",
                    }
                ),
                encoding="utf-8",
            )
            protocol_path.write_text(
                json.dumps({"overall": "PASS", "state": "ARM_FINISHED_GUARDS_PASS", "arm": "treatment"}),
                encoding="utf-8",
            )
            ok, detail, payload = validate_terminal_endpoint_health(
                checkpoint_path=benchmark_checkpoint,
                checkpoint=checkpoint,
                run_dir=run_dir,
                endpoint_status_path=endpoint_path,
                protocol_status_path=protocol_path,
            )
            self.assertTrue(ok, detail)
            self.assertEqual(payload["benchmark_checkpoint_sha256"], sha256_file(endpoint_checkpoint))


class Quick5kPromotionArtifactTest(unittest.TestCase):
    def test_expected_promotion_hands_block_is_artifact_complete(self):
        accepted, detail = promotion_gate_artifact_acceptable(
            "quick5k",
            1,
            {"checks": [{"name": "promotion_hands", "status": "FAIL"}]},
        )
        self.assertTrue(accepted, detail)

    def test_unexpected_health_failure_is_rejected(self):
        accepted, _ = promotion_gate_artifact_acceptable(
            "quick5k",
            1,
            {
                "checks": [
                    {"name": "promotion_hands", "status": "FAIL"},
                    {"name": "terminal_endpoint_health", "status": "FAIL"},
                ]
            },
        )
        self.assertFalse(accepted)


class BelowNormalFailClosedTest(unittest.TestCase):
    class FakeProcess:
        def __init__(self) -> None:
            self.pid = 12345
            self.returncode = None

        def poll(self):
            return self.returncode

        def terminate(self) -> None:
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

        def kill(self) -> None:
            self.returncode = -9

    def test_priority_setup_failure_aborts_direct_bundle(self):
        with tempfile.TemporaryDirectory() as tmp:
            output_dir = Path(tmp)
            args = argparse.Namespace(
                no_direct_low_priority=False,
                direct_stall_timeout_seconds=600.0,
                direct_poll_seconds=1.0,
                run_dir="run",
                policy_mode="greedy",
                temperature=1.0,
                guarded_allin_max_spr=2.0,
                guarded_allin_min_prob=0.65,
                callguard_min_prob=0.2,
                callguard_ratio=0.65,
                callguard_include_open=False,
            )
            plan = {
                "output_dir": str(output_dir),
                "tag": "priority_test",
                "sessions": 1,
                "hands_per_session": 1,
                "planned_hands": 1,
                "run_dir": "run",
                "artifacts": {},
            }
            with patch("v5_slumbot_benchmark_watch.subprocess.Popen", return_value=self.FakeProcess()), patch(
                "v5_slumbot_benchmark_watch.set_below_normal",
                return_value={"status": "WARN", "error": "denied"},
            ):
                result = run_benchmark_direct(args, plan, Path("frozen.pt"))
            self.assertEqual(result["status"], "FAIL")
            self.assertTrue(any("BelowNormal priority setup failed" in row for row in result["failures"]))


if __name__ == "__main__":
    unittest.main()
