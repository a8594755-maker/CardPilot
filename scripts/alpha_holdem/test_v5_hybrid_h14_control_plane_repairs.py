"""Adversarial fixtures for the H12 incident modes required before H14 registration."""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/alpha_holdem"))

import v5_hybrid_h12_health_watch as health
import v5_hybrid_h12_protocol_watch as protocol


class FakeSupervisor:
    def __init__(self, pid: int, command: list[str]) -> None:
        self.pid = pid
        self.info = {"pid": pid, "cmdline": command}

    def exe(self) -> str:
        return self.info["cmdline"][0]

    def ppid(self) -> int:
        return 1

    def create_time(self) -> float:
        return 1_789_000_000.0


def test_h12_incident_fixture_absent_startup_log_is_pending_not_failure(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert health.startup_log_gate(run_dir, 10.0, 11.0, 180.0) == "PENDING"


def test_absent_startup_log_fails_only_at_frozen_deadline(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    assert health.startup_log_gate(run_dir, 10.0, 190.0, 180.0) == "TIMEOUT"


def test_h12_incident_fixture_exact_ordered_supervisor_is_not_violation() -> None:
    command = ["python", "C:/Users/a/CardPilot/scripts/alpha_holdem/v5_hybrid_h12_ordered_rearm.py", "--arm", "control"]
    joined = " ".join(command)
    fake = FakeSupervisor(41212, command)
    with mock.patch.object(protocol.psutil, "process_iter", return_value=[fake]):
        assert protocol.forbidden_processes(29392, 41212, hashlib.sha256(joined.encode()).hexdigest()) == []


def test_spoofed_ordered_supervisor_pid_fails_closed() -> None:
    fake = FakeSupervisor(41212, ["python", "C:/Users/a/CardPilot/unregistered.py"])
    with mock.patch.object(protocol.psutil, "process_iter", return_value=[fake]):
        found = protocol.forbidden_processes(29392, 41212, "0" * 64)
    assert found[0]["token"] == "allowed_supervisor_identity_mismatch"


def test_canonical_rearm_nonzero_contract_is_explicit() -> None:
    source = (ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1").read_text(encoding="utf-8-sig")
    assert "if (-not $survivalPass) {\n    exit 3\n}" in source


def test_both_launchers_require_status_survival_true() -> None:
    for name in ("v5_hybrid_h12_launch_control.ps1", "v5_hybrid_h12_launch_treatment.ps1"):
        source = (ROOT / "scripts/alpha_holdem" / name).read_text(encoding="utf-8-sig")
        assert "watcher_rearm_status.json" in source
        assert "if(-not [bool]$rearmStatus.survival_pass)" in source
