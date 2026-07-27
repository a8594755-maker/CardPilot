#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))

import v5_hybrid_h11_protocol_watch as protocol


class FakeProcess:
    def __init__(self, pid: int, command: list[str], parent: int = 99) -> None:
        self.pid = pid
        self.info = {"pid": pid, "cmdline": command}
        self._command = command
        self._parent = parent

    def exe(self) -> str:
        return self._command[0]

    def ppid(self) -> int:
        return self._parent

    def create_time(self) -> float:
        return 1_789_000_000.0


class H11ControlPlaneTests(unittest.TestCase):
    def make_lock(self, root: Path) -> tuple[Path, str]:
        lock = root / "lock.json"
        lock.write_text(json.dumps({
            "design_id": "H11",
            "status": "LOCKED",
            "arms": {
                "control": {"run_dir": str(root / "control")},
                "treatment": {"run_dir": str(root / "treatment")},
            },
            "resource_isolation": {
                "full_trigger_provenance": ["pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"]
            },
        }, sort_keys=True), encoding="utf-8")
        return lock, hashlib.sha256(lock.read_bytes()).hexdigest()

    def run_active(self, root: Path, *extra: str) -> subprocess.CompletedProcess[str]:
        lock, digest = self.make_lock(root)
        return subprocess.run([
            sys.executable,
            str(ROOT / "scripts/alpha_holdem/v5_hybrid_h11_active_window.py"),
            *extra,
            "--sentinel", str(root / "sentinel.json"),
            "--design-lock", str(lock),
            "--expected-lock-sha256", digest,
        ], text=True, capture_output=True)

    def test_validate_accepts_prior_terminal_h10_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "sentinel.json").write_text(json.dumps({"design_id": "H10", "terminal": True}), encoding="utf-8")
            result = self.run_active(root, "validate")
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_control_protocol_abort_can_terminalize_without_treatment(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            activated = self.run_active(
                root, "activate", "--arm", "control", "--run-id",
                "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715",
            )
            self.assertEqual(activated.returncode, 0, activated.stderr)
            judgment = root / "judgment.json"
            judgment.write_text(json.dumps({"design_id": "H11", "overall": "INCONCLUSIVE"}), encoding="utf-8")
            terminal = self.run_active(root, "terminal", "--verdict", "INCONCLUSIVE", "--judgment", str(judgment))
            self.assertEqual(terminal.returncode, 0, terminal.stderr)
            value = json.loads((root / "sentinel.json").read_text(encoding="utf-8"))
            self.assertTrue(value["terminal"])
            self.assertFalse(value["active"])
            self.assertEqual(value["history"][-1]["terminal_from_arm"], "control")

    def test_treatment_protocol_abort_can_terminalize(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(self.run_active(root, "activate", "--arm", "control", "--run-id", "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715").returncode, 0)
            self.assertEqual(self.run_active(root, "activate", "--arm", "treatment", "--run-id", "v5_hybrid_h11_treatment_catchsmoothl1b1_same33834_20m_r1_20260715").returncode, 0)
            judgment = root / "judgment.json"
            judgment.write_text(json.dumps({"design_id": "H11", "overall": "FAIL"}), encoding="utf-8")
            self.assertEqual(self.run_active(root, "terminal", "--verdict", "FAIL", "--judgment", str(judgment)).returncode, 0)
            value = json.loads((root / "sentinel.json").read_text(encoding="utf-8"))
            self.assertEqual(value["history"][-1]["terminal_from_arm"], "treatment")

    def test_conflicting_terminal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            self.assertEqual(self.run_active(root, "activate", "--arm", "control", "--run-id", "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715").returncode, 0)
            first = root / "first.json"
            first.write_text(json.dumps({"design_id": "H11", "overall": "INCONCLUSIVE"}), encoding="utf-8")
            self.assertEqual(self.run_active(root, "terminal", "--verdict", "INCONCLUSIVE", "--judgment", str(first)).returncode, 0)
            second = root / "second.json"
            second.write_text(json.dumps({"design_id": "H11", "overall": "FAIL"}), encoding="utf-8")
            conflict = self.run_active(root, "terminal", "--verdict", "FAIL", "--judgment", str(second))
            self.assertNotEqual(conflict.returncode, 0)

    def test_unregistered_process_preserves_full_provenance(self) -> None:
        command = ["powershell.exe", "-Command", "Get-Content C:/Users/a/CardPilot/reports/state.json"]
        fake = FakeProcess(777, command, 42)
        with mock.patch.object(protocol.psutil, "process_iter", return_value=[fake]):
            found = protocol.forbidden_processes(123)
        self.assertEqual(len(found), 1)
        item = found[0]
        self.assertEqual(item["pid"], 777)
        self.assertEqual(item["parent_pid"], 42)
        self.assertEqual(item["command_line"], " ".join(command))
        self.assertEqual(item["command_line_sha256"], hashlib.sha256(item["command_line"].encode()).hexdigest())
        self.assertTrue(item["creation_time_utc"])
        self.assertEqual(item["executable"], "powershell.exe")

    def test_locked_lifecycle_and_path1_are_allowed(self) -> None:
        processes = [
            FakeProcess(1, ["python", "C:/x/CardPilot/scripts/alpha_holdem/v5_hybrid_h11_protocol_watch.py"]),
            FakeProcess(2, ["node", "C:/x/CardPilot/packages/cfr-solver/src/orchestration/solve-worker.ts"]),
            FakeProcess(3, ["node", "C:/x/CardPilot/packages/cfr-solver/src/scripts/solve-v3-parallel.ts"]),
        ]
        with mock.patch.object(protocol.psutil, "process_iter", return_value=processes):
            self.assertEqual(protocol.forbidden_processes(999), [])

    def test_evaluator_token_is_forbidden_with_provenance(self) -> None:
        fake = FakeProcess(444, ["python", "C:/x/CardPilot/scripts/alpha_holdem/v5_slumbot_benchmark_plan.py"])
        with mock.patch.object(protocol.psutil, "process_iter", return_value=[fake]):
            item = protocol.forbidden_processes(999)[0]
        self.assertEqual(item["token"], "v5_slumbot")
        self.assertIn("command_line_sha256", item)


if __name__ == "__main__":
    unittest.main()
