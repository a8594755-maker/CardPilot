#!/usr/bin/env python3
"""Focused tests for V5 next-action queue Slumbot loss-trend gating."""

from __future__ import annotations

import sys
import hashlib
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_next_action_queue import (
    EXP003_CI_PRECISION_FAILED,
    EXP003_CUTOVER_HANDS,
    EXP003_EVALUATOR_SHA256,
    EXP003_MIRROR_PAIRS,
    EXP003_MIRROR_POLICY_MODE,
    EXP003_MIRROR_SEED,
    EXP003_NATIVE_ANCHOR_HANDS,
    EXP003_NATIVE_MIRROR_TARGET_HANDS,
    EXP003_NATIVE_SHA256,
    EXP003_PRE_SHA256,
    build_queue,
    build_slumbot_loss_trend_item,
    claim_reference_from_strength,
    exp003_mirror_bundle_status,
    exp003_mirror_queue_instruction,
    external_eval_descriptor,
    latest_promotion20k_prerequisite,
    throughput_queue_policy,
)
import v5_next_action_queue as queue_module


CI_PATH = Path("models/bench_v55_example_100M_quick5k_ci_summary.json")
POST_SHA256 = hashlib.sha256(b"frozen-post").hexdigest()


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
    candidate_bb100: float = 20.0,
    candidate_ci95_bb100: float = 10.0,
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
                    "target_iteration": candidate_iteration,
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
        "pid": 1234,
        "command": ["python", "v5_mirror_eval.py"],
        "working_directory": str(run_dir),
        "status": "COMPLETED",
        "torch_threads": 1,
        "torch_interop_threads": 1,
        "priority": {"applied": True, "actual_label": "BelowNormal"},
    }
    role_name = (
        "pre_vs_native"
        if candidate_hands == EXP003_CUTOVER_HANDS
        else "post_vs_native"
        if anchor_hands == EXP003_NATIVE_ANCHOR_HANDS
        else "post_vs_pre_direct"
    )
    input_hashes = {
        "evaluator": EXP003_EVALUATOR_SHA256,
        "candidate": candidate_sha256,
        "anchor": anchor_sha256,
    }
    payload = {
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
                        "candidate_bb100": candidate_bb100,
                        "candidate_ci95_bb100": candidate_ci95_bb100,
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
    path.write_text(json.dumps(payload), encoding="utf-8")
    stem = str(path)[:-5]
    Path(stem + ".md").write_text("mirror\n", encoding="utf-8")
    Path(stem + ".stdout.log").write_text(json.dumps(payload), encoding="utf-8")
    Path(stem + ".stderr.log").write_text("", encoding="utf-8")
    Path(stem + ".execution.json").write_text(json.dumps(execution), encoding="utf-8")
    Path(stem + ".launcher.json").write_text(
        json.dumps(
            {
                "role": role_name,
                "attempt": 1,
                "pid": execution["pid"],
                "process_creation_date": "created",
                "process_command_line": "python v5_mirror_eval.py",
                "evaluator_sha256": EXP003_EVALUATOR_SHA256,
                "candidate_sha256": candidate_sha256,
                "anchor_sha256": anchor_sha256,
                "pairs": EXP003_MIRROR_PAIRS,
                "seed": EXP003_MIRROR_SEED,
                "starting_stack": 200.0,
                "device": "cpu",
                "priority": "below-normal",
                "state": "COMPLETED",
                "return_code": 0,
                "input_sha256_pre": input_hashes,
                "input_sha256_post": input_hashes,
                "posthash_error": None,
                "contention_detected": False,
                "contention_snapshots": [],
                "contention_monitor_errors": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def fingerprint(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
    }


def write_synthetic_contention_reaudit(run_dir: Path, result_path: Path) -> dict[str, object]:
    """Build a tiny hash-bound recovery fixture under patched allowlist IDs."""

    launcher_path = Path(str(result_path)[:-5] + ".launcher.json")
    launcher = json.loads(launcher_path.read_text(encoding="utf-8"))
    observer_command = "synthetic registered observer"
    snapshot = {
        "busy": True,
        "checked_at": "synthetic-check",
        "slumbot_running_statuses": [],
        "processes": [
            {
                "pid": 71,
                "creation_date": "synthetic-created",
                "command_line": observer_command,
                "name": "powershell.exe",
            }
        ],
    }
    launcher["contention_detected"] = True
    launcher["contention_snapshots"] = [snapshot]
    launcher["contention_monitor_errors"] = []
    launcher_path.write_text(json.dumps(launcher), encoding="utf-8")

    staging = run_dir / "exp003_bundle_staging" / "post_vs_native_attempt1"
    staging.mkdir(parents=True)
    canonical_paths = {
        "result": result_path,
        "markdown": Path(str(result_path)[:-5] + ".md"),
        "stdout": Path(str(result_path)[:-5] + ".stdout.log"),
        "stderr": Path(str(result_path)[:-5] + ".stderr.log"),
        "execution": Path(str(result_path)[:-5] + ".execution.json"),
        "launcher": launcher_path,
    }
    staged_paths = {
        name: staging / f"payload{suffix}"
        for name, suffix in {
            "result": ".json",
            "markdown": ".md",
            "stdout": ".stdout.log",
            "stderr": ".stderr.log",
            "execution": ".execution.json",
            "launcher": ".launcher.json",
        }.items()
    }
    for name, canonical in canonical_paths.items():
        shutil.copyfile(canonical, staged_paths[name])
    quarantine_path = staging / "quarantine.json"
    quarantine_path.write_text(
        json.dumps(
            {
                "state": "QUARANTINED",
                "published": False,
                "role": "post_vs_native",
                "evidence": [snapshot],
            }
        ),
        encoding="utf-8",
    )
    terminal_status_path = run_dir / "v5_exp003_bundle_watch_status.json"
    terminal_status = {
        "overall": "FAIL",
        "terminal": True,
        "state": "MEASUREMENT_CONTENTION_QUARANTINED",
    }
    with terminal_status_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(terminal_status, indent=2, sort_keys=True) + "\n")
    expected = {
        "command_line_sha256": hashlib.sha256(observer_command.encode("utf-8")).hexdigest(),
        "script_sha256": hashlib.sha256(b"synthetic-script").hexdigest(),
        "pid": 71,
        "creation_date": "synthetic-created",
        "checked_at": "synthetic-check",
        "snapshot_sha256": queue_module._canonical_json_sha256(snapshot),
        "launcher_sha256": fingerprint(staged_paths["launcher"])["sha256"],
        "quarantine_sha256": fingerprint(quarantine_path)["sha256"],
    }
    certificate_path = Path(str(result_path)[:-5] + ".contention_reaudit.json")
    staged_certificate_path = staging / "payload.contention_reaudit.json"
    source_raw = {name: fingerprint(path) for name, path in staged_paths.items()}
    classifier_process = {
        "status": "PASS",
        "pid": expected["pid"],
        "creation_date": expected["creation_date"],
        "classification": {
            "status": "PASS",
            "command_line_sha256": expected["command_line_sha256"],
            "script_sha256": expected["script_sha256"],
            "corrected_eval_invocation": [],
            "historical_allowlist": {
                "command_line_sha256": expected["command_line_sha256"],
                "script_sha256": expected["script_sha256"],
            },
        },
    }
    certificate = {
        "schema_version": queue_module.EXP003_CONTENTION_REAUDIT_SCHEMA_VERSION,
        "state": "FALSE_POSITIVE_CONTENTION_REAUDIT_PASS",
        "role": "post_vs_native",
        "attempt": 1,
        "staged_companion_path": str(staged_certificate_path),
        "canonical_companion_path": str(certificate_path),
        "source": {
            "launcher": source_raw["launcher"],
            "quarantine": fingerprint(quarantine_path),
            "terminal_status": fingerprint(terminal_status_path),
            "raw_artifacts": source_raw,
        },
        "terminal_status_snapshot": terminal_status,
        "terminal_status_snapshot_sha256": fingerprint(terminal_status_path)["sha256"],
        "classifier": {
            "status": "PASS",
            "all_saved_snapshots_covered": True,
            "launcher_quarantine_snapshots_exact_match": True,
            "launcher_snapshot_count": 1,
            "quarantine_snapshot_count": 1,
            "snapshots": [
                {
                    "status": "PASS",
                    "snapshot_sha256": expected["snapshot_sha256"],
                    "historical_allowlist": {
                        "pid": expected["pid"],
                        "creation_date": expected["creation_date"],
                        "checked_at": expected["checked_at"],
                        "snapshot_sha256": expected["snapshot_sha256"],
                    },
                    "busy": True,
                    "slumbot_running_statuses": [],
                    "processes": [classifier_process],
                }
            ],
        },
        "raw_audit": {
            "status": "PASS",
            "structural_checks": {"all": True},
            "input_sha256_actual": launcher["input_sha256_pre"],
            "raw_contention_clean": False,
            "reaudited_contention_exception_used": True,
        },
        "forensic_verdict": "PASS",
        "all_saved_contention_snapshots_reclassified": True,
        "no_slumbot_blocking_state": True,
        "no_monitor_errors": True,
        "raw_identity_protocol_audit_pass": True,
        "recovery_eligible": True,
        "recovery_scope": queue_module.EXP003_CONTENTION_RECOVERY_SCOPE,
        "original_launcher_and_quarantine_preserved": True,
    }
    encoded = json.dumps(certificate, indent=2, sort_keys=True) + "\n"
    staged_certificate_path.write_text(encoded, encoding="utf-8")
    certificate_path.write_text(encoded, encoding="utf-8")
    return expected


class GateStatusIdentityFilterTest(unittest.TestCase):
    @staticmethod
    def _write_gate(
        run_dir: Path,
        filename_iteration: int,
        *,
        target_iteration: int | str | None,
        checkpoint_iteration: int,
        checkpoint_hands: int,
        overall: str = "PASS",
        include_target_iteration: bool = True,
        nested_checkpoint: bool = False,
    ) -> Path:
        path = run_dir / f"gate_{filename_iteration}_status.json"
        payload = {"overall": overall}
        if nested_checkpoint:
            payload["checkpoint"] = {
                "iteration": checkpoint_iteration,
                "total_hands": checkpoint_hands,
            }
        else:
            payload.update(
                {
                    "checkpoint_iteration": checkpoint_iteration,
                    "checkpoint_hands": checkpoint_hands,
                }
            )
        if include_target_iteration:
            payload["target_iteration"] = target_iteration
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_stale_gate_name_target_checkpoint_mismatch_is_quarantined_before_selection(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            target_hands = 418_930_351
            historical = self._write_gate(
                run_dir,
                24_900,
                target_iteration=24_900,
                checkpoint_iteration=24_900,
                checkpoint_hands=409_058_520,
            )
            stale_paths = [
                self._write_gate(
                    run_dir,
                    iteration,
                    target_iteration=iteration,
                    checkpoint_iteration=25_500,
                    checkpoint_hands=target_hands,
                )
                for iteration in range(12_900, 14_100, 100)
            ]
            valid = self._write_gate(
                run_dir,
                25_600,
                target_iteration=25_600,
                checkpoint_iteration=25_600,
                checkpoint_hands=target_hands,
            )
            pending = self._write_gate(
                run_dir,
                25_700,
                target_iteration=25_700,
                checkpoint_iteration=25_500,
                checkpoint_hands=target_hands,
                overall="PENDING",
            )

            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, target_hands)
            selected = queue_module._first_eligible_exp003_gate(run_dir, target_hands)

        self.assertEqual([Path(row["path"]) for row in eligible], [valid])
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(Path(selected["path"]), valid)
        self.assertEqual(len(quarantined), len(stale_paths))
        self.assertEqual({Path(row["path"]) for row in quarantined}, set(stale_paths))
        self.assertTrue(all(row["status"] == "QUARANTINED" for row in quarantined))
        self.assertTrue(all("disagree" in row["reason"] for row in quarantined))
        self.assertNotIn(historical, {Path(row["path"]) for row in quarantined})
        self.assertNotIn(pending, {Path(row["path"]) for row in quarantined})

    def test_present_null_target_iteration_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            malformed_target = self._write_gate(
                run_dir,
                25_600,
                target_iteration=None,
                checkpoint_iteration=25_600,
                checkpoint_hands=418_930_351,
            )

            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, 418_930_351)
            selected = queue_module._first_eligible_exp003_gate(run_dir, 418_930_351)

        self.assertEqual(eligible, [])
        self.assertIsNone(selected)
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(Path(quarantined[0]["path"]), malformed_target)
        self.assertIn("target_iteration", quarantined[0]["reason"])

    def test_absent_target_iteration_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            missing_target = self._write_gate(
                run_dir,
                24_900,
                target_iteration=None,
                include_target_iteration=False,
                checkpoint_iteration=24_900,
                checkpoint_hands=409_058_520,
            )

            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, 408_064_575)
            selected = queue_module._first_eligible_exp003_gate(run_dir, 408_064_575)

        self.assertEqual(eligible, [])
        self.assertIsNone(selected)
        self.assertEqual(len(quarantined), 1)
        self.assertEqual(Path(quarantined[0]["path"]), missing_target)
        self.assertIn("target_iteration", quarantined[0]["reason"])

    def test_nested_checkpoint_legacy_schema_is_preserved_when_identity_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            legacy = self._write_gate(
                run_dir,
                24_900,
                target_iteration=24_900,
                checkpoint_iteration=24_900,
                checkpoint_hands=409_058_520,
                nested_checkpoint=True,
            )

            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, 408_064_575)
            selected = queue_module._first_eligible_exp003_gate(run_dir, 408_064_575)

        self.assertEqual(len(eligible), 1)
        self.assertEqual(Path(eligible[0]["path"]), legacy)
        self.assertEqual(eligible[0]["checkpoint_iteration_source"], "checkpoint.iteration")
        self.assertEqual(quarantined, [])
        self.assertIsNotNone(selected)
        assert selected is not None
        self.assertEqual(Path(selected["path"]), legacy)

    def test_conflicting_or_malformed_dual_checkpoint_fields_fail_closed(self):
        target_hands = 418_930_351
        cases = (
            (
                "iteration_conflict",
                {"iteration": 25_700, "total_hands": target_hands},
                {},
                "checkpoint_iteration conflicts with checkpoint.iteration",
            ),
            (
                "null_top_iteration",
                {"iteration": 25_600, "total_hands": target_hands},
                {"checkpoint_iteration": None},
                "checkpoint_iteration or checkpoint.iteration is not a strict integer",
            ),
            (
                "hands_conflict",
                {"iteration": 25_600, "total_hands": target_hands + 1},
                {},
                "checkpoint_hands conflicts with checkpoint.total_hands",
            ),
        )
        for label, nested_checkpoint, top_overrides, reason in cases:
            with self.subTest(case=label), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                path = self._write_gate(
                    run_dir,
                    25_600,
                    target_iteration=25_600,
                    checkpoint_iteration=25_600,
                    checkpoint_hands=target_hands,
                )
                payload = json.loads(path.read_text(encoding="utf-8"))
                payload["checkpoint"] = nested_checkpoint
                payload.update(top_overrides)
                path.write_text(json.dumps(payload), encoding="utf-8")

                eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, target_hands)
                selected = queue_module._first_eligible_exp003_gate(run_dir, target_hands)

                self.assertEqual(eligible, [])
                self.assertIsNone(selected)
                self.assertEqual(len(quarantined), 1)
                self.assertEqual(quarantined[0]["status"], "QUARANTINED")
                self.assertIn(reason, quarantined[0]["reason"])

    def test_matching_dual_checkpoint_fields_are_accepted(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            path = self._write_gate(
                run_dir,
                25_600,
                target_iteration=25_600,
                checkpoint_iteration=25_600,
                checkpoint_hands=418_930_351,
            )
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["checkpoint"] = {"iteration": 25_600, "total_hands": 418_930_351}
            path.write_text(json.dumps(payload), encoding="utf-8")

            eligible, quarantined = queue_module._eligible_exp003_gates(run_dir, 418_930_351)

        self.assertEqual(len(eligible), 1)
        self.assertEqual(eligible[0]["checkpoint_iteration_source"], "checkpoint_iteration+checkpoint.iteration")
        self.assertEqual(eligible[0]["checkpoint_hands_source"], "checkpoint_hands+checkpoint.total_hands")
        self.assertEqual(quarantined, [])


class Exp003CausalMirrorBundleTest(unittest.TestCase):
    def test_candidate_only_is_not_done(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post = write_exp003_mirror(
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
                candidate_bb100=-20.0,
            )
            post = write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_bb100=20.0,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW_READY")
        self.assertEqual(status["candidate_checkpoint_hands"], post_hands)
        self.assertEqual(status["freeze"]["archive_sha256"], POST_SHA256)
        self.assertEqual(status["first_eligible_gate"]["hands"], post_hands)
        self.assertIn("not an ADOPT/ROLLBACK decision", status["detail"])

    def test_freeze_cannot_substitute_a_quarantined_gate_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=-20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_bb100=20.0,
            )
            stale_gate = run_dir / "gate_12900_status.json"
            stale_gate.write_text(
                json.dumps(
                    {
                        "overall": "PASS",
                        "target_iteration": 12_900,
                        "checkpoint_iteration": 25_500,
                        "checkpoint_hands": post_hands,
                    }
                ),
                encoding="utf-8",
            )
            freeze_path = run_dir / "exp003_judgment_freeze_status.json"
            freeze = json.loads(freeze_path.read_text(encoding="utf-8"))
            freeze["selected_gate"]["path"] = str(stale_gate)
            freeze_path.write_text(json.dumps(freeze), encoding="utf-8")

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "INCOMPLETE")
        self.assertIn("first_eligible_pass_freeze", status["detail"])
        self.assertEqual(Path(status["first_eligible_gate"]["path"]).name, "gate_24900_status.json")
        self.assertEqual([Path(row["path"]).name for row in status["quarantined_gate_statuses"]], [stale_gate.name])

    def test_duplicate_matching_canonical_role_fails_closed_instead_of_selecting_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            # This represents an unregistered second same-role measurement.
            # It must not be hidden by preferring the first usable artifact.
            write_exp003_mirror(
                run_dir,
                "pre_native_extra_pairs",
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
        self.assertIn("duplicate canonical EXP-003 artifacts", status["detail"])
        self.assertIn("pre_vs_native", status["duplicate_role_artifacts"])
        self.assertEqual(len(status["duplicate_role_artifacts"]["pre_vs_native"]), 2)

    def test_duplicate_role_blocks_ci_precision_inconclusive_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            for name, candidate_hands, anchor_hands in (
                ("pre_native", EXP003_CUTOVER_HANDS, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_native", post_hands, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_direct", post_hands, EXP003_CUTOVER_HANDS),
                ("post_direct_duplicate", post_hands, EXP003_CUTOVER_HANDS),
            ):
                write_exp003_mirror(
                    run_dir,
                    name,
                    candidate_hands=candidate_hands,
                    anchor_hands=anchor_hands,
                    candidate_ci95_bb100=21.0,
                    ci_ok=False,
                )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("post_vs_pre_direct", status["duplicate_role_artifacts"])
        self.assertNotEqual(status["status"], EXP003_CI_PRECISION_FAILED)

    def test_contention_launcher_requires_hash_bound_recovery_and_cert_mutation_reopens_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=-20.0,
            )
            post_native = write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_bb100=20.0,
            )
            expected_allowlist = write_synthetic_contention_reaudit(run_dir, post_native)

            with patch.object(queue_module, "EXP003_CAPTURED_FALSE_POSITIVE_OBSERVER", expected_allowlist):
                before = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                self.assertEqual(before["status"], "REVIEW_READY", before)
                recovered = before["roles"]["post_vs_native"]
                self.assertEqual(recovered["launcher_recovery"]["status"], "PASS")
                self.assertIn("contention_reaudit", recovered["companion_paths"])
                artifact_hashes = {
                    role: {
                        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in [Path(record["path"]), *(Path(value) for value in record["companion_paths"].values())]
                    }
                    for role, record in before["roles"].items()
                }
                (run_dir / "v5_exp003_judgment.json").write_text(
                    json.dumps(
                        {
                            "schema_version": "v5.exp003.judgment.v1",
                            "checked_at": "2026-07-10T00:00:00+00:00",
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
                            "mirror_artifact_sha256": artifact_hashes,
                        }
                    ),
                    encoding="utf-8",
                )
                closed = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                certificate_path = Path(recovered["companion_paths"]["contention_reaudit"])
                certificate_path.write_text("mutated\n", encoding="utf-8")
                reopened = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                certificate_path.unlink()
                deleted = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(closed["status"], "ADOPT_CLOSED")
        self.assertEqual(reopened["status"], "REVIEW")
        self.assertEqual(deleted["status"], "REVIEW")

    def test_uncertified_launcher_contention_remains_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            post_native = write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            launcher_path = Path(str(post_native)[:-5] + ".launcher.json")
            launcher = json.loads(launcher_path.read_text(encoding="utf-8"))
            launcher["contention_detected"] = True
            launcher["contention_snapshots"] = [{"busy": True}]
            launcher_path.write_text(json.dumps(launcher), encoding="utf-8")
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("post_vs_native", status["detail"])

    def test_legacy_pre_provenance_is_inconclusive_only_and_hash_bound(self):
        def prepare(*, post_ci_failed: bool):
            tmp = tempfile.TemporaryDirectory()
            run_dir = Path(tmp.name)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            pre = write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=-20.0,
            )
            pre_launcher_path = Path(str(pre)[:-5] + ".launcher.json")
            pre_launcher = json.loads(pre_launcher_path.read_text(encoding="utf-8"))
            pre_launcher["state"] = "LEGACY_UNAVAILABLE"
            pre_launcher_path.write_text(json.dumps(pre_launcher), encoding="utf-8")
            post = write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=0.0,
                candidate_ci95_bb100=21.0 if post_ci_failed else 10.0,
                ci_ok=not post_ci_failed,
            )
            recovery_cert = Path(str(post)[:-5] + ".contention_reaudit.json")
            if post_ci_failed:
                post_launcher_path = Path(str(post)[:-5] + ".launcher.json")
                post_launcher = json.loads(post_launcher_path.read_text(encoding="utf-8"))
                post_launcher["contention_detected"] = True
                post_launcher["contention_snapshots"] = [{"busy": True, "synthetic": "recovered"}]
                post_launcher_path.write_text(json.dumps(post_launcher), encoding="utf-8")
                recovery_cert.write_text("post-recovery-cert\n", encoding="utf-8")
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_bb100=0.0,
            )
            cert = Path(str(pre)[:-5] + ".legacy_provenance.json")
            audit = Path(str(pre)[:-5] + ".legacy_provenance_audit.json")
            cert.write_text("legacy-cert\n", encoding="utf-8")
            audit.write_text("legacy-audit\n", encoding="utf-8")

            def fake_legacy(record, role):
                if role != "pre_vs_native" or not cert.is_file() or not audit.is_file():
                    return {"status": "FAIL", "reason": "missing legacy companion"}
                if cert.read_text(encoding="utf-8") != "legacy-cert\n" or audit.read_text(encoding="utf-8") != "legacy-audit\n":
                    return {"status": "FAIL", "reason": "mutated legacy companion"}
                return {
                    "status": "PASS",
                    "path": str(cert),
                    "audit_path": str(audit),
                    "sha256": hashlib.sha256(cert.read_bytes()).hexdigest(),
                    "audit_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
                }

            def fake_recovery(record, role):
                if role != "post_vs_native" or not recovery_cert.is_file():
                    return {"status": "FAIL", "reason": "missing recovered post role"}
                if recovery_cert.read_text(encoding="utf-8") != "post-recovery-cert\n":
                    return {"status": "FAIL", "reason": "mutated recovered post certificate"}
                return {
                    "status": "PASS",
                    "path": str(recovery_cert),
                    "sha256": hashlib.sha256(recovery_cert.read_bytes()).hexdigest(),
                }

            return tmp, run_dir, post_hands, cert, audit, fake_legacy, fake_recovery

        all_pass_tmp, all_pass_run, _, _, _, all_pass_legacy, _ = prepare(post_ci_failed=False)
        try:
            with patch.object(queue_module, "_legacy_pre_provenance_certificate", side_effect=all_pass_legacy):
                all_pass = exp003_mirror_bundle_status(all_pass_run, EXP003_NATIVE_MIRROR_TARGET_HANDS)
        finally:
            all_pass_tmp.cleanup()
        self.assertEqual(all_pass["status"], "REVIEW")
        legacy_role = all_pass["roles"]["pre_vs_native"]
        self.assertTrue(legacy_role["legacy_inconclusive_only"])
        self.assertFalse(legacy_role["launcher_evidence_ok"])
        self.assertFalse(legacy_role["judgmentable"])
        self.assertFalse(legacy_role["usable"])
        self.assertIsNone(all_pass["legacy_preflight_contract"])

        tmp, run_dir, post_hands, cert, audit, fake_legacy, fake_recovery = prepare(post_ci_failed=True)
        try:
            with (
                patch.object(queue_module, "_legacy_pre_provenance_certificate", side_effect=fake_legacy),
                patch.object(queue_module, "_recovered_launcher_certificate", side_effect=fake_recovery),
            ):
                before = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                self.assertEqual(before["status"], EXP003_CI_PRECISION_FAILED, before)
                self.assertIn("legacy_provenance", before["roles"]["pre_vs_native"]["companion_paths"])
                self.assertEqual(before["ci_precision_failed_roles"], ["post_vs_native"])
                self.assertIsNotNone(before["legacy_preflight_contract"])
                artifact_hashes = {
                    role: {
                        str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                        for path in [Path(record["path"]), *(Path(value) for value in record["companion_paths"].values())]
                    }
                    for role, record in before["roles"].items()
                }
                judgment = {
                    "schema_version": "v5.exp003.judgment.v1",
                    "checked_at": "2026-07-10T00:00:00+00:00",
                    "measurement_status": EXP003_CI_PRECISION_FAILED,
                    "decision": "ADOPT",
                    "decision_valid": True,
                    "candidate_checkpoint_hands": post_hands,
                    "candidate_checkpoint_sha256": POST_SHA256,
                    "effects": {
                        "native_axis": {"status": "INCONCLUSIVE"},
                        "direct_causal": {"status": "INCONCLUSIVE"},
                    },
                    "hard_guards": {"status": "PASS"},
                    "method_support": {
                        "value_loss": {"status": "INCONCLUSIVE"},
                        "postflop_raise_plus_allin": {"status": "INCONCLUSIVE"},
                    },
                    "ci_precision_gate": {"status": "FAIL", "failed_roles": ["post_vs_native"]},
                    "legacy_inconclusive_roles": ["pre_vs_native"],
                    "legacy_preflight_contract": before["legacy_preflight_contract"],
                    "mirror_artifact_sha256": artifact_hashes,
                }
                judgment_path = run_dir / "v5_exp003_judgment.json"
                judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
                self.assertEqual(
                    exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)["status"],
                    EXP003_CI_PRECISION_FAILED,
                )
                judgment["decision"] = "ROLLBACK"
                judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
                self.assertEqual(
                    exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)["status"],
                    EXP003_CI_PRECISION_FAILED,
                )
                judgment["decision"] = "INCONCLUSIVE"
                path_fields = {
                    "result_path",
                    "provenance_path",
                    "audit_path",
                    "post_vs_native_result_path",
                    "post_vs_native_contention_reaudit_path",
                }
                judgment["legacy_preflight_contract"] = {
                    key: (
                        os.path.relpath(value, Path.cwd())
                        if key in path_fields
                        else value
                    )
                    for key, value in judgment["legacy_preflight_contract"].items()
                }
                judgment["mirror_artifact_sha256"] = {
                    role: {
                        os.path.relpath(path, Path.cwd()): digest
                        for path, digest in hashes.items()
                    }
                    for role, hashes in judgment["mirror_artifact_sha256"].items()
                }
                judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
                closed = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                tampered_judgment = json.loads(json.dumps(judgment))
                tampered_role = "post_vs_native"
                tampered_path = next(iter(tampered_judgment["mirror_artifact_sha256"][tampered_role]))
                tampered_judgment["mirror_artifact_sha256"][tampered_role][tampered_path] = "0" * 64
                judgment_path.write_text(json.dumps(tampered_judgment), encoding="utf-8")
                tampered_hash = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
                cert.write_text("mutated\n", encoding="utf-8")
                reopened_cert = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                cert.unlink()
                reopened_deleted_cert = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                cert.write_text("legacy-cert\n", encoding="utf-8")
                audit.write_text("mutated\n", encoding="utf-8")
                reopened_audit = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
                audit.unlink()
                reopened_deleted_audit = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
        finally:
            tmp.cleanup()

        self.assertEqual(closed["status"], "INCONCLUSIVE_BLOCKED")
        self.assertEqual(tampered_hash["status"], EXP003_CI_PRECISION_FAILED)
        self.assertEqual(reopened_cert["status"], "REVIEW")
        self.assertEqual(reopened_deleted_cert["status"], "REVIEW")
        self.assertEqual(reopened_audit["status"], "REVIEW")
        self.assertEqual(reopened_deleted_audit["status"], "REVIEW")

    def test_legacy_contract_is_visible_after_recovered_role2_while_role3_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            pre = write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
            )
            pre_launcher_path = Path(str(pre)[:-5] + ".launcher.json")
            pre_launcher = json.loads(pre_launcher_path.read_text(encoding="utf-8"))
            pre_launcher["state"] = "LEGACY_UNAVAILABLE"
            pre_launcher_path.write_text(json.dumps(pre_launcher), encoding="utf-8")
            post = write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )
            post_launcher_path = Path(str(post)[:-5] + ".launcher.json")
            post_launcher = json.loads(post_launcher_path.read_text(encoding="utf-8"))
            post_launcher["contention_detected"] = True
            post_launcher["contention_snapshots"] = [{"busy": True, "synthetic": "recovered"}]
            post_launcher_path.write_text(json.dumps(post_launcher), encoding="utf-8")
            provenance = Path(str(pre)[:-5] + ".legacy_provenance.json")
            audit = Path(str(pre)[:-5] + ".legacy_provenance_audit.json")
            reaudited = Path(str(post)[:-5] + ".contention_reaudit.json")
            provenance.write_text("legacy-provenance\n", encoding="utf-8")
            audit.write_text("legacy-audit\n", encoding="utf-8")
            reaudited.write_text("post-recovery\n", encoding="utf-8")

            def fake_legacy(record, role):
                if role != "pre_vs_native" or not provenance.is_file() or not audit.is_file():
                    return {"status": "FAIL"}
                return {
                    "status": "PASS",
                    "path": str(provenance),
                    "sha256": hashlib.sha256(provenance.read_bytes()).hexdigest(),
                    "audit_path": str(audit),
                    "audit_sha256": hashlib.sha256(audit.read_bytes()).hexdigest(),
                }

            def fake_recovered(record, role):
                if role != "post_vs_native" or not reaudited.is_file():
                    return {"status": "FAIL"}
                return {
                    "status": "PASS",
                    "path": str(reaudited),
                    "sha256": hashlib.sha256(reaudited.read_bytes()).hexdigest(),
                }

            with (
                patch.object(queue_module, "_legacy_pre_provenance_certificate", side_effect=fake_legacy),
                patch.object(queue_module, "_recovered_launcher_certificate", side_effect=fake_recovered),
            ):
                status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "INCOMPLETE")
        self.assertIn("post_vs_pre_direct", status["detail"])
        contract = status["legacy_preflight_contract"]
        self.assertIsNotNone(contract)
        self.assertEqual(contract["required_ci_precision_failed_roles"], ["post_vs_native"])
        self.assertTrue(contract["inconclusive_only"])
        self.assertFalse(contract["normal_launcher_evidence"])

    def test_legacy_verifier_rejects_noncanonical_certificate_and_audit_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_id = "exact-run"
            result_name = "exact-result.json"
            run_dir = root / "models" / "alpha_holdem_v5_from_zero" / run_id
            run_dir.mkdir(parents=True)
            result_path = run_dir / result_name
            result_path.write_text("{}", encoding="utf-8")
            expected_certificate = Path(str(result_path)[:-5] + ".legacy_provenance.json")
            expected_audit = Path(str(result_path)[:-5] + ".legacy_provenance_audit.json")
            wrong_audit = run_dir / "copied-audit.json"
            wrong_audit.write_text("{}", encoding="utf-8")
            expected_certificate.write_text(
                json.dumps(
                    {
                        "canonical_companion_path": str(run_dir / "copied-cert.json"),
                        "post_hoc_read_only_audit": {"path": str(wrong_audit)},
                    }
                ),
                encoding="utf-8",
            )
            with (
                patch.object(queue_module, "REPO_ROOT", root),
                patch.object(queue_module, "EXP003_LEGACY_PRE_RUN_ID", run_id),
                patch.object(queue_module, "EXP003_LEGACY_PRE_RESULT_NAME", result_name),
            ):
                bad_certificate = queue_module._legacy_pre_provenance_certificate(
                    {"path": str(result_path)}, "pre_vs_native"
                )
                expected_certificate.write_text(
                    json.dumps(
                        {
                            "canonical_companion_path": str(expected_certificate),
                            "post_hoc_read_only_audit": {"path": str(wrong_audit)},
                        }
                    ),
                    encoding="utf-8",
                )
                bad_audit = queue_module._legacy_pre_provenance_certificate(
                    {"path": str(result_path)}, "pre_vs_native"
                )

        self.assertEqual(bad_certificate["status"], "FAIL")
        self.assertIn("canonical companion path", bad_certificate["reason"])
        self.assertEqual(bad_audit["status"], "FAIL")
        self.assertIn("audit path", bad_audit["reason"])

    def test_legacy_ops_evidence_binds_raw_row_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ledger = root / "reports" / "v5_experiment_ledger.md"
            ledger.parent.mkdir(parents=True)
            row = b"| 2026-07-09 | [event_id=exact_event] | raw bytes \xff |"
            ledger.write_bytes(b"header\n" + row + b"\n")
            expected = hashlib.sha256(row).hexdigest()
            with (
                patch.object(queue_module, "REPO_ROOT", root),
                patch.object(queue_module, "EXP003_LEGACY_PRE_OPS_ROWS", {"exact_event": expected}),
            ):
                evidence = queue_module._legacy_pre_ops_evidence()
                ledger.write_bytes(b"header\n" + row + b" changed\n")
                with self.assertRaisesRegex(RuntimeError, "row hash mismatch"):
                    queue_module._legacy_pre_ops_evidence()

        self.assertEqual(evidence["exact_event"]["row_sha256"], expected)

    def test_ci_precision_only_failure_requires_explicit_inconclusive_judgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            for name, candidate_hands, anchor_hands in (
                ("pre_native", EXP003_CUTOVER_HANDS, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_native", post_hands, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_direct", post_hands, EXP003_CUTOVER_HANDS),
            ):
                write_exp003_mirror(
                    run_dir,
                    name,
                    candidate_hands=candidate_hands,
                    anchor_hands=anchor_hands,
                    candidate_bb100=0.0,
                    candidate_ci95_bb100=21.0,
                    ci_ok=False,
                )

            before = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
            self.assertEqual(before["status"], EXP003_CI_PRECISION_FAILED)
            self.assertEqual(
                before["ci_precision_failed_roles"],
                ["pre_vs_native", "post_vs_native", "post_vs_pre_direct"],
            )
            self.assertTrue(all(row["judgmentable"] for row in before["roles"].values()))
            self.assertTrue(all(not row["usable"] for row in before["roles"].values()))
            artifact_hashes = {
                role: {
                    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [Path(record["path"]), *(Path(value) for value in record["companion_paths"].values())]
                }
                for role, record in before["roles"].items()
            }
            judgment = {
                "schema_version": "v5.exp003.judgment.v1",
                "checked_at": "2026-07-10T00:00:00+00:00",
                "measurement_status": EXP003_CI_PRECISION_FAILED,
                "decision": "ADOPT",
                "decision_valid": True,
                "candidate_checkpoint_hands": post_hands,
                "candidate_checkpoint_sha256": POST_SHA256,
                "effects": {
                    "native_axis": {"status": "INCONCLUSIVE"},
                    "direct_causal": {"status": "INCONCLUSIVE"},
                },
                "hard_guards": {"status": "PASS"},
                "method_support": {
                    "value_loss": {"status": "INCONCLUSIVE"},
                    "postflop_raise_plus_allin": {"status": "INCONCLUSIVE"},
                },
                "ci_precision_gate": {
                    "status": "FAIL",
                    "failed_roles": before["ci_precision_failed_roles"],
                },
                "mirror_artifact_sha256": artifact_hashes,
            }
            judgment_path = run_dir / "v5_exp003_judgment.json"
            judgment_path.write_text(json.dumps(judgment), encoding="utf-8")
            self.assertEqual(
                exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)["status"],
                EXP003_CI_PRECISION_FAILED,
            )
            judgment["decision"] = "INCONCLUSIVE"
            judgment_path.write_text(json.dumps(judgment), encoding="utf-8")

            after = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(after["status"], "INCONCLUSIVE_BLOCKED")
        self.assertEqual(after["judgment"]["decision"], "INCONCLUSIVE")

    def test_ci_precision_failure_does_not_bypass_ood_integrity(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
                ood_ok=False,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("post_vs_native", status["detail"])
        self.assertNotEqual(status["status"], EXP003_CI_PRECISION_FAILED)

    def test_inconsistent_ci_gate_is_not_reclassified_as_precision_inconclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            for name, candidate_hands, anchor_hands in (
                ("pre_native", EXP003_CUTOVER_HANDS, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_native", post_hands, EXP003_NATIVE_ANCHOR_HANDS),
                ("post_direct", post_hands, EXP003_CUTOVER_HANDS),
            ):
                # At 25k pairs a <=20 halfwidth must set passes_ci_gate=true;
                # a false declaration is malformed evidence, not a low-precision result.
                write_exp003_mirror(
                    run_dir,
                    name,
                    candidate_hands=candidate_hands,
                    anchor_hands=anchor_hands,
                    candidate_ci95_bb100=10.0,
                    ci_ok=False,
                )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertNotEqual(status["status"], EXP003_CI_PRECISION_FAILED)

    def test_ci_precision_failure_does_not_bypass_declared_model_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            pre_path = write_exp003_mirror(
                run_dir,
                "pre_native",
                candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )
            pre = json.loads(pre_path.read_text(encoding="utf-8"))
            pre["candidate"]["sha256"] = "00" * 32
            pre_path.write_text(json.dumps(pre), encoding="utf-8")
            Path(str(pre_path)[:-5] + ".stdout.log").write_text(json.dumps(pre), encoding="utf-8")
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_ci95_bb100=21.0,
                ci_ok=False,
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "REVIEW")
        self.assertIn("pre-cutover hash mismatch", status["detail"])

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
                candidate_bb100=-20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_native",
                candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS,
                candidate_bb100=20.0,
            )
            write_exp003_mirror(
                run_dir,
                "post_direct",
                candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS,
                candidate_bb100=20.0,
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
                            role: {
                                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in [
                                    Path(record["path"]),
                                    *(Path(value) for value in record["companion_paths"].values()),
                                ]
                            }
                            for role, record in exp003_mirror_bundle_status(
                                run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS
                            )["roles"].items()
                        },
                    }
                ),
                encoding="utf-8",
            )

            status = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(status["status"], "ADOPT_CLOSED")
        self.assertEqual(status["judgment"]["decision"], "ADOPT")

    def test_judgment_does_not_close_after_mirror_artifact_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            post_hands = EXP003_NATIVE_MIRROR_TARGET_HANDS + 1_000_000
            write_exp003_mirror(
                run_dir, "pre_native", candidate_hands=EXP003_CUTOVER_HANDS,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS, candidate_bb100=-20.0,
            )
            write_exp003_mirror(
                run_dir, "post_native", candidate_hands=post_hands,
                anchor_hands=EXP003_NATIVE_ANCHOR_HANDS, candidate_bb100=20.0,
            )
            write_exp003_mirror(
                run_dir, "post_direct", candidate_hands=post_hands,
                anchor_hands=EXP003_CUTOVER_HANDS, candidate_bb100=20.0,
            )
            before = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)
            artifact_hashes = {
                role: {
                    str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                    for path in [Path(record["path"]), *(Path(value) for value in record["companion_paths"].values())]
                }
                for role, record in before["roles"].items()
            }
            judgment = {
                "schema_version": "v5.exp003.judgment.v1",
                "checked_at": "2026-07-09T23:00:00+00:00",
                "measurement_status": "REVIEW_READY",
                "decision": "ADOPT",
                "decision_valid": True,
                "candidate_checkpoint_hands": post_hands,
                "candidate_checkpoint_sha256": POST_SHA256,
                "effects": {"native_axis": {"status": "PASS"}, "direct_causal": {"status": "PASS"}},
                "hard_guards": {"status": "PASS"},
                "method_support": {
                    "value_loss": {"status": "PASS"},
                    "postflop_raise_plus_allin": {"status": "PASS"},
                },
                "mirror_artifact_sha256": artifact_hashes,
            }
            (run_dir / "v5_exp003_judgment.json").write_text(json.dumps(judgment), encoding="utf-8")
            Path(before["roles"]["pre_vs_native"]["companion_paths"]["markdown"]).write_text(
                "mutated after judgment\n", encoding="utf-8"
            )

            after = exp003_mirror_bundle_status(run_dir, EXP003_NATIVE_MIRROR_TARGET_HANDS)

        self.assertEqual(after["status"], "REVIEW_READY")


