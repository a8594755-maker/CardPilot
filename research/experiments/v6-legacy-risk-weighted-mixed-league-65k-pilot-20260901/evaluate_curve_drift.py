#!/usr/bin/env python3
"""Run the common 50k-state source-drift curve on risk-weighted archives."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = (
    HERE.parent
    / "v6-legacy-contract-mixed-league-65k-pilot-20260901"
    / "evaluate_curve_drift.py"
)

spec = importlib.util.spec_from_file_location("source_drift_evaluator", REFERENCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load evaluator: {REFERENCE}")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)
evaluator.HERE = HERE
evaluator.SEED = 2_026_120_203
evaluator.CANDIDATES = {
    "iter04": HERE / "training/checkpoints/checkpoint_iter000004_hands000000016440.pt",
    "iter08": HERE / "training/checkpoints/checkpoint_iter000008_hands000000032891.pt",
    "iter12": HERE / "training/checkpoints/checkpoint_iter000012_hands000000049397.pt",
    "iter16": HERE / "training/checkpoints/checkpoint_iter000016_hands000000065810.pt",
}

if __name__ == "__main__":
    evaluator.main()
