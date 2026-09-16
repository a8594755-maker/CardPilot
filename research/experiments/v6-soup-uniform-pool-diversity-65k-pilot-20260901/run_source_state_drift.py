"""Replay both iter16 endpoints on the source soup's audited Slumbot states."""

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ENGINE = (
    ROOT
    / "research/experiments/v6-procedural-opponent-domain-randomization-pilot-20260901/evaluate_preservation.py"
)
CORPUS = (
    ROOT
    / "research/experiments/v6-procedural-iter32-soup-greedy-fresh20k-slumbot-20260901"
)
SOURCE = (
    ROOT
    / "research/experiments/v6-procedural-iter32-soup-preservation-20260901/frozen/treatment.pt"
)
SOURCE_SHA256 = "66c2254d96e36710c1b326d17026099e6ccabdec70d8e2333cfbef26a63c4a6c"


def main() -> None:
    spec = importlib.util.spec_from_file_location("source_state_replay", ENGINE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.CORPUS = CORPUS
    module.EXPECTED_PARENT_SHA256 = SOURCE_SHA256
    module.main()


if __name__ == "__main__":
    main()
