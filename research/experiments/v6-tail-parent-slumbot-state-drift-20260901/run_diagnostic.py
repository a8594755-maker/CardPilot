"""Reuse the reviewed distribution-replay engine for tail versus parent."""
import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = ROOT / "research/experiments/v6-slumbot-state-distribution-diagnostic-20260901/run_diagnostic.py"
PARENT = ROOT / "research/experiments/v6-actor-tail-greedy-fresh5k-slumbot-20260901"
TAIL = PARENT / "frozen/final.pt"
RAW_PARENT = ROOT / "research/experiments/v6-actor-ema-terminal-smoke-20260831/frozen/raw.pt"
TAIL_SHA = "6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b"
PARENT_SHA = "9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4"


def main():
    spec = importlib.util.spec_from_file_location("distribution_replay_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.PARENT = PARENT
    module.RAW = TAIL
    module.SOURCE = RAW_PARENT
    module.RAW_SHA = TAIL_SHA
    module.SOURCE_SHA = PARENT_SHA
    module.main()


if __name__ == "__main__":
    main()

