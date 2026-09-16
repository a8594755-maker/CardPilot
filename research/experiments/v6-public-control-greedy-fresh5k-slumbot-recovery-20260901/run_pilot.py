"""Packaging-only recovery of the fixed eight-session greedy pilot."""
import importlib.util
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SOURCE_WRAPPER = ROOT / "research/experiments/v6-public-control-greedy-fresh5k-slumbot-20260901/run_pilot.py"
sys.path.insert(0, str(BASE))
from pilot_stats import summarize


def load_wrapper():
    spec = importlib.util.spec_from_file_location("failed_zero_hand_wrapper", SOURCE_WRAPPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main():
    wrapper = load_wrapper()
    wrapper.BASE = BASE
    wrapper.RUNTIME = BASE / "prepared_runtime/scripts"
    wrapper.summarize = summarize
    wrapper.session_id = lambda index: f"v6_public_control_greedy_fresh5k_recovery_20260901_s{index:02d}"
    wrapper.session_seed = lambda index: 2026137100 + index
    wrapper.main()


if __name__ == "__main__":
    main()
