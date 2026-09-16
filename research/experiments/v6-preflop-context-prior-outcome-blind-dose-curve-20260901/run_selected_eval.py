"""Run one untouched learned-anchor panel for the outcome-blind iter4 dose."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SHARED = (
    ROOT
    / "research/experiments/v6-greedy-advantage-margin-smoke-20260901/run_eval.py"
)
PILOT = ROOT / "research/experiments/v6-preflop-head-only-context-prior-65k-pilot-20260901"
spec = importlib.util.spec_from_file_location("shared_matched_eval", SHARED)
runner = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(runner)
runner.BASE = BASE
runner.PAIRS = 2048
runner.SEED = 20261129
runner.ARMS = {
    "control": PILOT / "control/checkpoints/checkpoint_iter000004_hands000000016462.pt",
    "treatment": PILOT / "treatment/checkpoints/checkpoint_iter000004_hands000000016468.pt",
}


if __name__ == "__main__":
    runner.main()
