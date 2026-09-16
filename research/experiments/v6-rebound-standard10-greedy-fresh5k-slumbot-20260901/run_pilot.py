"""Current-v6 generic-greedy calibration for exact rebound Standard10."""

import importlib.util
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = (
    ROOT / "research/experiments/v6-source-kl-temperature-65k-greedy-fresh5k-slumbot-20260901/run_pilot.py"
)
SOURCE = ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor0.pt"
SOURCE_SHA = "944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2"
RUNTIME = BASE / "prepared_runtime/scripts"

sys.path.insert(0, str(BASE))
from pilot_stats import summarize  # noqa: E402


def load_parent():
    spec = importlib.util.spec_from_file_location("generic_greedy_fresh5k_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def session_id(index):
    return f"v6_rebound_standard10_greedy_fresh5k_20260901_s{index:02d}"


def session_seed(index):
    return 2026112000 + index


def main():
    impl = load_parent()
    impl.BASE = BASE
    impl.SOURCE = SOURCE
    impl.SOURCE_SHA = SOURCE_SHA
    impl.RUNTIME = RUNTIME
    impl.summarize = summarize
    impl.session_id = session_id
    impl.session_seed = session_seed
    impl.main()


if __name__ == "__main__":
    main()
