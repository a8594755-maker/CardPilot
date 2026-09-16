"""Run the untouched-seed matched source-KL-temperature iter15 panel."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SHARED = ROOT / "research/experiments/v6-greedy-advantage-margin-smoke-20260901/run_eval.py"
spec = importlib.util.spec_from_file_location("shared_matched_eval", SHARED)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)
runner.BASE = BASE
runner.PAIRS = 4096
runner.SEED = 20261118
runner.ARMS = {
    "control": BASE / "frozen/control_iter15.pt",
    "treatment": BASE / "frozen/treatment_iter15.pt",
}


if __name__ == "__main__":
    runner.main()
