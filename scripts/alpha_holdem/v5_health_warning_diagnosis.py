#!/usr/bin/env python3
"""Diagnose V5 health WARN causes over a rolling window.

The main health watcher is intentionally sensitive to the latest log line.
This report adds hysteresis: it distinguishes a one-iteration spike from a
rolling-window leak that should be handled at the next controlled checkpoint.
It is read-only and never changes training.
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

from v5_monitor import parse_log
from v5_run_dashboard import format_duration


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def fraction(values: list[bool]) -> float | None:
    return statistics.fmean([1.0 if value else 0.0 for value in values]) if values else None


def fmt(value: Any, digits: int = 3) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def add_check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def status_rank(status: str) -> int:
    return {"PASS": 0, "WATCH": 1, "WARN": 2, "FAIL": 3}.get(status, 1)


def build_diagnosis(run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    rows = parse_log(run_dir / "latest_train.log")
    selected = rows[-args.tail :] if args.tail > 0 else rows
    long_selected = rows[-args.long_tail :] if args.long_tail > 0 else rows
    latest = rows[-1] if rows else {}
    health = load_json(run_dir / "health_status.json")
    progress = load_json(run_dir / "progress_status.json")

    checks: list[dict[str, Any]] = []
    if not rows:
        add_check(checks, "rows", "FAIL", "no parsed training rows")
    elif len(selected) < args.min_rows:
        add_check(checks, "rows", "WARN", f"rows {len(selected)} < min {args.min_rows}")
    else:
        add_check(checks, "rows", "PASS", f"rows {len(selected)} >= min {args.min_rows}")

    latest_health = health.get("overall")
    add_check(checks, "latest_health", "PASS" if latest_health == "PASS" else "WATCH", f"health={latest_health}")

    preflop = [row["preflop_action_mix"] for row in selected if row.get("preflop_action_mix") is not None]
    long_preflop = [
        row["preflop_action_mix"] for row in long_selected if row.get("preflop_action_mix") is not None
    ]
    postflop = [row["postflop_action_mix"] for row in selected if row.get("postflop_action_mix") is not None]
    entropies = [float(row["entropy"]) for row in selected if row.get("entropy") is not None]
    value_losses = [float(row["value_loss"]) for row in selected if row.get("value_loss") is not None]

    pre_allin = [m["allin"] for m in preflop]
    pre_call = [m["call"] for m in preflop]
    pre_raise = [m["raise"] for m in preflop]
    pre_fold = [m["fold"] for m in preflop]
    long_pre_allin = [m["allin"] for m in long_preflop]
    post_ra = [m["raise"] + m["allin"] for m in postflop]
    post_call = [m["call"] for m in postflop]

    pre_allin_mean = mean(pre_allin)
    pre_allin_max = max(pre_allin) if pre_allin else None
    pre_allin_last = pre_allin[-1] if pre_allin else None
    pre_allin_warn_fraction = fraction([value >= args.preflop_allin_warn for value in pre_allin])
    long_pre_allin_mean = mean(long_pre_allin)

    if pre_allin_mean is None:
        add_check(checks, "preflop_allin", "WARN", "preflop mix missing")
    elif pre_allin_max is not None and pre_allin_max >= args.preflop_allin_fail:
        add_check(
            checks,
            "preflop_allin",
            "FAIL",
            f"max {pre_allin_max:.3f} >= fail {args.preflop_allin_fail:.3f}",
        )
    elif pre_allin_mean >= args.preflop_allin_fail_mean:
        add_check(
            checks,
            "preflop_allin",
            "FAIL",
            f"mean {pre_allin_mean:.3f} >= fail_mean {args.preflop_allin_fail_mean:.3f}",
        )
    elif (
        pre_allin_mean >= args.preflop_allin_warn
        and (pre_allin_warn_fraction or 0.0) >= args.sustained_warn_fraction
    ):
        add_check(
            checks,
            "preflop_allin",
            "WARN",
            f"sustained high all-in: latest {pre_allin_last:.3f}, mean {pre_allin_mean:.3f}, warn_frac {pre_allin_warn_fraction:.2f}",
        )
    elif pre_allin_last is not None and pre_allin_last >= args.preflop_allin_warn:
        add_check(
            checks,
            "preflop_allin",
            "WATCH",
            f"latest spike {pre_allin_last:.3f}, mean {pre_allin_mean:.3f}, warn_frac {pre_allin_warn_fraction:.2f}",
        )
    else:
        add_check(
            checks,
            "preflop_allin",
            "PASS",
            f"latest {pre_allin_last:.3f}, mean {pre_allin_mean:.3f}, max {pre_allin_max:.3f}",
        )

    pre_call_mean = mean(pre_call)
    pre_call_min = min(pre_call) if pre_call else None
    if pre_call_mean is None:
        add_check(checks, "preflop_call", "WARN", "preflop call mix missing")
    elif pre_call_min is not None and pre_call_min <= args.preflop_call_fail:
        add_check(checks, "preflop_call", "FAIL", f"min {pre_call_min:.3f} <= fail {args.preflop_call_fail:.3f}")
    elif pre_call_mean <= args.preflop_call_warn:
        add_check(checks, "preflop_call", "WARN", f"mean {pre_call_mean:.3f} <= warn {args.preflop_call_warn:.3f}")
    else:
        add_check(checks, "preflop_call", "PASS", f"mean {pre_call_mean:.3f}, min {fmt(pre_call_min)}")

    post_ra_mean = mean(post_ra)
    post_ra_max = max(post_ra) if post_ra else None
    post_call_mean = mean(post_call)
    post_call_min = min(post_call) if post_call else None
    if post_ra_mean is None:
        add_check(checks, "postflop_action_mix", "WARN", "postflop mix missing")
    elif post_ra_mean >= args.postflop_ra_fail_mean or (post_ra_max or 0.0) >= args.postflop_ra_fail:
        add_check(
            checks,
            "postflop_action_mix",
            "FAIL",
            f"RA mean {post_ra_mean:.3f}, max {fmt(post_ra_max)}",
        )
    elif post_ra_mean >= args.postflop_ra_warn or (post_call_mean is not None and post_call_mean <= args.postflop_call_warn):
        add_check(
            checks,
            "postflop_action_mix",
            "WARN",
            f"RA mean {post_ra_mean:.3f}, call mean {fmt(post_call_mean)}, min call {fmt(post_call_min)}",
        )
    else:
        add_check(
            checks,
            "postflop_action_mix",
            "PASS",
            f"RA mean {post_ra_mean:.3f}, max {fmt(post_ra_max)}, call mean {fmt(post_call_mean)}",
        )

    entropy_mean = mean(entropies)
    entropy_min = min(entropies) if entropies else None
    value_loss_mean = mean(value_losses)
    value_loss_max = max(value_losses) if value_losses else None
    if entropy_min is not None and entropy_min < args.entropy_fail:
        add_check(checks, "entropy_window", "FAIL", f"min entropy {entropy_min:.3f}")
    elif entropy_min is not None and entropy_min < args.entropy_warn:
        add_check(checks, "entropy_window", "WARN", f"min entropy {entropy_min:.3f}")
    else:
        add_check(checks, "entropy_window", "PASS", f"mean {fmt(entropy_mean)}, min {fmt(entropy_min)}")

    if value_loss_max is not None and value_loss_max > args.value_loss_fail:
        add_check(checks, "value_loss_window", "FAIL", f"max value_loss {value_loss_max:.1f}")
    else:
        add_check(checks, "value_loss_window", "PASS", f"mean {fmt(value_loss_mean, 1)}, max {fmt(value_loss_max, 1)}")

    worst = max((status_rank(check["status"]) for check in checks), default=1)
    preflop_allin_check = next((check for check in checks if check["name"] == "preflop_allin"), {})
    if worst >= status_rank("FAIL"):
        overall = "FAIL_COLLAPSE_RISK"
    elif preflop_allin_check.get("status") == "WARN":
        overall = "PREFLOP_ALLIN_SUSTAINED_WARN"
    elif latest_health == "WARN" or worst >= status_rank("WARN"):
        overall = "HEALTH_WARN_TRANSIENT_OR_LOCAL"
    elif worst >= status_rank("WATCH"):
        overall = "WATCH"
    else:
        overall = "PASS"

    checkpoint_iteration = int((progress.get("checkpoint") or {}).get("iteration") or 0)
    live_iteration = int(latest.get("iteration") or 0)
    if overall == "FAIL_COLLAPSE_RISK":
        recommendation = "Stop promotion decisions and inspect the policy before continuing."
    elif overall == "PREFLOP_ALLIN_SUSTAINED_WARN":
        if checkpoint_iteration >= args.intervention_target_iteration:
            recommendation = "Review the preflop intervention plan before any restart or promotion."
        else:
            recommendation = "Keep training to the next gate; carry this warning into the 4400 intervention review."
    elif latest_health == "WARN":
        recommendation = "Continue training, but keep the health warning visible until the rolling window clears."
    else:
        recommendation = "No health-warning intervention is due."

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "overall": overall,
        "recommendation": recommendation,
        "window": {
            "tail": args.tail,
            "long_tail": args.long_tail,
            "rows_total": len(rows),
            "rows_used": len(selected),
            "first_iteration": selected[0]["iteration"] if selected else None,
            "latest_iteration": live_iteration,
            "checkpoint_iteration": checkpoint_iteration,
            "latest_hands": latest.get("hands"),
        },
        "metrics": {
            "preflop_allin_latest": pre_allin_last,
            "preflop_allin_mean": pre_allin_mean,
            "preflop_allin_max": pre_allin_max,
            "preflop_allin_warn_fraction": pre_allin_warn_fraction,
            "preflop_allin_long_mean": long_pre_allin_mean,
            "preflop_call_mean": pre_call_mean,
            "preflop_call_min": pre_call_min,
            "preflop_raise_mean": mean(pre_raise),
            "preflop_fold_mean": mean(pre_fold),
            "postflop_ra_mean": post_ra_mean,
            "postflop_ra_max": post_ra_max,
            "postflop_call_mean": post_call_mean,
            "postflop_call_min": post_call_min,
            "entropy_mean": entropy_mean,
            "entropy_min": entropy_min,
            "value_loss_mean": value_loss_mean,
            "value_loss_max": value_loss_max,
        },
        "health_overall": latest_health,
        "checks": checks,
        "claim_note": "Health diagnostics are training-quality evidence only; they do not prove Slumbot strength.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    window = summary["window"]
    metrics = summary["metrics"]
    lines = [
        "# V5 Health Warning Diagnosis",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Health overall: `{summary['health_overall']}`",
        f"- Window iterations: `{window['first_iteration']}` to `{window['latest_iteration']}` over `{window['rows_used']}` rows",
        f"- Checkpoint iteration: `{window['checkpoint_iteration']}`",
        "",
        "Key metrics:",
        "",
        f"- Preflop all-in latest / mean / max / warn fraction: `{fmt(metrics['preflop_allin_latest'])}` / `{fmt(metrics['preflop_allin_mean'])}` / `{fmt(metrics['preflop_allin_max'])}` / `{fmt(metrics['preflop_allin_warn_fraction'])}`",
        f"- Preflop call mean / min: `{fmt(metrics['preflop_call_mean'])}` / `{fmt(metrics['preflop_call_min'])}`",
        f"- Preflop fold / raise mean: `{fmt(metrics['preflop_fold_mean'])}` / `{fmt(metrics['preflop_raise_mean'])}`",
        f"- Postflop RA mean / max: `{fmt(metrics['postflop_ra_mean'])}` / `{fmt(metrics['postflop_ra_max'])}`",
        f"- Postflop call mean / min: `{fmt(metrics['postflop_call_mean'])}` / `{fmt(metrics['postflop_call_min'])}`",
        f"- Entropy mean / min: `{fmt(metrics['entropy_mean'])}` / `{fmt(metrics['entropy_min'])}`",
        f"- Value loss mean / max: `{fmt(metrics['value_loss_mean'], 1)}` / `{fmt(metrics['value_loss_max'], 1)}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.extend(["", "Claim note:", "", f"- {summary['claim_note']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose rolling V5 health WARN causes.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--tail", type=int, default=20)
    parser.add_argument("--long-tail", type=int, default=60)
    parser.add_argument("--min-rows", type=int, default=10)
    parser.add_argument("--preflop-allin-warn", type=float, default=0.12)
    parser.add_argument("--preflop-allin-fail", type=float, default=0.25)
    parser.add_argument("--preflop-allin-fail-mean", type=float, default=0.20)
    parser.add_argument("--sustained-warn-fraction", type=float, default=0.50)
    parser.add_argument("--preflop-call-warn", type=float, default=0.08)
    parser.add_argument("--preflop-call-fail", type=float, default=0.03)
    parser.add_argument("--postflop-ra-warn", type=float, default=0.72)
    parser.add_argument("--postflop-ra-fail", type=float, default=0.88)
    parser.add_argument("--postflop-ra-fail-mean", type=float, default=0.78)
    parser.add_argument("--postflop-call-warn", type=float, default=0.08)
    parser.add_argument("--entropy-warn", type=float, default=0.30)
    parser.add_argument("--entropy-fail", type=float, default=0.10)
    parser.add_argument("--value-loss-fail", type=float, default=50000.0)
    parser.add_argument("--intervention-target-iteration", type=int, default=4400)
    args = parser.parse_args()

    summary = build_diagnosis(Path(args.run_dir), args)
    print(f"overall={summary['overall']}")
    print(f"recommendation={summary['recommendation']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
