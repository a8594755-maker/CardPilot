"""Fixed fresh5k current-v6 greedy Slumbot wrapper for the mixed control."""

import importlib.util
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT_MODULE = (
    ROOT / "research/experiments/v6-actor-raw-greedy-fresh5k-slumbot-20260901/run_pilot.py"
)
SOURCE = (
    ROOT / "research/experiments/v6-soup-uniform-pool-diversity-65k-pilot-20260901/control/latest.pt"
)
SOURCE_SHA = "ae9fcaaa726f05b2cb812d734284ed788102cbd3a092d8463efe47ad4d395de0"
RUNTIME = BASE / "prepared_runtime/scripts"

sys.path.insert(0, str(BASE))
from pilot_stats import summarize  # noqa: E402


def load_parent():
    spec = importlib.util.spec_from_file_location("greedy_fixed_session_parent", PARENT_MODULE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def session_id(index):
    return f"v6_soup_mixed_control_greedy_fresh5k_20260901_s{index:02d}"


def session_seed(index):
    return 2026112400 + index


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
