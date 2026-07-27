#!/usr/bin/env python3
"""Compare pre/post action-prior V5 training action-mix trends.

This is a diagnostic only. It does not prove Slumbot strength; it checks
whether an action-prior continuation is moving known leak indicators in the
intended direction before the next external benchmark.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_monitor import parse_log  # noqa: E402


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def quantile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * q)))
    return ordered[idx]


def summarize_run(run_dir: Path, tail: int) -> dict[str, Any]:
    rows = parse_log(run_dir / "latest_train.log")
    selected = rows[-tail:] if tail > 0 else rows
    postflop = [r["postflop_action_mix"] for r in selected if r.get("postflop_action_mix") is not None]
    preflop = [r["preflop_action_mix"] for r in selected if r.get("preflop_action_mix") is not None]
    action_prior = [r["action_prior_loss"] for r in selected if r.get("action_prior_loss") is not None]
    postflop_ra = [m["raise"] + m["allin"] for m in postflop]
    postflop_call = [m["call"] for m in postflop]
    preflop_allin = [m["allin"] for m in preflop]
    preflop_call = [m["call"] for m in preflop]
    health = load_json(run_dir / "health_status.json") or {}
    return {
        "run_dir": str(run_dir),
        "rows_total": len(rows),
        "rows_used": len(selected),
        "first_iteration": selected[0]["iteration"] if selected else None,
        "latest_iteration": selected[-1]["iteration"] if selected else None,
        "first_hands": selected[0]["hands"] if selected else None,
        "latest_hands": selected[-1]["hands"] if selected else None,
        "health_overall": health.get("overall"),
        "latest_reward100": selected[-1]["reward_window_100"] if selected else None,
        "hands_per_second_mean": mean([r["hands_per_second"] for r in selected]),
        "postflop_raise_allin_mean": mean(postflop_ra),
        "postflop_raise_allin_p50": quantile(postflop_ra, 0.5),
        "postflop_raise_allin_max": max(postflop_ra) if postflop_ra else None,
        "postflop_call_mean": mean(postflop_call),
        "postflop_call_min": min(postflop_call) if postflop_call else None,
        "preflop_allin_mean": mean(preflop_allin),
        "preflop_allin_max": max(preflop_allin) if preflop_allin else None,
        "preflop_call_mean": mean(preflop_call),
        "preflop_call_min": min(preflop_call) if preflop_call else None,
        "action_prior_loss_mean": mean(action_prior),
        "action_prior_loss_latest": action_prior[-1] if action_prior else None,
    }


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def build_summary(args: argparse.Namespace) -> dict[str, Any]:
    baseline = summarize_run(Path(args.baseline_run_dir), args.tail)
    candidate = summarize_run(Path(args.candidate_run_dir), args.tail)
    checks: list[dict[str, str]] = []

    def add_check(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if candidate["rows_used"] < args.min_candidate_rows:
        add_check("candidate_rows", "WARN", f"candidate rows {candidate['rows_used']} < {args.min_candidate_rows}")
    else:
        add_check("candidate_rows", "PASS", f"candidate rows {candidate['rows_used']} >= {args.min_candidate_rows}")

    if candidate["action_prior_loss_latest"] is None:
        add_check("action_prior_active", "FAIL", "candidate log has no action-prior loss")
    else:
        add_check("action_prior_active", "PASS", f"latest action-prior loss {candidate['action_prior_loss_latest']:.4f}")

    candidate_ra = candidate["postflop_raise_allin_mean"]
    baseline_ra = baseline["postflop_raise_allin_mean"]
    candidate_call = candidate["postflop_call_mean"]
    baseline_call = baseline["postflop_call_mean"]
    ra_delta = candidate_ra - baseline_ra if candidate_ra is not None and baseline_ra is not None else None
    call_delta = candidate_call - baseline_call if candidate_call is not None and baseline_call is not None else None
    candidate_pre_allin = candidate["preflop_allin_mean"]
    baseline_pre_allin = baseline["preflop_allin_mean"]
    candidate_pre_call = candidate["preflop_call_mean"]
    baseline_pre_call = baseline["preflop_call_mean"]
    pre_allin_delta = (
        candidate_pre_allin - baseline_pre_allin
        if candidate_pre_allin is not None and baseline_pre_allin is not None
        else None
    )
    pre_call_delta = (
        candidate_pre_call - baseline_pre_call
        if candidate_pre_call is not None and baseline_pre_call is not None
        else None
    )

    if candidate["postflop_raise_allin_max"] is not None and candidate["postflop_raise_allin_max"] >= args.postflop_ra_fail:
        add_check(
            "candidate_postflop_ra",
            "FAIL",
            f"candidate max RA {candidate['postflop_raise_allin_max']:.3f} >= {args.postflop_ra_fail:.3f}",
        )
    elif candidate_ra is not None and candidate_ra >= args.postflop_ra_warn:
        add_check(
            "candidate_postflop_ra",
            "WARN",
            f"candidate mean RA {candidate_ra:.3f} >= {args.postflop_ra_warn:.3f}",
        )
    else:
        add_check("candidate_postflop_ra", "PASS", f"candidate mean RA {fmt(candidate_ra)}")

    if candidate["postflop_call_min"] is not None and candidate["postflop_call_min"] <= args.postflop_call_fail:
        add_check(
            "candidate_postflop_call",
            "FAIL",
            f"candidate min call {candidate['postflop_call_min']:.3f} <= {args.postflop_call_fail:.3f}",
        )
    elif candidate_call is not None and candidate_call <= args.postflop_call_warn:
        add_check(
            "candidate_postflop_call",
            "WARN",
            f"candidate mean call {candidate_call:.3f} <= {args.postflop_call_warn:.3f}",
        )
    else:
        add_check("candidate_postflop_call", "PASS", f"candidate mean call {fmt(candidate_call)}")

    if ra_delta is None:
        add_check("postflop_ra_delta", "WARN", "baseline or candidate RA unavailable")
    elif ra_delta <= args.ra_delta_good:
        add_check("postflop_ra_delta", "PASS", f"RA delta {ra_delta:+.3f} <= {args.ra_delta_good:+.3f}")
    elif ra_delta >= args.ra_delta_bad:
        add_check("postflop_ra_delta", "WARN", f"RA delta {ra_delta:+.3f} >= {args.ra_delta_bad:+.3f}")
    else:
        add_check("postflop_ra_delta", "PASS", f"RA delta {ra_delta:+.3f}")

    if call_delta is None:
        add_check("postflop_call_delta", "WARN", "baseline or candidate call unavailable")
    elif call_delta >= args.call_delta_good:
        add_check("postflop_call_delta", "PASS", f"call delta {call_delta:+.3f} >= {args.call_delta_good:+.3f}")
    elif call_delta <= args.call_delta_bad:
        add_check("postflop_call_delta", "WARN", f"call delta {call_delta:+.3f} <= {args.call_delta_bad:+.3f}")
    else:
        add_check("postflop_call_delta", "PASS", f"call delta {call_delta:+.3f}")

    if candidate["preflop_allin_max"] is not None and candidate["preflop_allin_max"] >= args.preflop_allin_fail:
        add_check(
            "candidate_preflop_allin",
            "FAIL",
            f"candidate max all-in {candidate['preflop_allin_max']:.3f} >= {args.preflop_allin_fail:.3f}",
        )
    elif candidate_pre_allin is not None and candidate_pre_allin >= args.preflop_allin_warn:
        add_check(
            "candidate_preflop_allin",
            "WARN",
            f"candidate mean all-in {candidate_pre_allin:.3f} >= {args.preflop_allin_warn:.3f}",
        )
    else:
        add_check("candidate_preflop_allin", "PASS", f"candidate mean all-in {fmt(candidate_pre_allin)}")

    if candidate["preflop_call_min"] is not None and candidate["preflop_call_min"] <= args.preflop_call_fail:
        add_check(
            "candidate_preflop_call",
            "FAIL",
            f"candidate min call {candidate['preflop_call_min']:.3f} <= {args.preflop_call_fail:.3f}",
        )
    elif candidate_pre_call is not None and candidate_pre_call <= args.preflop_call_warn:
        add_check(
            "candidate_preflop_call",
            "WARN",
            f"candidate mean call {candidate_pre_call:.3f} <= {args.preflop_call_warn:.3f}",
        )
    else:
        add_check("candidate_preflop_call", "PASS", f"candidate mean call {fmt(candidate_pre_call)}")

    if pre_allin_delta is None:
        add_check("preflop_allin_delta", "WARN", "baseline or candidate preflop all-in unavailable")
    elif pre_allin_delta <= args.preflop_allin_delta_good:
        add_check(
            "preflop_allin_delta",
            "PASS",
            f"preflop all-in delta {pre_allin_delta:+.3f} <= {args.preflop_allin_delta_good:+.3f}",
        )
    elif pre_allin_delta >= args.preflop_allin_delta_bad:
        add_check(
            "preflop_allin_delta",
            "WARN",
            f"preflop all-in delta {pre_allin_delta:+.3f} >= {args.preflop_allin_delta_bad:+.3f}",
        )
    else:
        add_check("preflop_allin_delta", "PASS", f"preflop all-in delta {pre_allin_delta:+.3f}")

    if pre_call_delta is None:
        add_check("preflop_call_delta", "WARN", "baseline or candidate preflop call unavailable")
    elif pre_call_delta >= args.preflop_call_delta_good:
        add_check(
            "preflop_call_delta",
            "PASS",
            f"preflop call delta {pre_call_delta:+.3f} >= {args.preflop_call_delta_good:+.3f}",
        )
    elif pre_call_delta <= args.preflop_call_delta_bad:
        add_check(
            "preflop_call_delta",
            "WARN",
            f"preflop call delta {pre_call_delta:+.3f} <= {args.preflop_call_delta_bad:+.3f}",
        )
    else:
        add_check("preflop_call_delta", "PASS", f"preflop call delta {pre_call_delta:+.3f}")

    if any(c["status"] == "FAIL" for c in checks):
        overall = "FAIL"
    elif any(c["status"] == "WARN" for c in checks):
        overall = "WARN"
    else:
        overall = "PASS"

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tail": args.tail,
        "baseline": baseline,
        "candidate": candidate,
        "comparison": {
            "postflop_raise_allin_delta": ra_delta,
            "postflop_call_delta": call_delta,
            "preflop_allin_delta": pre_allin_delta,
            "preflop_call_delta": pre_call_delta,
        },
        "checks": checks,
        "overall": overall,
        "scope": "training-log action-mix diagnostic only; not Slumbot strength evidence",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    baseline = summary["baseline"]
    candidate = summary["candidate"]
    comparison = summary["comparison"]
    lines = [
        "# V5 Action-Prior Trend",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Scope: {summary['scope']}",
        f"- Tail rows: `{summary['tail']}`",
        "",
        "Baseline:",
        "",
        f"- Run: `{baseline['run_dir']}`",
        f"- Iterations: `{baseline['first_iteration']}` -> `{baseline['latest_iteration']}`",
        f"- Postflop RA mean/max: `{fmt(baseline['postflop_raise_allin_mean'])}` / `{fmt(baseline['postflop_raise_allin_max'])}`",
        f"- Postflop call mean/min: `{fmt(baseline['postflop_call_mean'])}` / `{fmt(baseline['postflop_call_min'])}`",
        f"- Preflop all-in mean/max: `{fmt(baseline['preflop_allin_mean'])}` / `{fmt(baseline['preflop_allin_max'])}`",
        f"- Preflop call mean/min: `{fmt(baseline['preflop_call_mean'])}` / `{fmt(baseline['preflop_call_min'])}`",
        "",
        "Candidate:",
        "",
        f"- Run: `{candidate['run_dir']}`",
        f"- Iterations: `{candidate['first_iteration']}` -> `{candidate['latest_iteration']}`",
        f"- Health: `{candidate['health_overall']}`",
        f"- Postflop RA mean/max: `{fmt(candidate['postflop_raise_allin_mean'])}` / `{fmt(candidate['postflop_raise_allin_max'])}`",
        f"- Postflop call mean/min: `{fmt(candidate['postflop_call_mean'])}` / `{fmt(candidate['postflop_call_min'])}`",
        f"- Preflop all-in mean/max: `{fmt(candidate['preflop_allin_mean'])}` / `{fmt(candidate['preflop_allin_max'])}`",
        f"- Preflop call mean/min: `{fmt(candidate['preflop_call_mean'])}` / `{fmt(candidate['preflop_call_min'])}`",
        f"- Action-prior loss mean/latest: `{fmt(candidate['action_prior_loss_mean'])}` / `{fmt(candidate['action_prior_loss_latest'])}`",
        "",
        "Comparison:",
        "",
        f"- Postflop RA delta: `{fmt(comparison['postflop_raise_allin_delta'], 4)}`",
        f"- Postflop call delta: `{fmt(comparison['postflop_call_delta'], 4)}`",
        f"- Preflop all-in delta: `{fmt(comparison['preflop_allin_delta'], 4)}`",
        f"- Preflop call delta: `{fmt(comparison['preflop_call_delta'], 4)}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-run-dir", required=True)
    parser.add_argument("--candidate-run-dir", required=True)
    parser.add_argument("--tail", type=int, default=40)
    parser.add_argument("--min-candidate-rows", type=int, default=20)
    parser.add_argument("--postflop-ra-warn", type=float, default=0.72)
    parser.add_argument("--postflop-ra-fail", type=float, default=0.88)
    parser.add_argument("--postflop-call-warn", type=float, default=0.08)
    parser.add_argument("--postflop-call-fail", type=float, default=0.03)
    parser.add_argument("--ra-delta-good", type=float, default=-0.03)
    parser.add_argument("--ra-delta-bad", type=float, default=0.05)
    parser.add_argument("--call-delta-good", type=float, default=0.03)
    parser.add_argument("--call-delta-bad", type=float, default=-0.05)
    parser.add_argument("--preflop-allin-warn", type=float, default=0.12)
    parser.add_argument("--preflop-allin-fail", type=float, default=0.18)
    parser.add_argument("--preflop-call-warn", type=float, default=0.16)
    parser.add_argument("--preflop-call-fail", type=float, default=0.10)
    parser.add_argument("--preflop-allin-delta-good", type=float, default=-0.02)
    parser.add_argument("--preflop-allin-delta-bad", type=float, default=0.03)
    parser.add_argument("--preflop-call-delta-good", type=float, default=0.02)
    parser.add_argument("--preflop-call-delta-bad", type=float, default=-0.03)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_summary(args)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    print(f"overall={summary['overall']}")
    print(f"candidate_postflop_ra_mean={fmt(summary['candidate']['postflop_raise_allin_mean'])}")
    print(f"candidate_postflop_call_mean={fmt(summary['candidate']['postflop_call_mean'])}")
    print(f"postflop_ra_delta={fmt(summary['comparison']['postflop_raise_allin_delta'], 4)}")
    print(f"postflop_call_delta={fmt(summary['comparison']['postflop_call_delta'], 4)}")
    print(f"preflop_allin_delta={fmt(summary['comparison']['preflop_allin_delta'], 4)}")
    print(f"preflop_call_delta={fmt(summary['comparison']['preflop_call_delta'], 4)}")
    return 0 if summary["overall"] != "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main())
