#!/usr/bin/env python3
"""Fresh common-state drift comparison for risk-scaled release."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = (
    HERE.parent
    / "v6-legacy-risk-weighted-source-margin-smoke-20260901"
    / "evaluate_source_drift.py"
)
spec = importlib.util.spec_from_file_location("risk_drift_evaluator", REFERENCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load evaluator: {REFERENCE}")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)
evaluator.HERE = HERE
evaluator.SEED = 2_026_120_306
evaluator.CANDIDATES = {
    "control": HERE / "control/latest.pt",
    "treatment": HERE / "treatment/latest.pt",
}

if __name__ == "__main__":
    evaluator.main()
