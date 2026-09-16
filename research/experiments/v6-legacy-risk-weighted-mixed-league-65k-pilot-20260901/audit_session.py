#!/usr/bin/env python3
"""Run the audited dynamic-FIFO session checker on this experiment."""
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
REFERENCE = (
    HERE.parent
    / "v6-legacy-contract-mixed-league-65k-pilot-20260901"
    / "audit_session.py"
)

spec = importlib.util.spec_from_file_location("dynamic_fifo_auditor", REFERENCE)
if spec is None or spec.loader is None:
    raise RuntimeError(f"cannot load auditor: {REFERENCE}")
auditor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(auditor)
auditor.TRAINING = HERE / "training"

if __name__ == "__main__":
    auditor.main()
