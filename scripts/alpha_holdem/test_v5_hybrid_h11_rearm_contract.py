from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REARM = ROOT / "scripts/alpha_holdem/v5_rearm_watchers.ps1"


def test_h11_rearm_validate_only_classifies_and_blocks_generic_paths() -> None:
    with tempfile.TemporaryDirectory(dir=ROOT / ".test_tmp") as td:
        run_dir = Path(td)
        (run_dir / "run_manifest.json").write_text(json.dumps({
            "run_id": "v5_hybrid_h11_control_catchmse_same33834_20m_r1_20260715",
            "iteration": 33834,
            "config": {"opponent_assignment": "per-iteration"},
        }), encoding="utf-8")
        completed = subprocess.run([
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(REARM),
            "-RunDir", str(run_dir), "-ValidateOnly",
        ], cwd=ROOT, text=True, capture_output=True)
        assert completed.returncode == 0, completed.stderr
        value = json.loads(completed.stdout)
        classification = value["run_classification"]
        assert classification["is_hybrid_h11_arm"] is True
        assert classification["block_generic_eval_and_slumbot"] is True


def test_h11_strict_rearm_contains_only_locked_lifecycle_launches() -> None:
    source = REARM.read_text(encoding="utf-8-sig")
    required = (
        "if ($script:isHybridH11Arm)",
        "Launch-H11ProtocolWatch",
        "Launch-H11TreatmentLaunchWatch",
        "Launch-H11CompletionWatch",
        "H11 strict active-window contract terminally blocks every non-H11 project path",
        "scripts/alpha_holdem/v5_hybrid_h11_endpoint_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h11_protocol_watch.py",
        "scripts/alpha_holdem/v5_hybrid_h11_completion_watch.py",
    )
    for token in required:
        assert token in source
