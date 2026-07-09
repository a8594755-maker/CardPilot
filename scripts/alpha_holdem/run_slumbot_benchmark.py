#!/usr/bin/env python3
"""Manual Slumbot benchmark launcher.

This keeps long benchmarks out of PowerShell quoting edge cases while reusing
the supervisor's log parsing and summary format.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from v55_supervisor import benchmark


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sessions", type=int, default=4)
    parser.add_argument("--hands-per-session", type=int, default=5000)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument(
        "--policy-mode",
        choices=["greedy", "greedy-guarded", "preflop-callguard", "sample", "guarded", "preflop-mixed"],
        default="greedy",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--callguard-include-open", action="store_true")
    args = parser.parse_args()

    benchmark(
        Path(args.model),
        args.tag,
        args.sessions,
        args.hands_per_session,
        sample=args.sample,
        temperature=args.temperature,
        policy_mode=args.policy_mode,
        guarded_allin_max_spr=args.guarded_allin_max_spr,
        guarded_allin_min_prob=args.guarded_allin_min_prob,
        callguard_min_prob=args.callguard_min_prob,
        callguard_ratio=args.callguard_ratio,
        callguard_include_open=args.callguard_include_open,
    )


if __name__ == "__main__":
    main()
