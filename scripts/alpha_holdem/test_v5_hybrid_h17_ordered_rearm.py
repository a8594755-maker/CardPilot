from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h17_ordered_rearm.py"
REARM = ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1"
SPEC = importlib.util.spec_from_file_location("h17_rearm", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_control_stage_order_is_dependency_safe() -> None:
    assert MODULE.stage_plan("control") == (
        ("health", "protocol"),
        ("endpoint",),
        ("treatment_launch", "completion"),
    )


def test_treatment_stage_order_omits_recursive_launcher() -> None:
    assert MODULE.stage_plan("treatment") == (
        ("health", "protocol"),
        ("endpoint",),
        ("completion",),
    )


def test_fresh_status_requires_exact_lock_and_allowed_state() -> None:
    value = {"design_lock_sha256": "abc", "overall": "PENDING", "state": "ARM_RUNNING"}
    assert MODULE.fresh_status(value, "abc", {"ARM_RUNNING"})
    assert not MODULE.fresh_status(value, "def", {"ARM_RUNNING"})
    assert not MODULE.fresh_status(value, "abc", {"ARM_ENDPOINT_FROZEN"})


def test_canonical_rearm_classifies_h17_and_blocks_generic_paths() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT / ".test_tmp") as directory:
        run_dir = Path(directory)
        (run_dir / "run_manifest.json").write_text(json.dumps({
            "run_id": "v5_hybrid_h17_control_catchmse_same35051_20m_r1_20260719",
            "iteration": 35051,
            "config": {"opponent_assignment": "per-iteration"},
        }), encoding="utf-8")
        completed = subprocess.run([
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REARM),
            "-RunDir", str(run_dir), "-ValidateOnly",
        ], cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        classification = json.loads(completed.stdout)["run_classification"]
        assert classification["is_hybrid_h17_arm"] is True
        assert classification["block_generic_eval_and_slumbot"] is True


def test_canonical_h17_branch_launches_only_ordered_supervisor() -> None:
    source = REARM.read_text(encoding="utf-8-sig")
    branch = source.split("if ($script:isHybridH17Arm)", 1)[1].split("} elseif ($script:isHybridH11Arm)", 1)[0]
    assert "Launch-H17OrderedRearm" in branch
    assert "Launch-Health" not in branch
    assert "Launch-H11" not in branch
    assert "H17 exact ordered lifecycle terminally blocks every generic project path" in branch
