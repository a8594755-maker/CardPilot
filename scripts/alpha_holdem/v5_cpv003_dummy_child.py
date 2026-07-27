#!/usr/bin/env python3
"""Disposable CPV003 child; never imports trainer code."""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--token", required=True)
    parser.add_argument("--spawn-grandchild", action="store_true")
    args = parser.parse_args()
    grandchild = None
    if args.spawn_grandchild:
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)
        grandchild = subprocess.Popen(
            [sys.executable, "-u", str(Path(__file__).resolve()), "--role", f"{args.role}_descendant", "--token", args.token],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=creationflags,
        )
    try:
        while True:
            time.sleep(1.0)
    finally:
        if grandchild is not None and grandchild.poll() is None:
            grandchild.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
