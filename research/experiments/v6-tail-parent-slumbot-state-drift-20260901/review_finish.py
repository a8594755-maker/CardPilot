"""Run the independent state-metric reviewer with this experiment as base."""
import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
REVIEWER = ROOT / "research/experiments/v6-slumbot-state-distribution-diagnostic-20260901/review_finish.py"


def main():
    spec = importlib.util.spec_from_file_location("state_metric_reviewer", REVIEWER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.main()


if __name__ == "__main__":
    main()

