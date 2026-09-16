"""Replay source-KL-temperature Slumbot states against rebound Standard10."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = ROOT / "research/experiments/v6-slumbot-state-distribution-diagnostic-20260901/run_diagnostic.py"
PARENT = ROOT / "research/experiments/v6-source-kl-temperature-65k-greedy-fresh5k-slumbot-20260901"
TREATMENT = PARENT / "frozen/final.pt"
SOURCE = ROOT / "research/experiments/v6-physical1m-learning-curve-20260831/frozen/anchor0.pt"
TREATMENT_SHA = "9e1566812f6550415be4d7d90b21180080a8c3f6f9b0096457a04a98a54b0847"
SOURCE_SHA = "944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2"


def main():
    spec = importlib.util.spec_from_file_location("distribution_replay_engine", ENGINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.BASE = BASE
    module.PARENT = PARENT
    module.RAW = TREATMENT
    module.SOURCE = SOURCE
    module.RAW_SHA = TREATMENT_SHA
    module.SOURCE_SHA = SOURCE_SHA
    module.main()


if __name__ == "__main__":
    main()
