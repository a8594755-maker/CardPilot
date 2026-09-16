#!/usr/bin/env python3
"""Frozen-runtime legacy-observation entrypoint for the session auditor."""
from pathlib import Path
import sys


BASE = Path(__file__).resolve().parent
RUNTIME = BASE / "prepared_runtime" / "scripts"
sys.path.insert(0, str(RUNTIME))

from alpha_holdem import audit_slumbot_v6_session  # noqa: E402


if __name__ == "__main__":
    if "--observation-bridge" not in sys.argv:
        sys.argv.extend(["--observation-bridge", "legacy-v4"])
    audit_slumbot_v6_session.main()
