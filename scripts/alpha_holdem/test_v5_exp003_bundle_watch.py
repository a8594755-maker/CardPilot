#!/usr/bin/env python3
"""Focused safety tests for the EXP-003 fixed-bundle watcher."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

import v5_exp003_bundle_watch as bundle_watch

from v5_exp003_bundle_watch import (
    DEVICE,
    EXP003_EVALUATOR_SHA256,
    EXP003_MIRROR_OOD_MAX,
    EXP003_MIRROR_PAIRS,
    EXP003_MIRROR_POLICY_MODE,
    EXP003_MIRROR_SEED,
    EXP003_NATIVE_SHA256,
    EXP003_PRE_SHA256,
    PRIORITY,
    STARTING_STACK,
    SingleInstanceLock,
    StageSpec,
    _build_publish_manifest,
    _audit_staged,
    _atomic_copy_verified,
    _command,
    _launcher_payload,
    _publish_from_manifest,
    _stage_specs,
    _staging_spec,
    atomic_write_json,
    active_eval_processes,
    eval_contention,
    preflight,
    recover_staging,
    launch_stage,
    run_once,
    scan_published_role_artifacts,
    sha256_file,
)


FREEZE = {
    "gate_iteration": 24900,
    "gate_hands": 409_000_000,
    "gate_path": "gate_24900_status.json",
    "archive_path": "post.pt",
    "archive_sha256": "post-sha",
    "archive_actual_sha256": "post-sha",
    "run_id": "run",
}


def structural_role(spec: StageSpec, *, usable: bool) -> dict:
    return {
        "path": str(spec.result_path),
        "usable": usable,
        "execution_ok": True,
        "companions_ok": True,
        "stderr_empty": True,
        "pairs": EXP003_MIRROR_PAIRS,
        "seed": EXP003_MIRROR_SEED,
        "policy_mode": EXP003_MIRROR_POLICY_MODE,
        "starting_stack": STARTING_STACK,
        "device": DEVICE,
        "ood_threshold": EXP003_MIRROR_OOD_MAX,
        "candidate_hands": FREEZE["gate_hands"],
        "anchor_hands": 75_479_020 if spec.role == "post_vs_native" else 358_064_575,
        "candidate_sha256": spec.candidate_sha256,
        "anchor_sha256": spec.anchor_sha256,
        "candidate_path": str(spec.candidate_path),
        "anchor_path": str(spec.anchor_path),
        "candidate_bb100": 1.0,
        "candidate_ci95_bb100": 10.0,
        "ood_rate": 0.01,
        "ci_ok": usable,
        "ood_ok": True,
    }


class LockIdentityTest(unittest.TestCase):
    def test_partial_lock_creation_race_fails_closed_without_deletion(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "watch.lock"
            lock_path.write_text("", encoding="utf-8")
            lock = SingleInstanceLock(lock_path, identity_lookup=lambda pid: None)
            with self.assertRaisesRegex(RuntimeError, "partial/unreadable"):
                lock.acquire()
            self.assertTrue(lock_path.exists())
            self.assertEqual(lock_path.read_text(encoding="utf-8"), "")

    def test_release_does_not_unlink_another_owner_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "watch.lock"
            identity = {"pid": 321, "creation_date": "created", "command_line": "watcher"}
            lock = SingleInstanceLock(lock_path, identity_lookup=lambda pid: identity)
            with patch("v5_exp003_bundle_watch.os.getpid", return_value=321):
                lock.acquire()
            replacement = json.loads(lock_path.read_text(encoding="utf-8"))
            replacement["owner_token"] = "replacement-owner"
            atomic_write_json(lock_path, replacement)
            lock.release()
            self.assertTrue(lock_path.exists())
            self.assertEqual(
                json.loads(lock_path.read_text(encoding="utf-8"))["owner_token"],
                "replacement-owner",
            )

    def test_exact_live_pid_creation_and_command_blocks_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "watch.lock"
            identity = {"pid": 123, "creation_date": "created", "command_line": "python watcher"}
            atomic_write_json(lock_path, {**identity, "owner_token": "owner"})
            lock = SingleInstanceLock(lock_path, identity_lookup=lambda pid: dict(identity))
            with self.assertRaisesRegex(RuntimeError, "exact live process"):
                lock.acquire()
            self.assertTrue(lock_path.exists())

    def test_pid_reuse_with_different_creation_is_stale(self):
        with tempfile.TemporaryDirectory() as tmp:
            lock_path = Path(tmp) / "watch.lock"
            atomic_write_json(
                lock_path,
                {
                    "pid": 123,
                    "owner_token": "old-owner",
                    "creation_date": "old",
                    "command_line": "python watcher",
                },
            )
            current = {"pid": 123, "creation_date": "new", "command_line": "python other"}
            lock = SingleInstanceLock(lock_path, identity_lookup=lambda pid: dict(current))
            with patch("v5_exp003_bundle_watch.os.getpid", return_value=123):
                lock.acquire()
            persisted = json.loads(lock_path.read_text(encoding="utf-8"))
            self.assertEqual(persisted["creation_date"], "new")
            lock.release()


class FixedProtocolTest(unittest.TestCase):
    def test_hashes_are_computed_and_compared_before_popen(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            candidate = run_dir / "post.pt"
            anchor = run_dir / "native.pt"
            candidate.write_bytes(b"post")
            anchor.write_bytes(b"native")
            spec = StageSpec(
                role="post_vs_native",
                stem=run_dir / "v5_mirror_eval_exp003_post_vs_native_gate24900_25kp",
                candidate_label="post",
                candidate_path=candidate,
                candidate_sha256="candidate-sha",
                anchor_label="native",
                anchor_path=anchor,
                anchor_sha256="anchor-sha",
            )
            expected = {
                "evaluator": EXP003_EVALUATOR_SHA256,
                "candidate": "candidate-sha",
                "anchor": "anchor-sha",
            }
            events: list[str] = []

            class FakeProcess:
                pid = 4321
                returncode = 0

                def poll(self):
                    return 0

                def wait(self, timeout=None):
                    return 0

                def terminate(self):
                    pass

                def kill(self):
                    pass

            def hashes(_spec):
                events.append("hash")
                return dict(expected)

            def popen(*args, **kwargs):
                events.append("popen")
                self.assertEqual(events[0], "hash")
                return FakeProcess()

            with (
                patch("v5_exp003_bundle_watch._input_hashes", side_effect=hashes),
                patch("v5_exp003_bundle_watch.subprocess.Popen", side_effect=popen),
                patch(
                    "v5_exp003_bundle_watch._wait_process_identity",
                    return_value={
                        "pid": 4321,
                        "creation_date": "created",
                        "command_line": "python mirror",
                    },
                ),
            ):
                result = launch_stage(spec, "python", contention_scan=lambda excluded: {"busy": False})
            self.assertEqual(result["status"], "STAGED_COMPLETED")
            self.assertEqual(events[:2], ["hash", "popen"])

    def test_command_is_exact_fixed_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            spec = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})[0]
            command = _command(spec, "python")
            pairs = command[command.index("--pairs") + 1]
            seed = command[command.index("--seed") + 1]
            stack = command[command.index("--starting-stack") + 1]
            self.assertEqual((pairs, seed, stack), ("25000", "20260709", "200"))
            self.assertEqual(command[command.index("--device") + 1], "cpu")
            self.assertEqual(command[command.index("--priority") + 1], "below-normal")
            self.assertEqual(command[command.index("--torch-threads") + 1], "1")
            self.assertEqual(command[command.index("--torch-interop-threads") + 1], "1")
            self.assertEqual(command[command.index("--anchor-ood-valid-threshold") + 1], "0.15")

    def test_launcher_records_pid_creation_full_command_hashes_and_protocol(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            canonical = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})[0]
            staged = _staging_spec(run_dir, canonical)
            command = _command(staged, "python")
            payload = _launcher_payload(
                staged,
                canonical,
                456,
                command,
                {"creation_date": "created", "command_line": "full cmd"},
                {
                    "evaluator": EXP003_EVALUATOR_SHA256,
                    "candidate": canonical.candidate_sha256,
                    "anchor": canonical.anchor_sha256,
                },
                "before-popen",
            )
            self.assertEqual(payload["pid"], 456)
            self.assertEqual(payload["process_creation_date"], "created")
            self.assertEqual(payload["process_command_line"], "full cmd")
            self.assertEqual(payload["attempt"], 1)
            self.assertEqual(payload["prelaunch_hashed_at"], "before-popen")
            self.assertEqual(payload["protocol"]["pairs"], 25_000)
            self.assertEqual(payload["protocol"]["policy_mode"], EXP003_MIRROR_POLICY_MODE)
            self.assertEqual(payload["model_sha256"]["candidate"], canonical.candidate_sha256)


class FreezeFailClosedTest(unittest.TestCase):
    def test_freeze_fail_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            atomic_write_json(
                run_dir / "exp003_judgment_freeze_status.json",
                {"overall": "FAIL", "state": "MISSED_FIRST_ELIGIBLE_PASS", "reason": "missed"},
            )
            result = preflight(run_dir)
            self.assertEqual(result["overall"], "FAIL")
            self.assertEqual(result["state"], "FREEZE_TERMINAL_FAIL")
            self.assertTrue(result["terminal"])

    def test_pass_with_wrong_freeze_state_is_terminal(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            atomic_write_json(
                run_dir / "exp003_judgment_freeze_status.json",
                {"overall": "PASS", "state": "OTHER"},
            )
            result = preflight(run_dir)
            self.assertEqual(result["state"], "FREEZE_STATE_INVALID")
            self.assertTrue(result["terminal"])


class AtomicPublishTest(unittest.TestCase):
    def _make_specs(self, run_dir: Path) -> tuple[StageSpec, StageSpec]:
        canonical = StageSpec(
            role="post_vs_native",
            stem=run_dir / "v5_mirror_eval_exp003_post_vs_native_gate24900_25kp",
            candidate_label="post",
            candidate_path=run_dir / "post.pt",
            candidate_sha256="post",
            anchor_label="native",
            anchor_path=run_dir / "native.pt",
            anchor_sha256="native",
        )
        return canonical, _staging_spec(run_dir, canonical)

    def test_main_json_is_published_last_and_crash_recovery_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical, staged = self._make_specs(run_dir)
            staged.stem.parent.mkdir(parents=True)
            for index, path in enumerate(staged.artifacts()):
                path.write_text(f"artifact-{index}", encoding="utf-8")
            manifest = _build_publish_manifest(canonical, staged, {"measurement_usable": True})
            manifest_path = staged.stem.parent / "publish_manifest.json"
            atomic_write_json(manifest_path, manifest)

            # Simulate a crash after one companion was published.
            first = manifest["artifacts"]["markdown"]
            Path(first["canonical"]).write_bytes(Path(first["staged"]).read_bytes())
            order: list[Path] = []
            import v5_exp003_bundle_watch as module

            original = module._atomic_copy_verified

            def tracked(source: Path, destination: Path, expected: str) -> str:
                if destination != canonical.result_path:
                    self.assertFalse(canonical.result_path.exists())
                else:
                    self.assertTrue(all(path.exists() for path in canonical.artifacts()[1:]))
                order.append(destination)
                return original(source, destination, expected)

            with patch("v5_exp003_bundle_watch._atomic_copy_verified", side_effect=tracked):
                result = _publish_from_manifest(manifest_path)
            self.assertEqual(result["status"], "PUBLISHED")
            self.assertEqual(order[-1], canonical.result_path)
            self.assertTrue(all(path.exists() for path in canonical.artifacts()))
            second = _publish_from_manifest(manifest_path)
            self.assertEqual(second["status"], "PUBLISHED")

    def test_destination_race_never_clobbers_different_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / "source"
            destination = root / "destination"
            source.write_bytes(b"expected")
            expected = sha256_file(source)

            def racing_link(temp: Path, target: Path) -> None:
                Path(target).write_bytes(b"racer")
                raise FileExistsError

            with patch("v5_exp003_bundle_watch.os.link", side_effect=racing_link):
                with self.assertRaisesRegex(RuntimeError, "different SHA256"):
                    _atomic_copy_verified(source, destination, expected)
            self.assertEqual(destination.read_bytes(), b"racer")

    def test_exact_orphan_child_blocks_duplicate_attempt(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            canonical, staged = self._make_specs(run_dir)
            staged.stem.parent.mkdir(parents=True)
            atomic_write_json(
                staged.launcher_path,
                {
                    "state": "RUNNING",
                    "pid": 777,
                    "process_creation_date": "created",
                    "process_command_line": "python mirror",
                },
            )
            with patch(
                "v5_exp003_bundle_watch.process_identity",
                return_value={
                    "pid": 777,
                    "creation_date": "created",
                    "command_line": "python mirror",
                },
            ):
                result = recover_staging(canonical)
            self.assertEqual(result["status"], "ORPHAN_RUNNING")
            self.assertFalse(canonical.result_path.exists())

    def test_completed_recovery_with_contention_is_quarantined(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            canonical, staged = self._make_specs(run_dir)
            staged.stem.parent.mkdir(parents=True)
            atomic_write_json(
                staged.launcher_path,
                {
                    "state": "COMPLETED",
                    "return_code": 0,
                    "contention_detected": True,
                    "contention_snapshots": [{"state": "RUNNING"}],
                    "contention_monitor_errors": [],
                },
            )
            result = recover_staging(canonical)
            self.assertEqual(result["status"], "QUARANTINED")
            self.assertTrue((staged.stem.parent / "quarantine.json").exists())
            self.assertFalse(canonical.result_path.exists())

    def test_midrun_model_hash_mutation_fails_staged_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            canonical, staged = self._make_specs(run_dir)
            staged.stem.parent.mkdir(parents=True)
            for path in staged.artifacts():
                path.write_text("{}", encoding="utf-8")
            expected = {
                "evaluator": EXP003_EVALUATOR_SHA256,
                "candidate": canonical.candidate_sha256,
                "anchor": canonical.anchor_sha256,
            }
            atomic_write_json(
                staged.launcher_path,
                {
                    "state": "COMPLETED",
                    "return_code": 0,
                    "input_sha256_pre": expected,
                    "input_sha256_post": {**expected, "candidate": "mutated"},
                },
            )
            record = {
                "execution_ok": True,
                "companions_ok": True,
                "stderr_empty": True,
                "pairs": EXP003_MIRROR_PAIRS,
                "seed": EXP003_MIRROR_SEED,
                "policy_mode": EXP003_MIRROR_POLICY_MODE,
                "starting_stack": STARTING_STACK,
                "device": DEVICE,
                "ood_threshold": EXP003_MIRROR_OOD_MAX,
                "candidate_sha256": canonical.candidate_sha256,
                "candidate_path": str(canonical.candidate_path),
                "anchor_sha256": canonical.anchor_sha256,
                "anchor_path": str(canonical.anchor_path),
                "candidate_bb100": 0.0,
                "candidate_ci95_bb100": 10.0,
                "ood_rate": 0.0,
                "usable": True,
                "ci_ok": True,
                "ood_ok": True,
            }
            with (
                patch("v5_exp003_bundle_watch._exp003_mirror_record", return_value=record),
                patch("v5_exp003_bundle_watch._input_hashes", return_value=expected),
            ):
                audit = _audit_staged(canonical, staged)
            self.assertEqual(audit["status"], "FAIL")
            self.assertFalse(audit["structural_checks"]["launcher_complete"])

    def test_staged_audit_requires_exact_launcher_execution_identity_and_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            canonical, staged = self._make_specs(run_dir)
            canonical.candidate_path.write_bytes(b"post")
            canonical.anchor_path.write_bytes(b"native")
            staged.stem.parent.mkdir(parents=True)
            command = _command(staged, sys.executable)
            expected = {
                "evaluator": EXP003_EVALUATOR_SHA256,
                "candidate": canonical.candidate_sha256,
                "anchor": canonical.anchor_sha256,
            }
            launcher = _launcher_payload(
                staged,
                canonical,
                555,
                command,
                {
                    "creation_date": "created",
                    "command_line": __import__("subprocess").list2cmdline(command),
                },
                expected,
                "before-popen",
            )
            launcher.update(
                {
                    "state": "COMPLETED",
                    "return_code": 0,
                    "input_sha256_post": expected,
                    "contention_detected": False,
                    "contention_snapshots": [],
                    "contention_monitor_errors": [],
                }
            )
            execution = {
                "pid": 555,
                "command": command,
                "working_directory": str(Path(__file__).resolve().parents[2]),
            }
            for path in staged.artifacts():
                path.write_text("{}", encoding="utf-8")
            atomic_write_json(staged.launcher_path, launcher)
            atomic_write_json(staged.execution_path, execution)
            record = {
                "execution_ok": True,
                "companions_ok": True,
                "stderr_empty": True,
                "pairs": EXP003_MIRROR_PAIRS,
                "seed": EXP003_MIRROR_SEED,
                "policy_mode": EXP003_MIRROR_POLICY_MODE,
                "starting_stack": STARTING_STACK,
                "device": DEVICE,
                "ood_threshold": EXP003_MIRROR_OOD_MAX,
                "candidate_sha256": canonical.candidate_sha256,
                "candidate_path": str(canonical.candidate_path),
                "anchor_sha256": canonical.anchor_sha256,
                "anchor_path": str(canonical.anchor_path),
                "candidate_bb100": 0.0,
                "candidate_ci95_bb100": 10.0,
                "ood_rate": 0.0,
                "usable": True,
                "ci_ok": True,
                "ood_ok": True,
            }
            with (
                patch("v5_exp003_bundle_watch._exp003_mirror_record", return_value=record),
                patch("v5_exp003_bundle_watch._input_hashes", return_value=expected),
            ):
                audit = _audit_staged(canonical, staged)
            self.assertEqual(audit["status"], "PASS", audit)
            self.assertTrue(audit["structural_checks"]["launcher_command"])
            self.assertTrue(audit["structural_checks"]["launcher_paths"])


class EvalMutualExclusionTest(unittest.TestCase):
    def test_slumbot_running_status_blocks_even_without_visible_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp)
            atomic_write_json(
                run_dir / "slumbot_promotion20k_launch_status.json",
                {"state": "RUNNING", "pid": 999},
            )
            with patch("v5_exp003_bundle_watch.active_eval_processes", return_value=[]):
                contention = eval_contention(run_dir)
            self.assertTrue(contention["busy"])
            self.assertEqual(contention["slumbot_running_statuses"][0]["pid"], 999)

    def test_all_launch_and_cadence_transitional_states_block(self):
        for index, state in enumerate(
            (
                "RUNNING",
                "FREEZING",
                "PREFLIGHT",
                "SELECTOR_REPLAY",
                "READY",
                "READY_WITH_WARNINGS",
                "FREEZE_RETRY",
            )
        ):
            with self.subTest(state=state), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp)
                name = (
                    "slumbot_cadence_promotion20k_500M_status.json"
                    if index % 2
                    else "slumbot_promotion20k_launch_status.json"
                )
                atomic_write_json(run_dir / name, {"state": state})
                with patch("v5_exp003_bundle_watch.active_eval_processes", return_value=[]):
                    self.assertTrue(eval_contention(run_dir)["busy"])

    def test_all_eval_process_families_block(self):
        invocations = (
            ("python.exe -u C:/repo/scripts/alpha_holdem/play_slumbot.py", "play_slumbot.py"),
            (
                "python.exe C:/repo/scripts/alpha_holdem/v5_slumbot_selector_replay.py",
                "v5_slumbot_selector_replay.py",
            ),
            (
                "python.exe C:/repo/scripts/alpha_holdem/v5_slumbot_pipeline_preflight.py",
                "v5_slumbot_pipeline_preflight.py",
            ),
            (
                "python.exe C:/repo/scripts/alpha_holdem/slumbot_pipeline_preflight.py",
                "slumbot_pipeline_preflight.py",
            ),
            ("python.exe C:/repo/scripts/alpha_holdem/v5_mirror_eval.py", "v5_mirror_eval.py"),
            (
                "powershell.exe -NoProfile -File C:/repo/scripts/alpha_holdem/bench_v55_slumbot.ps1",
                "bench_v55_slumbot.ps1",
            ),
        )
        for index, (command_line, token) in enumerate(invocations, start=100):
            with self.subTest(command_line=command_line):
                with patch(
                    "v5_exp003_bundle_watch.process_rows",
                    return_value=[
                        {
                            "ProcessId": index,
                            "Name": "python.exe",
                            "CreationDate": "created",
                            "CommandLine": command_line,
                        }
                    ],
                ):
                    rows = active_eval_processes()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["matched_tokens"], [token])

    def test_command_text_inspectors_and_python_code_do_not_block(self):
        rows = [
            {
                "ProcessId": 201,
                "Name": "powershell.exe",
                "CreationDate": "created",
                "CommandLine": (
                    'powershell.exe -NoProfile -Command "Get-CimInstance Win32_Process | '
                    "Where-Object {$_.CommandLine -match 'play_slumbot|v5_mirror_eval.py|"
                    "bench_v55_slumbot.ps1'}\""
                ),
            },
            {
                "ProcessId": 202,
                "Name": "python.exe",
                "CreationDate": "created",
                "CommandLine": 'python.exe -c "print(\'play_slumbot.py v5_mirror_eval.py\')"',
            },
            {
                "ProcessId": 203,
                "Name": "cmd.exe",
                "CreationDate": "created",
                "CommandLine": (
                    'cmd.exe /c "python.exe C:/repo/scripts/alpha_holdem/v5_mirror_eval.py"'
                ),
            },
        ]
        with patch("v5_exp003_bundle_watch.process_rows", return_value=rows):
            self.assertEqual(active_eval_processes(), [])

    def test_process_command_parse_error_blocks(self):
        with (
            patch(
                "v5_exp003_bundle_watch.process_rows",
                return_value=[
                    {
                        "ProcessId": 301,
                        "Name": "python.exe",
                        "CreationDate": "created",
                        "CommandLine": "malformed command line",
                    }
                ],
            ),
            patch(
                "v5_exp003_bundle_watch._parse_process_command_line",
                side_effect=ValueError("unparseable argv"),
            ),
        ):
            rows = active_eval_processes()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["matched_tokens"], ["command_line_parse_error"])
        self.assertIn("unparseable argv", rows[0]["parse_error"])


class SequentialBundleTest(unittest.TestCase):
    def _ready_preflight(self, run_dir: Path, roles: dict) -> dict:
        return {
            "schema_version": "test",
            "checked_at": "now",
            "run_dir": str(run_dir),
            "overall": "PASS",
            "state": "READY_TO_LAUNCH",
            "reason": "ready",
            "terminal": False,
            "freeze": dict(FREEZE),
            "bundle": {"status": "INCOMPLETE", "roles": roles},
        }

    def test_failed_role2_measurement_still_runs_role3_without_more_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            specs = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})
            roles: dict = {"pre_vs_native": {"usable": True}}
            launched: list[str] = []

            def fake_preflight(*args, **kwargs):
                return self._ready_preflight(run_dir, roles)

            def fake_launcher(spec, python, on_started, **kwargs):
                launched.append(spec.role)
                on_started(
                    {
                        "pid": 100 + len(launched),
                        "process_creation_date": f"c{len(launched)}",
                        "process_command_line": f"cmd{len(launched)}",
                    }
                )
                roles[spec.role] = structural_role(spec, usable=(spec.role != "post_vs_native"))
                return {
                    "status": "STAGED_COMPLETED",
                    "staged_spec": _staging_spec(run_dir, spec),
                    "launcher": {"contention_detected": False},
                }

            def validator(*args):
                status = "REVIEW" if len(launched) == 2 else "INCOMPLETE"
                return {"status": status, "roles": dict(roles)}

            with (
                patch("v5_exp003_bundle_watch.preflight", side_effect=fake_preflight),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
                patch("v5_exp003_bundle_watch.finalize_staged", return_value={"status": "PUBLISHED"}),
                patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
            ):
                result = run_once(
                    run_dir,
                    validator=validator,
                    process_scan=lambda: [],
                    launcher=fake_launcher,
                )
            self.assertEqual(launched, ["post_vs_native", "post_vs_pre_direct"])
            self.assertEqual(result["overall"], "FAIL")
            self.assertEqual(result["state"], "FINAL_BUNDLE_NOT_REVIEW_READY")
            self.assertEqual([row["role"] for row in result["measurement_failures"]], ["post_vs_native"])
            self.assertTrue(all("25000" in _command(spec, "python") for spec in specs))

    def test_duplicate_partial_canonical_artifact_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            spec = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})[0]
            spec.stderr_path.write_text("failed once", encoding="utf-8")
            roles = {"pre_vs_native": {"usable": True}}

            with (
                patch(
                    "v5_exp003_bundle_watch.preflight",
                    return_value=self._ready_preflight(run_dir, roles),
                ),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
            ):
                result = run_once(
                    run_dir,
                    validator=lambda *args: {"status": "INCOMPLETE", "roles": roles},
                    process_scan=lambda: [],
                    launcher=lambda *args, **kwargs: self.fail("launcher must not run"),
                )
            self.assertEqual(result["state"], "PUBLISHED_ROLE_ARTIFACT_CONFLICT")
            self.assertEqual(spec.stderr_path.read_text(encoding="utf-8"), "failed once")

    def test_duplicate_structural_role_results_are_a_terminal_selection_conflict(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            spec = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})[0]
            paths = [
                run_dir / "v5_mirror_eval_exp003_post_vs_native_a.json",
                run_dir / "v5_mirror_eval_exp003_post_vs_native_b.json",
            ]
            for path in paths:
                path.write_text("{}", encoding="utf-8")

            def record(path, mirror):
                row = structural_role(spec, usable=True)
                row["path"] = str(path)
                return row

            with patch("v5_exp003_bundle_watch._exp003_mirror_record", side_effect=record):
                scan = scan_published_role_artifacts(run_dir, spec, FREEZE)
            self.assertEqual(scan["status"], "FAIL")
            self.assertIn("duplicate structurally complete", ";".join(scan["problems"]))

    def test_only_review_ready_is_successful_terminal_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            roles: dict = {"pre_vs_native": {"usable": True}}

            def fake_preflight(*args, **kwargs):
                return self._ready_preflight(run_dir, roles)

            def fake_launcher(spec, python, on_started, **kwargs):
                roles[spec.role] = structural_role(spec, usable=True)
                return {
                    "status": "STAGED_COMPLETED",
                    "staged_spec": _staging_spec(run_dir, spec),
                    "launcher": {"contention_detected": False},
                }

            def validator(*args):
                complete = all(key in roles for key in ("post_vs_native", "post_vs_pre_direct"))
                return {"status": "REVIEW_READY" if complete else "INCOMPLETE", "roles": dict(roles)}

            with (
                patch("v5_exp003_bundle_watch.preflight", side_effect=fake_preflight),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
                patch("v5_exp003_bundle_watch.finalize_staged", return_value={"status": "PUBLISHED"}),
                patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
            ):
                result = run_once(
                    run_dir,
                    validator=validator,
                    process_scan=lambda: [],
                    launcher=fake_launcher,
                )
            self.assertEqual(result["overall"], "REVIEW_READY")
            self.assertEqual(result["state"], "REVIEW_READY")
            self.assertTrue(result["terminal"])

    def test_midrun_contention_is_quarantined_without_canonical_publish(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            spec = _stage_specs(run_dir, {**FREEZE, "archive_path": str(run_dir / "post.pt")})[0]
            staged = _staging_spec(run_dir, spec)
            staged.stem.parent.mkdir(parents=True)
            roles = {"pre_vs_native": {"usable": True}}

            def fake_launcher(*args, **kwargs):
                return {
                    "status": "STAGED_COMPLETED",
                    "staged_spec": staged,
                    "launcher": {
                        "contention_detected": True,
                        "contention_snapshots": [{"processes": [{"pid": 99}]}],
                    },
                }

            with (
                patch(
                    "v5_exp003_bundle_watch.preflight",
                    return_value=self._ready_preflight(run_dir, roles),
                ),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
                patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
            ):
                result = run_once(
                    run_dir,
                    validator=lambda *args: {"status": "INCOMPLETE", "roles": roles},
                    process_scan=lambda: [],
                    launcher=fake_launcher,
                )
            self.assertEqual(result["state"], "MEASUREMENT_CONTENTION_QUARANTINED")
            self.assertTrue((staged.stem.parent / "quarantine.json").is_file())
            self.assertFalse(spec.result_path.exists())


class LegacyInconclusiveRole1PreflightTest(unittest.TestCase):
    """The legacy role1 exception is a contract-bound role3 continuation only."""

    def _fixture(self, root: Path) -> tuple[Path, dict, dict, dict]:
        run_dir = root / bundle_watch.EXP003_LEGACY_PRE_RUN_ID
        run_dir.mkdir(parents=True)
        archive = run_dir / "post.pt"
        archive.write_bytes(b"post")
        freeze = {
            **FREEZE,
            "archive_path": str(archive),
            "archive_sha256": "post-sha",
            "archive_actual_sha256": "post-sha",
        }
        specs = _stage_specs(run_dir, freeze)
        post_spec = specs[0]
        role1_path = run_dir / bundle_watch.EXP003_LEGACY_PRE_RESULT_NAME
        provenance_path = Path(str(role1_path)[:-5] + ".legacy_provenance.json")
        audit_path = Path(str(role1_path)[:-5] + ".legacy_provenance_audit.json")
        reaudit_path = post_spec.contention_reaudit_path
        atomic_write_json(
            provenance_path,
            {
                "schema_version": bundle_watch.EXP003_LEGACY_PRE_SCHEMA_VERSION,
                "state": "LEGACY_PROVENANCE_INCONCLUSIVE_ONLY_PASS",
                "role": "pre_vs_native",
                "run_id": bundle_watch.EXP003_LEGACY_PRE_RUN_ID,
                "result_path": str(role1_path),
                "candidate_sha256": EXP003_PRE_SHA256,
                "anchor_sha256": EXP003_NATIVE_SHA256,
                "decision_capability": "INCONCLUSIVE_ONLY",
                "generic_fallback": False,
            },
        )
        atomic_write_json(
            audit_path,
            {
                "schema_version": bundle_watch.EXP003_LEGACY_PRE_AUDIT_SCHEMA_VERSION,
                "overall": "PASS",
                "role": "pre_vs_native",
                "run_id": bundle_watch.EXP003_LEGACY_PRE_RUN_ID,
            },
        )
        atomic_write_json(
            reaudit_path,
            {
                "schema_version": bundle_watch.CONTENTION_REAUDIT_SCHEMA_VERSION,
                "state": "FALSE_POSITIVE_CONTENTION_REAUDIT_PASS",
                "role": "post_vs_native",
                "recovery_eligible": True,
                "forensic_verdict": "PASS",
            },
        )
        provenance_sha = sha256_file(provenance_path)
        audit_sha = sha256_file(audit_path)
        reaudit_sha = sha256_file(reaudit_path)
        role1 = {
            "path": str(role1_path),
            "candidate_iteration": bundle_watch.EXP003_CUTOVER_ITERATION,
            "candidate_hands": bundle_watch.EXP003_CUTOVER_HANDS,
            "anchor_iteration": 4600,
            "anchor_hands": bundle_watch.EXP003_NATIVE_ANCHOR_HANDS,
            "candidate_sha256": EXP003_PRE_SHA256,
            "anchor_sha256": EXP003_NATIVE_SHA256,
            "candidate_path": str(bundle_watch.PRE_CHECKPOINT_PATH),
            "anchor_path": str(bundle_watch.NATIVE_CHECKPOINT_PATH),
            "legacy_inconclusive_only": True,
            "base_judgmentable": True,
            "launcher_evidence_ok": False,
            "judgmentable": False,
            "usable": False,
            "legacy_provenance": {
                "status": "PASS",
                "path": str(provenance_path),
                "sha256": provenance_sha,
                "audit_path": str(audit_path),
                "audit_sha256": audit_sha,
            },
            "companion_paths": {
                "legacy_provenance": str(provenance_path),
                "legacy_provenance_audit": str(audit_path),
            },
        }
        post = structural_role(post_spec, usable=False)
        post.update(
            {
                "candidate_iteration": freeze["gate_iteration"],
                "base_judgmentable": True,
                "launcher_evidence_ok": True,
                "judgmentable": True,
                "usable": False,
                "ci_precision_failed": True,
                "ci_ok": False,
                "legacy_inconclusive_only": False,
                "companion_paths": {"contention_reaudit": str(reaudit_path)},
            }
        )
        contract = {
            "schema_version": bundle_watch.LEGACY_PREFLIGHT_CONTRACT_SCHEMA_VERSION,
            "role": "pre_vs_native",
            "run_id": bundle_watch.EXP003_LEGACY_PRE_RUN_ID,
            "result_path": str(role1_path),
            "candidate_iteration": bundle_watch.EXP003_CUTOVER_ITERATION,
            "candidate_hands": bundle_watch.EXP003_CUTOVER_HANDS,
            "candidate_sha256": EXP003_PRE_SHA256,
            "anchor_iteration": 4600,
            "anchor_hands": bundle_watch.EXP003_NATIVE_ANCHOR_HANDS,
            "anchor_sha256": EXP003_NATIVE_SHA256,
            "provenance_path": str(provenance_path),
            "provenance_sha256": provenance_sha,
            "audit_path": str(audit_path),
            "audit_sha256": audit_sha,
            "post_vs_native_result_path": str(post_spec.result_path),
            "post_vs_native_candidate_iteration": freeze["gate_iteration"],
            "post_vs_native_candidate_hands": freeze["gate_hands"],
            "post_vs_native_candidate_sha256": post_spec.candidate_sha256,
            "post_vs_native_contention_reaudit_path": str(reaudit_path),
            "post_vs_native_contention_reaudit_sha256": reaudit_sha,
            "required_ci_precision_failed_roles": ["post_vs_native"],
            "inconclusive_only": True,
            "requires_post_vs_native_ci_failure": True,
            "forbids_review_ready": True,
            "forbids_additional_pairs": True,
            "normal_launcher_evidence": False,
        }
        bundle = {
            "status": "INCOMPLETE",
            "roles": {"pre_vs_native": role1, "post_vs_native": post, "post_vs_pre_direct": None},
            "legacy_inconclusive_roles": ["pre_vs_native"],
            "ci_precision_failed_roles": ["post_vs_native"],
            "candidate_checkpoint_hands": freeze["gate_hands"],
            "legacy_preflight_contract": contract,
        }
        atomic_write_json(
            run_dir / "exp003_judgment_freeze_status.json",
            {"overall": "PASS", "state": "FROZEN_FIRST_ELIGIBLE_PASS"},
        )
        atomic_write_json(run_dir / "health_status.json", {"overall": "PASS"})
        (run_dir / "console.err.log").write_text("", encoding="utf-8")
        return run_dir, freeze, bundle, contract

    def _preflight(self, run_dir: Path, freeze: dict, bundle: dict) -> dict:
        with patch("v5_exp003_bundle_watch._validate_freeze", return_value=(freeze, None)):
            return preflight(
                run_dir,
                validator=lambda *args: bundle,
                process_scan=lambda: {"busy": False, "processes": [], "slumbot_running_statuses": []},
            )

    def _run_legacy_role3_continuation(
        self,
        run_dir: Path,
        bundle: dict,
        allowed: dict,
        final_bundle: dict,
    ) -> tuple[list[str], dict]:
        """Exercise the only permitted legacy path through the remaining role."""

        roles = bundle["roles"]
        launched: list[str] = []

        def fake_scan(_run_dir, spec, _freeze):
            return {
                "status": "PASS",
                "selected": roles.get(spec.role),
                "problems": [],
                "partial_groups": [],
                "matching_records": [],
                "structural_records": [],
            }

        def fake_launcher(spec, _python, _on_started, **kwargs):
            launched.append(spec.role)
            roles[spec.role] = structural_role(spec, usable=True)
            return {
                "status": "STAGED_COMPLETED",
                "staged_spec": _staging_spec(run_dir, spec),
                "launcher": {"contention_detected": False},
            }

        def fake_preflight(*args, **kwargs):
            return {**allowed, "bundle": {**bundle, "roles": dict(roles)}}

        with (
            patch("v5_exp003_bundle_watch.preflight", side_effect=fake_preflight),
            patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
            patch("v5_exp003_bundle_watch.scan_published_role_artifacts", side_effect=fake_scan),
            patch("v5_exp003_bundle_watch.finalize_staged", return_value={"status": "PUBLISHED"}),
            patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
        ):
            result = run_once(
                run_dir,
                validator=lambda *args: {**final_bundle, "roles": dict(roles)},
                process_scan=lambda: [],
                launcher=fake_launcher,
            )
        return launched, result

    def test_exact_contract_allows_explicit_role3_only_continuation_and_mutation_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, freeze, bundle, contract = self._fixture(Path(tmp).resolve())
            allowed = self._preflight(run_dir, freeze, bundle)
            self.assertEqual(allowed["overall"], "PASS", allowed)
            self.assertEqual(allowed["state"], "LEGACY_INCONCLUSIVE_ONLY_ROLE3_CONTINUATION")
            self.assertEqual(allowed["role1_continuity_mode"], "LEGACY_INCONCLUSIVE_ONLY_ROLE3_CONTINUATION")
            self.assertTrue(allowed["legacy_role1_allowance"]["contract"]["forbids_review_ready"])
            self.assertTrue(allowed["legacy_role1_allowance"]["contract"]["forbids_additional_pairs"])

            mutated = json.loads(json.dumps(bundle))
            mutated["legacy_preflight_contract"]["post_vs_native_contention_reaudit_sha256"] = "mutated"
            rejected = self._preflight(run_dir, freeze, mutated)
            self.assertEqual(rejected["overall"], "FAIL")
            self.assertEqual(rejected["state"], "ROLE1_NOT_USABLE")
            self.assertIn("legacy_role1_allowance", rejected)

    def test_legacy_mode_runs_only_missing_direct_role_and_ends_ci_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir, freeze, bundle, _contract = self._fixture(Path(tmp).resolve())
            allowed = self._preflight(run_dir, freeze, bundle)
            self.assertEqual(allowed["overall"], "PASS", allowed)
            launched, result = self._run_legacy_role3_continuation(
                run_dir,
                bundle,
                allowed,
                {
                    "status": "CI_PRECISION_FAILED",
                    "measurement_status": "CI_PRECISION_FAILED",
                    "legacy_preflight_contract": bundle["legacy_preflight_contract"],
                    "ci_precision_failed_roles": ["post_vs_native"],
                    "legacy_inconclusive_roles": ["pre_vs_native"],
                },
            )
            self.assertEqual(launched, ["post_vs_pre_direct"])
            self.assertEqual(result["overall"], "INCONCLUSIVE_JUDGMENT_REQUIRED")
            self.assertEqual(result["state"], "CI_PRECISION_FAILED_READY_FOR_EXPLICIT_INCONCLUSIVE_JUDGMENT")

    def test_legacy_mode_rejects_review_ready_or_adopt_final_state(self):
        for forbidden_status in ("REVIEW_READY", "ADOPT"):
            with self.subTest(final_status=forbidden_status), tempfile.TemporaryDirectory() as tmp:
                run_dir, freeze, bundle, _contract = self._fixture(Path(tmp).resolve())
                allowed = self._preflight(run_dir, freeze, bundle)
                self.assertEqual(allowed["overall"], "PASS", allowed)
                launched, result = self._run_legacy_role3_continuation(
                    run_dir,
                    bundle,
                    allowed,
                    {
                        "status": forbidden_status,
                        "measurement_status": forbidden_status,
                        "legacy_preflight_contract": bundle["legacy_preflight_contract"],
                        "ci_precision_failed_roles": ["post_vs_native"],
                        "legacy_inconclusive_roles": ["pre_vs_native"],
                    },
                )
                self.assertEqual(launched, ["post_vs_pre_direct"])
                self.assertEqual(result["overall"], "FAIL")
                self.assertEqual(result["state"], "LEGACY_INCONCLUSIVE_ONLY_FINAL_STATE_VIOLATION")
                self.assertTrue(result["terminal"])


class ForensicFalsePositiveRecoveryTest(unittest.TestCase):
    """Focused tests for the one allowlisted historical contention recovery."""

    def _make_forensic_stage(
        self,
        run_dir: Path,
        *,
        slumbot_status: bool = False,
        monitor_error: bool = False,
    ) -> tuple[StageSpec, StageSpec, dict, Path, dict, dict]:
        candidate = run_dir / "post.pt"
        anchor = run_dir / "native.pt"
        candidate.write_bytes(b"post")
        anchor.write_bytes(b"native")
        spec = StageSpec(
            role="post_vs_native",
            stem=run_dir / "v5_mirror_eval_exp003_post_vs_native_gate24900_25kp",
            candidate_label="post",
            candidate_path=candidate,
            candidate_sha256="post",
            anchor_label="native",
            anchor_path=anchor,
            anchor_sha256="native",
        )
        staged = _staging_spec(run_dir, spec)
        staged.stem.parent.mkdir(parents=True)
        for path in staged.artifacts():
            path.write_text("{}", encoding="utf-8")
        staged.markdown_path.write_text("# result\n", encoding="utf-8")
        staged.stdout_path.write_text("stdout\n", encoding="utf-8")
        staged.stderr_path.write_text("", encoding="utf-8")

        observer_command = 'powershell.exe -Command "Get-Content observer"'
        argv = bundle_watch._parse_process_command_line(observer_command)
        observer_script, observer_error = bundle_watch._powershell_command_argument(argv)
        self.assertIsNone(observer_error)
        self.assertIsNotNone(observer_script)
        snapshot = {
            "busy": True,
            "checked_at": "test-snapshot-time",
            "processes": [
                {
                    "pid": 778,
                    "name": "powershell.exe",
                    "creation_date": "test-created",
                    "command_line": observer_command,
                    "matched_tokens": ["play_slumbot", "v5_mirror_eval.py"],
                }
            ],
            "slumbot_running_statuses": ([{"state": "RUNNING"}] if slumbot_status else []),
        }
        expected_hashes = {
            "evaluator": EXP003_EVALUATOR_SHA256,
            "candidate": spec.candidate_sha256,
            "anchor": spec.anchor_sha256,
        }
        command = _command(staged, sys.executable)
        launcher = _launcher_payload(
            staged,
            spec,
            555,
            command,
            {
                "creation_date": "evaluator-created",
                "command_line": subprocess.list2cmdline(command),
            },
            expected_hashes,
            "before-popen",
        )
        launcher.update(
            {
                "state": "COMPLETED",
                "return_code": 0,
                "input_sha256_post": expected_hashes,
                "contention_detected": True,
                "contention_snapshots": [snapshot],
                "contention_monitor_errors": ([{"error": "monitor"}] if monitor_error else []),
            }
        )
        atomic_write_json(staged.launcher_path, launcher)
        atomic_write_json(
            staged.execution_path,
            {
                "pid": 555,
                "command": command,
                "working_directory": str(Path(__file__).resolve().parents[2]),
            },
        )
        quarantine = {
            "schema_version": "test",
            "state": "QUARANTINED",
            "role": spec.role,
            "published": False,
            "reason": "historical detector false positive",
            "evidence": [snapshot],
        }
        atomic_write_json(staged.stem.parent / "quarantine.json", quarantine)
        terminal_status = {
            "overall": "FAIL",
            "terminal": True,
            "state": "MEASUREMENT_CONTENTION_QUARANTINED",
            "quarantine": quarantine,
            "run_dir": str(run_dir),
        }
        status_path = run_dir / "v5_exp003_bundle_watch_status.json"
        atomic_write_json(status_path, terminal_status)
        allowlist = {
            "command_line_sha256": bundle_watch._sha256_text(observer_command),
            "script_sha256": bundle_watch._sha256_text(str(observer_script)),
            "pid": 778,
            "creation_date": "test-created",
            "checked_at": "test-snapshot-time",
            "snapshot_sha256": bundle_watch._json_fingerprint(snapshot),
            "launcher_sha256": sha256_file(staged.launcher_path),
            "quarantine_sha256": sha256_file(staged.stem.parent / "quarantine.json"),
        }
        record = structural_role(spec, usable=True)
        return spec, staged, terminal_status, status_path, allowlist, record

    def test_exact_historical_reaudit_is_immutable_and_publishes_without_new_pairs(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            spec, staged, terminal_status, status_path, allowlist, record = self._make_forensic_stage(run_dir)
            launcher_before = staged.launcher_path.read_bytes()
            quarantine_path = staged.stem.parent / "quarantine.json"
            quarantine_before = quarantine_path.read_bytes()
            expected_hashes = {
                "evaluator": EXP003_EVALUATOR_SHA256,
                "candidate": spec.candidate_sha256,
                "anchor": spec.anchor_sha256,
            }
            with (
                patch.object(bundle_watch, "CAPTURED_FALSE_POSITIVE_OBSERVER", allowlist),
                patch("v5_exp003_bundle_watch._input_hashes", return_value=expected_hashes),
                patch("v5_exp003_bundle_watch._exp003_mirror_record", return_value=record),
                patch("v5_exp003_bundle_watch._is_recoverable_false_positive_terminal", return_value=True),
            ):
                result = recover_staging(
                    spec,
                    allow_contention_recovery=True,
                    original_terminal_status=terminal_status,
                    original_terminal_status_path=status_path,
                )
            self.assertEqual(result["status"], "PUBLISHED", result)
            self.assertEqual(staged.launcher_path.read_bytes(), launcher_before)
            self.assertEqual(quarantine_path.read_bytes(), quarantine_before)
            self.assertTrue(spec.result_path.is_file())
            self.assertTrue(staged.contention_reaudit_path.is_file())
            self.assertTrue(spec.contention_reaudit_path.is_file())
            self.assertEqual(
                staged.contention_reaudit_path.read_bytes(),
                spec.contention_reaudit_path.read_bytes(),
            )
            certificate = json.loads(spec.contention_reaudit_path.read_text(encoding="utf-8"))
            self.assertEqual(certificate["schema_version"], "v5.exp003.contention_reaudit.v1")
            self.assertEqual(certificate["forensic_verdict"], "PASS")
            self.assertTrue(certificate["all_saved_contention_snapshots_reclassified"])
            self.assertFalse(certificate["raw_audit"]["raw_contention_clean"])
            self.assertTrue(certificate["raw_audit"]["reaudited_contention_exception_used"])
            self.assertEqual(certificate["source"]["terminal_status"]["sha256"], sha256_file(status_path))
            self.assertEqual(certificate["terminal_status_snapshot"], terminal_status)

    def test_any_saved_slumbot_status_or_monitor_error_keeps_stage_quarantined(self):
        for kwargs in ({"slumbot_status": True}, {"monitor_error": True}):
            with self.subTest(kwargs=kwargs), tempfile.TemporaryDirectory() as tmp:
                run_dir = Path(tmp).resolve()
                spec, staged, terminal_status, status_path, allowlist, record = self._make_forensic_stage(
                    run_dir,
                    **kwargs,
                )
                expected_hashes = {
                    "evaluator": EXP003_EVALUATOR_SHA256,
                    "candidate": spec.candidate_sha256,
                    "anchor": spec.anchor_sha256,
                }
                with (
                    patch.object(bundle_watch, "CAPTURED_FALSE_POSITIVE_OBSERVER", allowlist),
                    patch("v5_exp003_bundle_watch._input_hashes", return_value=expected_hashes),
                    patch("v5_exp003_bundle_watch._exp003_mirror_record", return_value=record),
                    patch("v5_exp003_bundle_watch._is_recoverable_false_positive_terminal", return_value=True),
                ):
                    result = recover_staging(
                        spec,
                        allow_contention_recovery=True,
                        original_terminal_status=terminal_status,
                        original_terminal_status_path=status_path,
                    )
                self.assertEqual(result["status"], "QUARANTINED", result)
                self.assertFalse(spec.result_path.exists())
                self.assertFalse(staged.contention_reaudit_path.exists())
                self.assertFalse(spec.contention_reaudit_path.exists())

    def test_terminal_false_positive_resume_reuses_role2_then_launches_only_role3(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            status_path = run_dir / "v5_exp003_bundle_watch_status.json"
            freeze = {**FREEZE, "archive_path": str(run_dir / "post.pt")}
            terminal = {
                "overall": "FAIL",
                "terminal": True,
                "state": "MEASUREMENT_CONTENTION_QUARANTINED",
                "quarantine": {"state": "QUARANTINED", "published": False},
                "freeze": dict(freeze),
            }
            atomic_write_json(status_path, terminal)
            specs = _stage_specs(run_dir, freeze)
            roles: dict = {
                "pre_vs_native": {"usable": True},
                "post_vs_native": structural_role(specs[0], usable=True),
            }
            launched: list[str] = []
            recovery_calls: list[dict] = []

            def fake_preflight(*args, **kwargs):
                return {
                    "overall": "PASS",
                    "state": "READY_TO_LAUNCH",
                    "terminal": False,
                    "freeze": dict(freeze),
                    "bundle": {"status": "INCOMPLETE", "roles": dict(roles)},
                }

            def fake_recovery(spec, **kwargs):
                recovery_calls.append({"role": spec.role, **kwargs})
                if spec.role == "post_vs_native":
                    return {
                        "status": "PUBLISHED",
                        "staged_spec": _staging_spec(run_dir, spec),
                        "contention_reaudit": {
                            "status": "PUBLISHED",
                            "canonical_path": str(spec.contention_reaudit_path),
                            "sha256": "cert",
                        },
                    }
                return {"status": "NONE", "staged_spec": _staging_spec(run_dir, spec)}

            def fake_scan(_run_dir, spec, _freeze):
                return {
                    "status": "PASS",
                    "selected": roles.get(spec.role),
                    "problems": [],
                    "partial_groups": [],
                    "matching_records": [],
                    "structural_records": [],
                }

            def fake_launcher(spec, _python, _on_started, **kwargs):
                launched.append(spec.role)
                roles[spec.role] = structural_role(spec, usable=True)
                return {
                    "status": "STAGED_COMPLETED",
                    "staged_spec": _staging_spec(run_dir, spec),
                    "launcher": {"contention_detected": False},
                }

            def validator(*args):
                complete = all(name in roles for name in ("post_vs_native", "post_vs_pre_direct"))
                return {"status": "REVIEW_READY" if complete else "INCOMPLETE", "roles": dict(roles)}

            with (
                patch("v5_exp003_bundle_watch.preflight", side_effect=fake_preflight),
                patch("v5_exp003_bundle_watch._is_recoverable_false_positive_terminal", return_value=True),
                patch("v5_exp003_bundle_watch.recover_staging", side_effect=fake_recovery),
                patch("v5_exp003_bundle_watch.scan_published_role_artifacts", side_effect=fake_scan),
                patch("v5_exp003_bundle_watch.finalize_staged", return_value={"status": "PUBLISHED"}),
                patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
            ):
                result = run_once(
                    run_dir,
                    status_path=status_path,
                    validator=validator,
                    process_scan=lambda: [],
                    launcher=fake_launcher,
                )
            self.assertEqual(result["state"], "REVIEW_READY", result)
            self.assertEqual(launched, ["post_vs_pre_direct"])
            self.assertTrue(recovery_calls[0]["allow_contention_recovery"])
            self.assertEqual(recovery_calls[0]["original_terminal_status"], terminal)

    def test_similar_non_allowlisted_terminal_stays_byte_identical_and_never_enters_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            status_path = run_dir / "v5_exp003_bundle_watch_status.json"
            similar = {
                "run_dir": str(run_dir),
                "overall": "FAIL",
                "terminal": True,
                "state": "MEASUREMENT_CONTENTION_QUARANTINED",
                "freeze": {
                    "gate_iteration": 24900,
                    # One hand below the captured gate is deliberately close
                    # enough to catch a broad state-only resume predicate.
                    "gate_hands": 409_058_519,
                    "archive_sha256": "060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020",
                    "archive_actual_sha256": "060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020",
                },
                "quarantine": {
                    "state": "QUARANTINED",
                    "published": False,
                    "role": "post_vs_native",
                },
            }
            atomic_write_json(status_path, similar)
            before = status_path.read_bytes()
            with (
                patch("v5_exp003_bundle_watch.preflight", side_effect=AssertionError("must not preflight")),
                patch("v5_exp003_bundle_watch.recover_staging", side_effect=AssertionError("must not recover")),
            ):
                result = run_once(run_dir, status_path=status_path)
            self.assertEqual(result, similar)
            self.assertEqual(status_path.read_bytes(), before)
            self.assertFalse(list(run_dir.rglob("*.contention_reaudit.json")))
            self.assertFalse(list(run_dir.rglob("publish_manifest.json")))

    def test_validated_recovery_failure_preserves_terminal_without_preflight_or_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            status_path = run_dir / "v5_exp003_bundle_watch_status.json"
            freeze = {**FREEZE, "archive_path": str(run_dir / "post.pt")}
            terminal = {
                "run_dir": str(run_dir),
                "overall": "FAIL",
                "terminal": True,
                "state": "MEASUREMENT_CONTENTION_QUARANTINED",
                "freeze": freeze,
                "quarantine": {
                    "state": "QUARANTINED",
                    "published": False,
                    "role": "post_vs_native",
                },
            }
            atomic_write_json(status_path, terminal)
            before = status_path.read_bytes()
            with (
                patch("v5_exp003_bundle_watch._is_recoverable_false_positive_terminal", return_value=True),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "QUARANTINED"}),
                patch("v5_exp003_bundle_watch.preflight", side_effect=AssertionError("must not preflight")),
            ):
                result = run_once(run_dir, status_path=status_path)
            self.assertEqual(result, terminal)
            self.assertEqual(status_path.read_bytes(), before)

    def test_ci_precision_terminal_requires_explicit_inconclusive_judgment(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp).resolve()
            (run_dir / "post.pt").write_bytes(b"post")
            freeze = {**FREEZE, "archive_path": str(run_dir / "post.pt")}
            specs = _stage_specs(run_dir, freeze)
            roles = {
                "pre_vs_native": {"usable": True},
                "post_vs_native": structural_role(specs[0], usable=False),
                "post_vs_pre_direct": structural_role(specs[1], usable=True),
            }

            def fake_preflight(*args, **kwargs):
                return {
                    "overall": "PASS",
                    "state": "READY_TO_LAUNCH",
                    "terminal": False,
                    "freeze": dict(freeze),
                    "bundle": {"status": "CI_PRECISION_FAILED", "roles": dict(roles)},
                }

            def fake_scan(_run_dir, spec, _freeze):
                return {
                    "status": "PASS",
                    "selected": roles[spec.role],
                    "problems": [],
                    "partial_groups": [],
                    "matching_records": [],
                    "structural_records": [],
                }

            with (
                patch("v5_exp003_bundle_watch.preflight", side_effect=fake_preflight),
                patch("v5_exp003_bundle_watch.recover_staging", return_value={"status": "NONE"}),
                patch("v5_exp003_bundle_watch.scan_published_role_artifacts", side_effect=fake_scan),
                patch("v5_exp003_bundle_watch.process_identity", return_value={"pid": 1}),
            ):
                result = run_once(
                    run_dir,
                    validator=lambda *args: {"status": "CI_PRECISION_FAILED", "roles": dict(roles)},
                    process_scan=lambda: [],
                    launcher=lambda *args, **kwargs: self.fail("no new role may launch"),
                )
            self.assertEqual(result["overall"], "INCONCLUSIVE_JUDGMENT_REQUIRED")
            self.assertEqual(result["state"], "CI_PRECISION_FAILED_READY_FOR_EXPLICIT_INCONCLUSIVE_JUDGMENT")
            self.assertIn("do not retry", result["next_action"])


if __name__ == "__main__":
    unittest.main()
