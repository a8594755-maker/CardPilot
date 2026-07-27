#!/usr/bin/env python3
"""
Compare V5 training throughput before and after a controlled continuation.

This is read-only. It parses latest_train.log through v5_monitor.parse_log and
emits a small gate summary for the batching cutover. The gate is intentionally
about engineering throughput only; it does not promote checkpoints or claim any
Slumbot milestone.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_monitor import parse_log  # noqa: E402


def mean(values: list[float]) -> float | None:
    return statistics.fmean(values) if values else None


def summarize(run_dir: Path, tail: int) -> dict:
    rows = parse_log(run_dir / "latest_train.log")
    recent = rows[-tail:] if tail > 0 else rows
    return {
        "run_dir": str(run_dir),
        "log_path": str(run_dir / "latest_train.log"),
        "parsed_rows": len(rows),
        "window_rows": len(recent),
        "first_iteration": recent[0]["iteration"] if recent else None,
        "latest_iteration": recent[-1]["iteration"] if recent else None,
        "first_hands": recent[0]["hands"] if recent else None,
        "latest_hands": recent[-1]["hands"] if recent else None,
        "hands_per_second_mean": mean([float(r["hands_per_second"]) for r in recent]),
        "trainable_decisions_per_second_mean": mean(
            [float(r["trainable_decisions_per_second"]) for r in recent]
        ),
        "inference_batch_size_mean": mean([float(r["inference_batch_size"]) for r in recent]),
        "collect_seconds_mean": mean([float(r["collect_seconds"]) for r in recent]),
        "ppo_seconds_mean": mean([float(r["ppo_seconds"]) for r in recent]),
        "latest": recent[-1] if recent else None,
    }


def ratio(num: float | None, den: float | None) -> float | None:
    if num is None or den is None or den == 0:
        return None
    return num / den


def add_check(checks: list[dict], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def build_summary(args: argparse.Namespace) -> dict:
    baseline = summarize(Path(args.baseline_run_dir), args.tail)
    candidate = summarize(Path(args.candidate_run_dir), args.tail)
    checks: list[dict] = []

    if baseline["window_rows"] < args.min_baseline_rows:
        add_check(
            checks,
            "baseline_rows",
            "PENDING",
            f"baseline rows {baseline['window_rows']} < {args.min_baseline_rows}",
        )
    else:
        add_check(
            checks,
            "baseline_rows",
            "PASS",
            f"baseline rows {baseline['window_rows']} >= {args.min_baseline_rows}",
        )

    if candidate["window_rows"] < args.min_candidate_rows:
        add_check(
            checks,
            "candidate_rows",
            "PENDING",
            f"candidate rows {candidate['window_rows']} < {args.min_candidate_rows}",
        )
    else:
        add_check(
            checks,
            "candidate_rows",
            "PASS",
            f"candidate rows {candidate['window_rows']} >= {args.min_candidate_rows}",
        )

    rows_ready = (
        baseline["window_rows"] >= args.min_baseline_rows
        and candidate["window_rows"] >= args.min_candidate_rows
    )

    hps_ratio = ratio(
        candidate["hands_per_second_mean"],
        baseline["hands_per_second_mean"],
    )
    inf_bs_ratio = ratio(
        candidate["inference_batch_size_mean"],
        baseline["inference_batch_size_mean"],
    )
    collect_ratio = ratio(
        baseline["collect_seconds_mean"],
        candidate["collect_seconds_mean"],
    )

    if not rows_ready:
        add_check(checks, "hps_ratio", "PENDING", "waiting for row-count gates")
    elif hps_ratio is None:
        add_check(checks, "hps_ratio", "PENDING", "cannot compute hps ratio")
    elif hps_ratio >= args.min_hps_ratio:
        add_check(
            checks,
            "hps_ratio",
            "PASS",
            f"hps ratio {hps_ratio:.3f} >= {args.min_hps_ratio:.3f}",
        )
    else:
        add_check(
            checks,
            "hps_ratio",
            "FAIL",
            f"hps ratio {hps_ratio:.3f} < {args.min_hps_ratio:.3f}",
        )

    cand_inf = candidate["inference_batch_size_mean"]
    if not rows_ready:
        add_check(checks, "candidate_inf_bs", "PENDING", "waiting for row-count gates")
    elif cand_inf is None:
        add_check(checks, "candidate_inf_bs", "PENDING", "cannot compute candidate inf_bs")
    elif cand_inf >= args.min_candidate_inf_bs:
        add_check(
            checks,
            "candidate_inf_bs",
            "PASS",
            f"candidate inf_bs {cand_inf:.3f} >= {args.min_candidate_inf_bs:.3f}",
        )
    else:
        add_check(
            checks,
            "candidate_inf_bs",
            "FAIL",
            f"candidate inf_bs {cand_inf:.3f} < {args.min_candidate_inf_bs:.3f}",
        )

    if not rows_ready:
        add_check(checks, "inf_bs_ratio", "PENDING", "waiting for row-count gates")
    elif inf_bs_ratio is None:
        add_check(checks, "inf_bs_ratio", "PENDING", "cannot compute inf_bs ratio")
    elif inf_bs_ratio >= args.min_inf_bs_ratio:
        add_check(
            checks,
            "inf_bs_ratio",
            "PASS",
            f"inf_bs ratio {inf_bs_ratio:.3f} >= {args.min_inf_bs_ratio:.3f}",
        )
    else:
        add_check(
            checks,
            "inf_bs_ratio",
            "FAIL",
            f"inf_bs ratio {inf_bs_ratio:.3f} < {args.min_inf_bs_ratio:.3f}",
        )

    statuses = {c["status"] for c in checks}
    if "PENDING" in statuses:
        overall = "PENDING"
    elif "FAIL" in statuses:
        overall = "FAIL"
    else:
        overall = "PASS"

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "baseline": baseline,
        "candidate": candidate,
        "ratios": {
            "hands_per_second": hps_ratio,
            "inference_batch_size": inf_bs_ratio,
            "collect_speedup": collect_ratio,
        },
        "thresholds": {
            "tail": args.tail,
            "min_baseline_rows": args.min_baseline_rows,
            "min_candidate_rows": args.min_candidate_rows,
            "min_hps_ratio": args.min_hps_ratio,
            "min_inf_bs_ratio": args.min_inf_bs_ratio,
            "min_candidate_inf_bs": args.min_candidate_inf_bs,
        },
        "checks": checks,
        "note": (
            "Throughput gate only. PASS does not imply stronger poker play, "
            "Slumbot promotion, L5, or L6."
        ),
    }


def write_markdown(path: Path, summary: dict) -> None:
    def fmt(value: float | int | None, digits: int = 3) -> str:
        if value is None:
            return "`null`"
        if isinstance(value, float):
            return f"`{value:.{digits}f}`"
        return f"`{value}`"

    baseline = summary["baseline"]
    candidate = summary["candidate"]
    ratios = summary["ratios"]
    lines = [
        "# V5 Throughput Compare",
        "",
        f"- Overall: **{summary['overall']}**",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Baseline: `{baseline['run_dir']}`",
        f"- Candidate: `{candidate['run_dir']}`",
        "",
        "## Window",
        "",
        f"- Baseline rows: `{baseline['window_rows']}`",
        f"- Baseline iterations: `{baseline['first_iteration']}` to `{baseline['latest_iteration']}`",
        f"- Candidate rows: `{candidate['window_rows']}`",
        f"- Candidate iterations: `{candidate['first_iteration']}` to `{candidate['latest_iteration']}`",
        "",
        "## Metrics",
        "",
        f"- Baseline h/s mean: {fmt(baseline['hands_per_second_mean'], 1)}",
        f"- Candidate h/s mean: {fmt(candidate['hands_per_second_mean'], 1)}",
        f"- H/s ratio: {fmt(ratios['hands_per_second'])}",
        f"- Baseline inf_bs mean: {fmt(baseline['inference_batch_size_mean'])}",
        f"- Candidate inf_bs mean: {fmt(candidate['inference_batch_size_mean'])}",
        f"- inf_bs ratio: {fmt(ratios['inference_batch_size'])}",
        f"- Collect speedup ratio: {fmt(ratios['collect_speedup'])}",
        "",
        "## Checks",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['name']}: **{check['status']}** - {check['detail']}")
    lines.extend(["", summary["note"], ""])
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-run-dir", required=True)
    parser.add_argument("--candidate-run-dir", required=True)
    parser.add_argument("--tail", type=int, default=20)
    parser.add_argument("--min-baseline-rows", type=int, default=10)
    parser.add_argument("--min-candidate-rows", type=int, default=10)
    parser.add_argument("--min-hps-ratio", type=float, default=1.25)
    parser.add_argument("--min-inf-bs-ratio", type=float, default=1.8)
    parser.add_argument("--min-candidate-inf-bs", type=float, default=8.0)
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    args = parser.parse_args()

    summary = build_summary(args)
    if args.out_json:
        Path(args.out_json).write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if args.out_md:
        write_markdown(Path(args.out_md), summary)

    print(
        f"{summary['overall']}: "
        f"hps_ratio={summary['ratios']['hands_per_second']} "
        f"inf_bs_ratio={summary['ratios']['inference_batch_size']} "
        f"candidate_inf_bs={summary['candidate']['inference_batch_size_mean']}"
    )
    if summary["overall"] == "PASS":
        return 0
    if summary["overall"] == "PENDING":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