class ExternalEvalDescriptorTest(unittest.TestCase):
    def test_promotion_is_not_mislabeled_quick5k_or_guarded_policy(self):
        descriptor = external_eval_descriptor("promotion20k", 500_000_000)

        self.assertEqual(descriptor["key"], "slumbot_promotion20k_500000000")
        self.assertIn("greedy-direct promotion20k", descriptor["noun"])
        self.assertNotIn("guarded", descriptor["action"])


class Exp003MirrorQueueInstructionTest(unittest.TestCase):
    def test_inconclusive_fixed_window_forbids_rerun_and_requires_new_design(self):
        trigger, action = exp003_mirror_queue_instruction("INCONCLUSIVE_BLOCKED")

        self.assertIn("INCONCLUSIVE_BLOCKED", trigger)
        self.assertIn("Do not rerun", action)
        self.assertIn("add pairs", action)
        self.assertIn("substitute another checkpoint", action)
        self.assertIn("Register a new measurement design", action)

    def test_open_window_keeps_registered_mirror_instruction(self):
        trigger, action = exp003_mirror_queue_instruction("INCOMPLETE")

        self.assertIn("checkpoint hands >=", trigger)
        self.assertIn("run the registered", action)
        self.assertNotIn("Do not rerun", action)

    def test_build_queue_exposes_inconclusive_no_rerun_instruction(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run_dir = root / "v5_exp003_test"
            output_dir = root / "output"
            run_dir.mkdir()
            output_dir.mkdir()
            dashboard = {
                "training": {"latest": {"iteration": 24_900}, "current_hands": 409_058_520},
                "checkpoint": {
                    "iteration": 24_900,
                    "total_hands": 409_058_520,
                    "run_id": "v5_exp003_test",
                },
                "health": {"overall": "PASS"},
                "gates": {},
            }
            with (
                patch.object(queue_module, "build_summary", return_value=dashboard),
                patch.object(
                    queue_module,
                    "exp003_mirror_bundle_status",
                    return_value={"status": "INCONCLUSIVE_BLOCKED", "detail": "fixed window closed"},
                ),
            ):
                summary = build_queue(run_dir, output_dir)

        entry = next(item for item in summary["queue"] if item["key"] == "exp003_native_anchor_mirror_408064575")
        self.assertEqual(entry["status"], "BLOCKED")
        self.assertIn("INCONCLUSIVE_BLOCKED", entry["trigger"])
        self.assertIn("Do not rerun", entry["action"])
        self.assertIn("Register a new measurement design", entry["action"])


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
