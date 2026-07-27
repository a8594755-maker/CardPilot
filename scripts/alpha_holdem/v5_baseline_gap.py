#!/usr/bin/env python3
"""Compare V5 Slumbot evidence with project baselines and L6 target.

This report is intentionally evidence-gated. If no Slumbot CI artifact exists,
it says so directly instead of inferring strength from self-play or internal
probe scores.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_scorecard import build_scorecard


DEFAULT_BASELINE_NAME = "Fresh V4 direct Slumbot baseline (current harness, 2026-07-09)"
DEFAULT_BASELINE_BB100 = -71.383
DEFAULT_BASELINE_CI95 = 20.839
DEFAULT_BASELINE_HANDS = 20_400
DEFAULT_L6_TARGET_BB100 = 11.1
DEFAULT_L6_TOLERANCE_BB100 = 2.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def round_or_none(value: Any, digits: int = 3) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def classify_level(hands: int, bb100: float | None, lower: float | None, l6_target: float, l6_tolerance: float) -> str:
    if bb100 is None:
        return "UNPROVEN"
    l5 = hands >= 100_000 and bb100 > 0.0 and lower is not None and lower > 0.0
    if l5 and bb100 >= l6_target - l6_tolerance:
        return "L6"
    if l5:
        return "L5"
    if bb100 > 0.0:
        return "L4"
    if bb100 >= -10.0:
        return "L3"
    if bb100 >= -25.0:
        return "L2"
    if bb100 >= -50.0:
        return "L1"
    return "L0"


def compare_to_baseline(
    *,
    hands: int,
    bb100: float | None,
    lower: float | None,
    baseline_bb100: float,
    baseline_hands: int,
) -> dict[str, Any]:
    if bb100 is None:
        return {
            "answer": "UNKNOWN_NO_SLUMBOT_SCORE",
            "can_answer": False,
            "claim_allowed": False,
            "reason": "No Slumbot CI artifact exists for this V5 run.",
        }

    point_delta = bb100 - baseline_bb100
    lower_delta = lower - baseline_bb100 if lower is not None else None
    enough_hands = hands >= baseline_hands

    if not enough_hands:
        answer = "SAMPLE_TOO_SMALL_FOR_BASELINE_CLAIM"
        claim_allowed = False
        reason = f"Need at least {baseline_hands:,} Slumbot hands before baseline comparison is meaningful."
    elif lower is not None and lower > baseline_bb100:
        answer = "CI_LOWER_ABOVE_BASELINE"
        claim_allowed = True
        reason = "The 95% CI lower bound is above the baseline point estimate."
    elif bb100 > baseline_bb100:
        answer = "POINT_ESTIMATE_ABOVE_BASELINE_CI_UNPROVEN"
        claim_allowed = False
        reason = "Point estimate is above baseline, but CI lower bound does not clear baseline."
    else:
        answer = "NOT_ABOVE_BASELINE"
        claim_allowed = False
        reason = "Point estimate does not exceed the baseline."

    return {
        "answer": answer,
        "can_answer": enough_hands,
        "claim_allowed": claim_allowed,
        "reason": reason,
        "point_delta_bb100": round_or_none(point_delta),
        "lower_delta_bb100": round_or_none(lower_delta),
        "required_hands": baseline_hands,
    }


def l5_l6_gap(
    *,
    hands: int,
    bb100: float | None,
    lower: float | None,
    l6_target: float,
    l6_tolerance: float,
) -> dict[str, Any]:
    if bb100 is None:
        return {
            "to_l5_point_bb100": None,
            "to_l5_ci_lower_bb100": None,
            "to_l6_target_bb100": None,
            "formal_l5_ready": False,
            "formal_l6_ready": False,
            "blockers": ["no Slumbot CI result yet"],
        }

    blockers: list[str] = []
    if hands < 100_000:
        blockers.append("hands < 100000")
    if bb100 <= 0.0:
        blockers.append("bb/100 <= 0")
    if lower is None or lower <= 0.0:
        blockers.append("95% CI lower bound <= 0")

    formal_l5 = not blockers
    formal_l6 = formal_l5 and bb100 >= l6_target - l6_tolerance
    if formal_l5 and not formal_l6:
        blockers.append(f"bb/100 < L6 threshold {l6_target - l6_tolerance:.1f}")

    return {
        "to_l5_point_bb100": round_or_none(max(0.0, -bb100)),
        "to_l5_ci_lower_bb100": round_or_none(max(0.0, -(lower or 0.0))),
        "to_l6_target_bb100": round_or_none(l6_target - bb100),
        "l6_threshold_bb100": round_or_none(l6_target - l6_tolerance),
        "formal_l5_ready": formal_l5,
        "formal_l6_ready": formal_l6,
        "blockers": blockers,
    }


def extract_latest(scorecard: dict[str, Any]) -> dict[str, Any] | None:
    slumbot = scorecard.get("slumbot_ci") or {}
    latest = slumbot.get("latest")
    return latest if isinstance(latest, dict) else None


def build_baseline_gap(
    run_dir: Path,
    output_dir: Path,
    *,
    baseline_name: str = DEFAULT_BASELINE_NAME,
    baseline_bb100: float = DEFAULT_BASELINE_BB100,
    baseline_ci95: float = DEFAULT_BASELINE_CI95,
    baseline_hands: int = DEFAULT_BASELINE_HANDS,
    l6_target: float = DEFAULT_L6_TARGET_BB100,
    l6_tolerance: float = DEFAULT_L6_TOLERANCE_BB100,
) -> dict[str, Any]:
    scorecard = build_scorecard(run_dir, output_dir)
    latest = extract_latest(scorecard)
    hands = int((latest or {}).get("hands") or 0)
    bb100 = round_or_none((latest or {}).get("bb_per_100"))
    lower = round_or_none((latest or {}).get("lower_bound_bb_per_100"))
    upper = round_or_none((latest or {}).get("upper_bound_bb_per_100"))
    level = classify_level(hands, bb100, lower, l6_target, l6_tolerance)
    baseline_lower = baseline_bb100 - baseline_ci95
    baseline_upper = baseline_bb100 + baseline_ci95

    baseline_comparison = compare_to_baseline(
        hands=hands,
        bb100=bb100,
        lower=lower,
        baseline_bb100=baseline_bb100,
        baseline_hands=baseline_hands,
    )
    target_gap = l5_l6_gap(
        hands=hands,
        bb100=bb100,
        lower=lower,
        l6_target=l6_target,
        l6_tolerance=l6_tolerance,
    )

    if latest is None:
        overall = "UNPROVEN_NO_SLUMBOT_SCORE"
    elif target_gap["formal_l6_ready"]:
        overall = "L6_PROVEN"
    elif target_gap["formal_l5_ready"]:
        overall = "L5_PROVEN"
    elif baseline_comparison["claim_allowed"]:
        overall = "BASELINE_BEATEN_CI"
    elif baseline_comparison.get("answer") == "POINT_ESTIMATE_ABOVE_BASELINE_CI_UNPROVEN":
        overall = "BASELINE_POINT_UP_CI_UNPROVEN"
    else:
        overall = "BASELINE_NOT_PROVEN"

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "run_id": scorecard.get("run_id") or run_dir.name,
        "overall": overall,
        "latest_slumbot": {
            "exists": latest is not None,
            "path": (latest or {}).get("path"),
            "hands": hands if latest is not None else None,
            "bb_per_100": bb100,
            "lower_bound_bb_per_100": lower,
            "upper_bound_bb_per_100": upper,
            "milestone_level": (latest or {}).get("milestone_level") if latest else "UNPROVEN",
            "derived_level": level,
        },
        "reference_baseline": {
            "name": baseline_name,
            "bb_per_100": baseline_bb100,
            "ci95_bb_per_100": baseline_ci95,
            "hands": baseline_hands,
            "lower_bound_bb_per_100": round_or_none(baseline_lower),
            "upper_bound_bb_per_100": round_or_none(baseline_upper),
            "source_note": (
                "Current-harness V4 direct Slumbot 20.4k benchmark from "
                "reports/v4_vs_slumbot_fresh_20260709_final.json; supersedes "
                "the old 2026-05-07 -49.7 baseline."
            ),
        },
        "baseline_comparison": baseline_comparison,
        "targets": {
            "l5_rule": "100k+ Slumbot hands, bb/100 > 0, and 95% CI lower bound > 0.",
            "l6_target_bb_per_100": l6_target,
            "l6_tolerance_bb_per_100": l6_tolerance,
            "l6_threshold_bb_per_100": round_or_none(l6_target - l6_tolerance),
        },
        "gap": target_gap,
        "claim_rules": {
            "can_claim_stronger_than_v4": bool(baseline_comparison.get("claim_allowed")),
            "can_claim_l5": bool(target_gap.get("formal_l5_ready")),
            "can_claim_l6": bool(target_gap.get("formal_l6_ready")),
            "internal_probe_can_prove_baseline": False,
            "quick5k_can_prove_l5_or_l6": False,
        },
        "notes": [
            "This report uses Slumbot CI artifacts only for strength claims.",
            "Internal probes and self-play reward can guide debugging, but cannot prove V4/L5/L6 strength.",
            "20k promotion screens can justify spending on a larger formal run; only 100k+ can prove L5/L6.",
        ],
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    latest = summary.get("latest_slumbot") or {}
    baseline = summary.get("reference_baseline") or {}
    comparison = summary.get("baseline_comparison") or {}
    targets = summary.get("targets") or {}
    gap = summary.get("gap") or {}
    claims = summary.get("claim_rules") or {}

    lines = [
        "# V5 Baseline Gap",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Run: `{summary.get('run_id')}`",
        f"- Overall: **{summary.get('overall')}**",
        "",
        "## Latest Slumbot Evidence",
        "",
        f"- Exists: `{latest.get('exists')}`",
        f"- CI path: `{latest.get('path')}`",
        f"- Hands: `{latest.get('hands')}`",
        f"- bb/100: `{latest.get('bb_per_100')}`",
        f"- 95% CI lower: `{latest.get('lower_bound_bb_per_100')}`",
        f"- 95% CI upper: `{latest.get('upper_bound_bb_per_100')}`",
        f"- Derived level: `{latest.get('derived_level')}`",
        "",
        "## V4/BC Baseline",
        "",
        f"- Baseline: `{baseline.get('name')}`",
        f"- bb/100: `{baseline.get('bb_per_100')}` +/- `{baseline.get('ci95_bb_per_100')}` over `{baseline.get('hands')}` hands",
        f"- Baseline interval: `[{baseline.get('lower_bound_bb_per_100')}, {baseline.get('upper_bound_bb_per_100')}]`",
        "",
        "## Comparison",
        "",
        f"- Answer: `{comparison.get('answer')}`",
        f"- Can answer: `{comparison.get('can_answer')}`",
        f"- Claim allowed: `{comparison.get('claim_allowed')}`",
        f"- Point delta bb/100: `{comparison.get('point_delta_bb100')}`",
        f"- Lower-bound delta bb/100: `{comparison.get('lower_delta_bb100')}`",
        f"- Reason: {comparison.get('reason')}",
        "",
        "## L5/L6 Gap",
        "",
        f"- L5 point gap bb/100: `{gap.get('to_l5_point_bb100')}`",
        f"- L5 CI-lower gap bb/100: `{gap.get('to_l5_ci_lower_bb100')}`",
        f"- L6 target: `{targets.get('l6_target_bb_per_100')}` bb/100",
        f"- L6 threshold with tolerance: `{targets.get('l6_threshold_bb_per_100')}` bb/100",
        f"- Gap to L6 target bb/100: `{gap.get('to_l6_target_bb100')}`",
        f"- Blockers: `{gap.get('blockers')}`",
        "",
        "## Claim Rules",
        "",
        f"- Can claim stronger than V4/BC baseline: `{claims.get('can_claim_stronger_than_v4')}`",
        f"- Can claim L5: `{claims.get('can_claim_l5')}`",
        f"- Can claim L6: `{claims.get('can_claim_l6')}`",
        f"- Internal probe can prove baseline: `{claims.get('internal_probe_can_prove_baseline')}`",
        f"- quick5k can prove L5/L6: `{claims.get('quick5k_can_prove_l5_or_l6')}`",
        "",
        "## Notes",
        "",
    ]
    for note in summary.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a V5 baseline/L6 gap report.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--baseline-name", default=DEFAULT_BASELINE_NAME)
    parser.add_argument("--baseline-bb100", type=float, default=DEFAULT_BASELINE_BB100)
    parser.add_argument("--baseline-ci95", type=float, default=DEFAULT_BASELINE_CI95)
    parser.add_argument("--baseline-hands", type=int, default=DEFAULT_BASELINE_HANDS)
    parser.add_argument("--l6-target-bb100", type=float, default=DEFAULT_L6_TARGET_BB100)
    parser.add_argument("--l6-tolerance-bb100", type=float, default=DEFAULT_L6_TOLERANCE_BB100)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_baseline_gap(
        Path(args.run_dir),
        Path(args.output_dir),
        baseline_name=args.baseline_name,
        baseline_bb100=args.baseline_bb100,
        baseline_ci95=args.baseline_ci95,
        baseline_hands=args.baseline_hands,
        l6_target=args.l6_target_bb100,
        l6_tolerance=args.l6_tolerance_bb100,
    )
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
