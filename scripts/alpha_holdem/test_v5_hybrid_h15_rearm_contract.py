from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REARM = ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1"


def test_h15_rearm_validate_only_classifies_and_blocks_generic_paths() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT / ".test_tmp") as td:
        run_dir = Path(td)
        (run_dir / "run_manifest.json").write_text(json.dumps({
            "run_id": "v5_hybrid_h15_control_catchmse_same35051_20m_r1_20260719",
            "iteration": 35051,
            "config": {"opponent_assignment": "per-iteration"},
        }), encoding="utf-8")
        completed = subprocess.run([
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REARM),
            "-RunDir", str(run_dir), "-ValidateOnly",
        ], cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        value = json.loads(completed.stdout)
        classification = value["run_classification"]
        assert classification["is_hybrid_h15_arm"] is True
        assert classification["block_generic_eval_and_slumbot"] is True


def test_h15_strict_rearm_contains_only_locked_lifecycle_launches() -> None:
    source = REARM.read_text(encoding="utf-8-sig")
    required = (
        "if ($script:isHybridH15Arm)",
        "Launch-H15OrderedRearm",
        "H15 exact ordered lifecycle terminally blocks every generic project path",
        "scripts/alpha_holdem/v5_hybrid_h15_ordered_rearm.py",
        "reports/v5_hybrid_h15_design_lock_v",
        "_20260719.json",
    )
    for token in required:
        assert token in source


def test_rearm_returns_nonzero_when_survival_fails() -> None:
    source = REARM.read_text(encoding="utf-8-sig")
    assert "if (-not $survivalPass) {\n    exit 3\n}" in source


def test_launcher_requires_rearm_status_survival_true() -> None:
    for name in ("v5_hybrid_h15_launch_control.ps1", "v5_hybrid_h15_launch_treatment.ps1"):
        launcher = (ROOT / "scripts/alpha_holdem" / name).read_text(encoding="utf-8-sig")
        assert "watcher_rearm_status.json" in launcher
        assert "rearm survival_pass=false" in launcher
