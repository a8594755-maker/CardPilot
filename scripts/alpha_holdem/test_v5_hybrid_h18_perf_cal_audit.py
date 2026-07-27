from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/alpha_holdem/v5_hybrid_h18_perf_cal_audit.py"


def test_audit_module_loads_and_freezes_thresholds() -> None:
    spec = importlib.util.spec_from_file_location("h18_perf_audit", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.THROUGHPUT_RATIO_MIN == 0.85
    assert module.MSE_STABILITY_RATIO_MIN == 0.95
    assert module.MODEL_TOLERANCE == 1e-6
    assert module.OPTIMIZER_TOLERANCE == 1e-8


def test_audit_recomputes_every_registered_gate() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "timing_dimensions", "timing_medians_recomputed",
        "throughput_recomputed_and_pass", "stability_recomputed_and_pass",
        "model_maximum_recomputed", "optimizer_maximum_recomputed",
        "bitwise_gate_forbidden", "trainerless_no_checkpoint", "path1_unchanged",
    ):
        assert token in source
