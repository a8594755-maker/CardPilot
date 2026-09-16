#!/usr/bin/env python3
"""CPU-corrected wrapper preserving the original CUDA replay source."""
from __future__ import annotations

import importlib.util
from pathlib import Path


BASE = Path(__file__).resolve().parent
SOURCE = BASE / "analyze_drift_cuda.py"


def main() -> None:
    spec = importlib.util.spec_from_file_location("cuda_first_drift_replay", SOURCE)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    module.BASE = BASE / "cpu"
    module.BASE.mkdir(exist_ok=False)
    module.torch.cuda.is_available = lambda: False
    module.main()


if __name__ == "__main__":
    main()
