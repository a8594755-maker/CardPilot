#!/usr/bin/env python3
"""Compute Slumbot benchmark CI from per-hand JSONL rows.

Input rows are produced by:

  python scripts/alpha_holdem/play_slumbot.py \
    --hand-results-jsonl <path> \
    --result-json <path>

The formal L5 gate is:
  hands >= 100000, bb/100 > 0, lower_bound_bb_per_100 > 0.

The L6 target is near +11.1 bb/100.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
from pathlib import Path
from typing import Any


BIG_BLIND = 100.0
DEFAULT_BASELINE_BB100 = -71.383
DEFAULT_BASELINE_HANDS_MIN = 20_400


def load_rewards(paths: list[Path]) -> list[float]:
    rewards_bb: list[float] = []
    for path in paths:
        with path.open("r", encoding="utf-8-sig") as fp:
            for line in fp:
                line = line.strip()
                if not line:
                    continue
                row: dict[str, Any] = json.loads(line)
                if "winnings_bb" in row:
                    rewards_bb.append(float(row["winnings_bb"]))
                elif "winnings_chips" in row:
                    rewards_bb.append(float(row["winnings_chips"]) / BIG_BLIND)
                else:
                    raise ValueError(f"{path} row missing winnings_bb/winnings_chips")
    return rewards_bb


def expand_inputs(patterns: list[str]) -> list[Path]:
    paths: list[Path] = []
    for pattern in patterns:
        matches = [Path(p) for p in glob.glob(pattern)]
        if matches:
            paths.extend(sorted(matches))
        else:
            paths.append(Path(pattern))
    return paths


def sample_std(values: list[float], mean: float) -> float:
    if len(values) <= 1:
        return 0.0
    var = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return math.sqrt(var)


def classify_level(
    hands: int,
    bb_per_100: float,
    lower_bound_bb_per_100: float,
    l6_target_bb100: float,
    l6_tolerance_bb100: float,
) -> dict[str, Any]:
    """Classify a Slumbot result using the project L1-L6 milestone ladder."""
    l5_formal = hands >= 100_000 and bb_per_100 > 0.0 and lower_bound_bb_per_100 > 0.0
    l6 = l5_formal and bb_per_100 >= (l6_target_bb100 - l6_tolerance_bb100)
    if l6:
        level = "L6"
        meaning = "near AlphaHoldem paper target"
    elif l5_formal:
        level = "L5"
        meaning = "formal Slumbot win"
    elif bb_per_100 > 0.0:
        level = "L4"
        meaning = "candidate champion; CI gate not yet proven"
    elif bb_per_100 >= -10.0:
        level = "L3"
        meaning = "near break-even"
    elif bb_per_100 >= -25.0:
        level = "L2"
        meaning = "clear baseline improvement band"
    elif bb_per_100 >= -50.0:
        level = "L1"
        meaning = "near V4/BC-anchor baseline band"
    else:
        level = "L0"
        meaning = "below current baseline band"

    l5_blockers: list[str] = []
    if hands < 100_000:
        l5_blockers.append("hands < 100000")
    if bb_per_100 <= 0.0:
        l5_blockers.append("bb/100 <= 0")
    if lower_bound_bb_per_100 <= 0.0:
        l5_blockers.append("95% CI lower bound <= 0")

    return {
        "milestone_level": level,
        "milestone_meaning": meaning,
        "l5_formal_win": l5_formal,
        "l5_blockers": l5_blockers,
        "l6_near_paper_target": l6,
    }


def summarize(
    rewards_bb: list[float],
    l6_target_bb100: float,
    l6_tolerance_bb100: float,
    baseline_bb100: float,
    baseline_hands_min: int,
) -> dict[str, Any]:
    n = len(rewards_bb)
    if n == 0:
        raise ValueError("no hand rewards parsed")
    total_bb = sum(rewards_bb)
    avg_bb_per_hand = total_bb / n
    std_bb_per_hand = sample_std(rewards_bb, avg_bb_per_hand)
    ci95_bb_per_hand = 1.96 * std_bb_per_hand / math.sqrt(n) if n > 1 else 0.0
    bb_per_100 = avg_bb_per_hand * 100.0
    ci95_bb_per_100 = ci95_bb_per_hand * 100.0
    lower = bb_per_100 - ci95_bb_per_100
    upper = bb_per_100 + ci95_bb_per_100
    level = classify_level(
        hands=n,
        bb_per_100=bb_per_100,
        lower_bound_bb_per_100=lower,
        l6_target_bb100=l6_target_bb100,
        l6_tolerance_bb100=l6_tolerance_bb100,
    )
    baseline_delta = bb_per_100 - baseline_bb100
    return {
        "hands": n,
        "total_bb": total_bb,
        "avg_bb_per_hand": avg_bb_per_hand,
        "bb_per_100": bb_per_100,
        "std_bb_per_hand": std_bb_per_hand,
        "ci95_bb_per_hand": ci95_bb_per_hand,
        "ci95_bb_per_100": ci95_bb_per_100,
        "lower_bound_bb_per_100": lower,
        "upper_bound_bb_per_100": upper,
        **level,
        "l6_target_bb_per_100": l6_target_bb100,
        "l6_tolerance_bb_per_100": l6_tolerance_bb100,
        "baseline_bb_per_100": baseline_bb100,
        "baseline_delta_bb_per_100": baseline_delta,
        "baseline_point_estimate_improved": n >= baseline_hands_min and bb_per_100 > baseline_bb100,
        "baseline_ci_lower_above_baseline": n >= baseline_hands_min and lower > baseline_bb100,
        "baseline_hands_min": baseline_hands_min,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", help="Per-hand JSONL files or glob patterns.")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--l6-target-bb100", type=float, default=11.1)
    parser.add_argument("--l6-tolerance-bb100", type=float, default=2.0)
    parser.add_argument("--baseline-bb100", type=float, default=DEFAULT_BASELINE_BB100,
                        help="Fresh current-harness V4 direct Slumbot baseline point estimate.")
    parser.add_argument("--baseline-hands-min", type=int, default=DEFAULT_BASELINE_HANDS_MIN,
                        help="Minimum hands before baseline-improvement fields are meaningful.")
    args = parser.parse_args()

    paths = expand_inputs(args.inputs)
    rewards = load_rewards(paths)
    summary = summarize(
        rewards,
        l6_target_bb100=args.l6_target_bb100,
        l6_tolerance_bb100=args.l6_tolerance_bb100,
        baseline_bb100=args.baseline_bb100,
        baseline_hands_min=args.baseline_hands_min,
    )
    summary["input_files"] = [str(path) for path in paths]

    print(f"hands={summary['hands']:,}")
    print(f"bb/100={summary['bb_per_100']:+.2f}")
    print(f"95% CI bb/100=[{summary['lower_bound_bb_per_100']:+.2f}, {summary['upper_bound_bb_per_100']:+.2f}]")
    print(f"milestone_level={summary['milestone_level']} ({summary['milestone_meaning']})")
    print(f"l5_formal_win={summary['l5_formal_win']}")
    if summary["l5_blockers"]:
        print(f"l5_blockers={'; '.join(summary['l5_blockers'])}")
    print(f"l6_near_paper_target={summary['l6_near_paper_target']}")
    print(f"baseline_delta_bb/100={summary['baseline_delta_bb_per_100']:+.2f}")
    print(f"baseline_point_estimate_improved={summary['baseline_point_estimate_improved']}")
    print(f"baseline_ci_lower_above_baseline={summary['baseline_ci_lower_above_baseline']}")

    if args.out_json:
        out_path = Path(args.out_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote={out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
