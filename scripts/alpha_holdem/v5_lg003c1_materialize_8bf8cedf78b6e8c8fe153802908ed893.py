#!/usr/bin/env python3
"""Materialize the sole LG003C1 pre-output runtime correction."""

from __future__ import annotations

import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PARENT = ROOT / "scripts" / "alpha_holdem" / "v5_lg003_train_fbd630ab6a689913afc1cee8a63066dd.py"
OUT = ROOT / "scripts" / "alpha_holdem" / "v5_lg003c1_train_8bf8cedf78b6e8c8fe153802908ed893.py"
PARENT_SHA256 = "a887ddae0e94065e5757ff88c650901fe88eee3a2cbc542b371ddf124f285615"


def replace_once(source: str, old: str, new: str, label: str) -> str:
    if source.count(old) != 1:
        raise RuntimeError(f"{label} anchor count is {source.count(old)}")
    return source.replace(old, new, 1)


def main() -> None:
    if OUT.exists():
        raise SystemExit("refusing to overwrite LG003C1 trainer")
    parent_bytes = PARENT.read_bytes()
    if hashlib.sha256(parent_bytes).hexdigest() != PARENT_SHA256:
        raise SystemExit("terminal LG003 parent trainer identity mismatch")
    source = parent_bytes.decode("utf-8")
    source = replace_once(
        source,
        "    def checkpoint_payload() -> dict:\n",
        "    assignment_provenance_last_sha = None\n"
        "    assignment_provenance_last_iteration = None\n\n"
        "    def checkpoint_payload() -> dict:\n",
        "early initialization",
    )
    source = replace_once(
        source,
        "    assignment_provenance_fh = None\n"
        "    assignment_provenance_last_sha = None\n"
        "    assignment_provenance_last_iteration = None\n"
        "    if args.opponent_assignment_provenance_file:\n",
        "    assignment_provenance_fh = None\n"
        "    if args.opponent_assignment_provenance_file:\n",
        "late initialization removal",
    )
    source = replace_once(
        source,
        "v5_lg003_fbd630ab6a689913afc1cee8a63066dd_20260723",
        "v5_lg003c1_8bf8cedf78b6e8c8fe153802908ed893_20260723",
        "fresh output root",
    )
    compile(source, str(OUT), "exec")
    OUT.write_text(source, encoding="utf-8", newline="\n")
    print(hashlib.sha256(OUT.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
