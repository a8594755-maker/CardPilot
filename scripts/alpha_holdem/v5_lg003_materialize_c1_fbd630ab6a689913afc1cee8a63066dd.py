#!/usr/bin/env python3
"""Sole pre-output correction for LG003's materializer hunk-count guard."""

from __future__ import annotations

import hashlib
from pathlib import Path


HERE = Path(__file__).resolve().parent
PARENT = HERE / "v5_lg003_materialize_fbd630ab6a689913afc1cee8a63066dd.py"
PARENT_SHA256 = "c70d9a63ba18420635fb1bb0c059dc41acf58c51cc45d7ab632e1a7575f62e04"


def main() -> None:
    parent_bytes = PARENT.read_bytes()
    if hashlib.sha256(parent_bytes).hexdigest() != PARENT_SHA256:
        raise SystemExit("failed parent materializer identity mismatch")
    parent_source = parent_bytes.decode("utf-8")
    old = "    if applied != 86:\n"
    new = "    if applied != 90:\n"
    if parent_source.count(old) != 1:
        raise SystemExit("sole registered correction anchor mismatch")
    corrected = parent_source.replace(old, new, 1)
    namespace = {
        "__name__": "v5_lg003_materialize_c1",
        "__file__": str(PARENT),
    }
    exec(compile(corrected, str(PARENT), "exec"), namespace)
    namespace["main"]()


if __name__ == "__main__":
    main()
