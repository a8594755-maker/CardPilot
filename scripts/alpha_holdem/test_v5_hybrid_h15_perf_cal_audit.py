from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h15_perf_cal_audit.py"


def test_audit_module_loads_and_freezes_thresholds() -> None:
    spec = importlib.util.spec_from_file_location("h15_perf_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.LOSS_RATIO_MIN == 0.95
    assert module.COMMON_BASELINE_RATIO_MIN == 0.95
