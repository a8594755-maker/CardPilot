#!/usr/bin/env python3
"""Fresh common-state high-risk comparison to the prior unweighted iter16."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = (
    HERE.parent
    / "v6-legacy-risk-weighted-source-margin-smoke-20260901"
    / "evaluate_source_drift.py"
)
UNWEIGHTED = (
    HERE.parent
    / "v6-legacy-contract-mixed-league-65k-pilot-20260901"
    / "training/checkpoints/checkpoint_iter000016_hands000000065966.pt"
)

spec = importlib.util.spec_from_file_location("risk_drift_evaluator", REFERENCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load evaluator: {REFERENCE}")
evaluator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(evaluator)
evaluator.HERE = HERE
evaluator.SEED = 2_026_120_204
evaluator.CANDIDATES = {
    "control": UNWEIGHTED,
    "treatment": (
        HERE
        / "training/checkpoints/checkpoint_iter000016_hands000000065810.pt"
    ),
}

if __name__ == "__main__":
    evaluator.main()
