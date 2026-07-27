"""Sole serialization correction for the LRFT-F8R1 instantiated audit.

The parent completed its in-memory gates but left a partial JSON file when the
standard encoder rejected numpy.bool_.  This fresh wrapper changes only the exclusive
output path and scalar JSON conversion, then reruns the frozen instantiated audit.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import numpy as np


ROOT = Path(r"C:\Users\a8594\CardPilot")
TOKEN = "b35078ee7ad2ab123d5f9b0770538793"
PARENT_SOURCE = (
    ROOT
    / "scripts"
    / "alpha_holdem"
    / f"audit_v5_lrft_f8r1_preregistration_{TOKEN}.py"
)
PARENT_PARTIAL = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_preregistration_audit_{TOKEN}_20260723.json"
)
C1_OUT = (
    ROOT
    / "reports"
    / f"v5_lrft_f8r1_preregistration_audit_c1_{TOKEN}_20260723.json"
)
EXPECTED_PARENT_SOURCE_SHA = (
    "22a05e170e42c7efdc9583622d2102bade57580fda2ecb49d1e4b3c14cbd2c3b"
)
EXPECTED_PARENT_PARTIAL_SHA = (
    "0a308d7caaa5f769d5bce353e675fdc348d85f893faa746f2bbc80e1e11017ae"
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def native(value: Any) -> Any:
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        return float(value)
    if isinstance(value, np.ndarray):
        return value.tolist()
    raise TypeError(f"unsupported JSON value {type(value)!r}")


def main() -> int:
    if C1_OUT.exists():
        raise RuntimeError(f"refusing to overwrite {C1_OUT}")
    observed_source = sha(PARENT_SOURCE)
    observed_partial = sha(PARENT_PARTIAL)
    if observed_source != EXPECTED_PARENT_SOURCE_SHA:
        raise RuntimeError(
            f"parent source mismatch {observed_source} != {EXPECTED_PARENT_SOURCE_SHA}"
        )
    if observed_partial != EXPECTED_PARENT_PARTIAL_SHA:
        raise RuntimeError(
            f"parent partial mismatch {observed_partial} != {EXPECTED_PARENT_PARTIAL_SHA}"
        )
    spec = importlib.util.spec_from_file_location("lrft_f8r1_parent_audit", PARENT_SOURCE)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load frozen parent audit")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.OUT = C1_OUT
    standard_dumps = json.dumps

    def corrected_dump(obj: Any, stream: Any, **kwargs: Any) -> None:
        stream.write(standard_dumps(obj, default=native, **kwargs))

    module.json.dump = corrected_dump
    return int(module.main())


if __name__ == "__main__":
    raise SystemExit(main())
