from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

from scripts.alpha_holdem import v5_hybrid_h10_protocol_watch as protocol_watch


ROOT = Path(__file__).resolve().parents[2]
TOOL = ROOT / "scripts/alpha_holdem/v5_hybrid_h10_active_window.py"
PLANNER = ROOT / "scripts/alpha_holdem/v5_slumbot_benchmark_plan.py"
CONTROL = "v5_hybrid_h10_control_catchmse_same33834_20m_r1_20260715"
TREATMENT = "v5_hybrid_h10_treatment_catchsmoothl1b1_same33834_20m_r1_20260715"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, str(TOOL), *args], cwd=ROOT, text=True, capture_output=True)


def test_h10_active_window_transitions_and_planner_command_block(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"design_id": "H10", "status": "LOCKED"}) + "\n", encoding="utf-8")
    lock_sha = sha(lock)
    sentinel = tmp_path / "active.json"
    common = ("--sentinel", str(sentinel), "--design-lock", str(lock), "--expected-lock-sha256", lock_sha)

    assert run("activate", *common, "--arm", "control", "--run-id", CONTROL).returncode == 0
    current = json.loads(sentinel.read_text(encoding="utf-8"))
    assert current["active"] is True and current["arm"] == "control"

    plan = tmp_path / "plan.json"
    planner = subprocess.run(
        [
            sys.executable,
            str(PLANNER),
            "--run-dir",
            str(tmp_path / "missing-run"),
            "--stage",
            "quick5k",
            "--active-window-sentinel",
            str(sentinel),
            "--out-json",
            str(plan),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
    )
    assert planner.returncode == 1
    assert "command:" not in planner.stdout
    result = json.loads(plan.read_text(encoding="utf-8"))
    assert result["overall"] == "BLOCKED"
    assert result["command"] == ""
    assert result["active_window_sentinel"]["active_block"] is True

    assert run("activate", *common, "--arm", "treatment", "--run-id", TREATMENT).returncode == 0
    judgment = tmp_path / "judgment.json"
    judgment.write_text(json.dumps({"design_id": "H10", "overall": "FAIL"}) + "\n", encoding="utf-8")
    assert run("terminal", *common, "--verdict", "FAIL", "--judgment", str(judgment)).returncode == 0
    terminal = json.loads(sentinel.read_text(encoding="utf-8"))
    assert terminal["active"] is False and terminal["terminal"] is True


def test_h10_active_window_rejects_wrong_run_identity(tmp_path: Path) -> None:
    lock = tmp_path / "lock.json"
    lock.write_text(json.dumps({"design_id": "H10", "status": "LOCKED"}) + "\n", encoding="utf-8")
    result = run(
        "activate",
        "--sentinel",
        str(tmp_path / "active.json"),
        "--design-lock",
        str(lock),
        "--expected-lock-sha256",
        sha(lock),
        "--arm",
        "control",
        "--run-id",
        TREATMENT,
    )
    assert result.returncode != 0


def test_h10_protocol_detects_exact_evaluators_and_unregistered_project_processes(monkeypatch) -> None:
    class FakeProcess:
        def __init__(self, pid: int, command: str):
            self.pid = pid
            self.info = {"pid": pid, "cmdline": command.split()}

    processes = [
        FakeProcess(1, "python C:/Users/a8594/CardPilot/scripts/alpha_holdem/train_v5.py"),
        FakeProcess(2, "python C:/Users/a8594/CardPilot/scripts/alpha_holdem/v5_hybrid_h10_endpoint_watch.py"),
        FakeProcess(3, "node C:/Users/a8594/CardPilot/packages/cfr-solver/src/orchestration/solve-worker.ts"),
        FakeProcess(4, "python C:/Users/a8594/CardPilot/scripts/alpha_holdem/v5_slumbot_benchmark_plan.py"),
        FakeProcess(5, "python C:/Users/a8594/CardPilot/scripts/alpha_holdem/unregistered_probe.py"),
    ]
    monkeypatch.setattr(protocol_watch.psutil, "process_iter", lambda _attrs: processes)
    found = protocol_watch.forbidden_processes(1)
    assert {row["pid"] for row in found} == {4, 5}
    assert any("v5_slumbot" in row["token"] for row in found)
    assert any(row["token"] == "unregistered_cardpilot_project_process" for row in found)
