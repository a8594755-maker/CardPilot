"""Run the preregistered untouched learned-anchor panel for iter16 endpoints."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SHARED = (
    ROOT
    / "research/experiments/v6-greedy-advantage-margin-smoke-20260901/run_eval.py"
)
spec = importlib.util.spec_from_file_location("shared_matched_eval", SHARED)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)
runner.BASE = BASE
runner.PAIRS = 2048
runner.SEED = 20261128
runner.ARMS = {
    "control": BASE / "control/latest.pt",
    "treatment": BASE / "treatment/latest.pt",
}


if __name__ == "__main__":
    runner.main()
