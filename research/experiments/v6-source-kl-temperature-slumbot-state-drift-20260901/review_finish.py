"""Run the independent distribution-replay review in this experiment directory."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = ROOT / "research/experiments/v6-slumbot-state-distribution-diagnostic-20260901/review_finish.py"


def main():
    spec = importlib.util.spec_from_file_location("distribution_review_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.main()


if __name__ == "__main__":
    main()
