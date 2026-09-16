"""Reuse the audited common-deck treatment-only evaluator for T=0.5."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SHARED = ROOT / "research/experiments/v6-source-greedy-margin-preservation-smoke-20260901/run_eval.py"
spec = importlib.util.spec_from_file_location("shared_treatment_eval", SHARED)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)
runner.BASE = BASE
runner.TREATMENT = BASE / "treatment/latest.pt"
runner.EXPECTED_TREATMENT_SHA = "895bb8d090eff2533d3dfd65244d8ac0ed8a7f29521e22ef778610c4edc26753"


if __name__ == "__main__":
    runner.main()
