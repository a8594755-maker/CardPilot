from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h16_perf_cal_audit.py"


def test_audit_module_loads_and_freezes_thresholds() -> None:
    spec = importlib.util.spec_from_file_location("h16_perf_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.THROUGHPUT_RATIO_MIN == 0.85
    assert module.MSE_STABILITY_RATIO_MIN == 0.95
