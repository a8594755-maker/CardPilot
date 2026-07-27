#!/usr/bin/env python3
"""
Wait for a V5 continuation run to produce enough training log rows, then run
the post-cutover throughput gate.

This watcher is read-only with respect to training. It never starts or stops a
trainer. It repeatedly writes the compare JSON/Markdown so the current status
is inspectable while the candidate run is warming up.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_throughput_compare import build_summary, write_markdown  # noqa: E402


def log(message: str, path: Path | None) -> None:
    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}"
    print(line, flush=True)
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")


def write_outputs(summary: dict, json_path: Path | None, md_path: Path | None) -> None:
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    if md_path is not None:
        md_path.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(md_path, summary)


def append_final_report(report_path: Path, summary: dict) -> None:
    baseline = summary["baseline"]
    candidate = summary["candidate"]
    ratios = summary["ratios"]

    def fmt(value: float | int | None, digits: int = 3) -> str:
        if value is None:
            return "`null`"
        if isinstance(value, float):
            return f"`{value:.{digits}f}`"
        return f"`{value}`"

    lines = [
        "",
        "## Post-Cutover Throughput Verification",
        "",
        f"- checked at: `{summary['checked_at']}`",
        f"- overall: **{summary['overall']}**",
        f"- baseline run: `{baseline['run_dir']}`",
        f"- candidate run: `{candidate['run_dir']}`",
        f"- baseline rows: `{baseline['window_rows']}`",
        f"- candidate rows: `{candidate['window_rows']}`",
        f"- baseline h/s mean: {fmt(baseline['hands_per_second_mean'], 1)}",
        f"- candidate h/s mean: {fmt(candidate['hands_per_second_mean'], 1)}",
        f"- h/s ratio: {fmt(ratios['hands_per_second'])}",
        f"- baseline inf_bs mean: {fmt(baseline['inference_batch_size_mean'])}",
        f"- candidate inf_bs mean: {fmt(candidate['inference_batch_size_mean'])}",
        f"- inf_bs ratio: {fmt(ratios['inference_batch_size'])}",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['name']}: **{check['status']}** - {check['detail']}")
    lines.extend(
        [
            "",
            "This is a throughput-only verification. It does not support a Slumbot, L5, or L6 claim.",
            "",
        ]
    )
    with report_path.open("a", encoding="utf-8") as f:
        f.write("\n".join(lines))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--baseline-run-dir", required=True)
    parser.add_argument("--candidate-run-dir", required=True)
    parser.add_argument("--tail", type=int, default=20)
    parser.add_argument("--min-baseline-rows", type=int, default=10)
    parser.add_argument("--min-candidate-rows", type=int, default=10)
    parser.add_argument("--min-hps-ratio", type=float, default=1.25)
    parser.add_argument("--min-inf-bs-ratio", type=float, default=1.8)
    parser.add_argument("--min-candidate-inf-bs", type=float, default=8.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=7200.0)
    parser.add_argument("--out-json")
    parser.add_argument("--out-md")
    parser.add_argument("--log-path")
    parser.add_argument("--append-report")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    json_path = Path(args.out_json) if args.out_json else None
    md_path = Path(args.out_md) if args.out_md else None
    log_path = Path(args.log_path) if args.log_path else None
    report_path = Path(args.append_report) if args.append_report else None

    log(
        "throughput watcher started "
        f"baseline={args.baseline_run_dir} candidate={args.candidate_run_dir}",
        log_path,
    )
    start = time.time()
    appended = False

    while True:
        summary = build_summary(args)
        write_outputs(summary, json_path, md_path)
        cand_rows = summary["candidate"]["window_rows"]
        hps_ratio = summary["ratios"]["hands_per_second"]
        inf_bs_ratio = summary["ratios"]["inference_batch_size"]
        log(
            f"{summary['overall']}: candidate_rows={cand_rows} "
            f"hps_ratio={hps_ratio} inf_bs_ratio={inf_bs_ratio}",
            log_path,
        )

        if summary["overall"] in {"PASS", "FAIL"}:
            if report_path is not None and not appended:
                append_final_report(report_path, summary)
                appended = True
            return 0 if summary["overall"] == "PASS" else 1

        if args.timeout_seconds > 0 and (time.time() - start) >= args.timeout_seconds:
            summary = dict(summary)
            summary["overall"] = "PENDING"
            summary["timed_out_at"] = datetime.now(timezone.utc).isoformat()
            write_outputs(summary, json_path, md_path)
            if report_path is not None and not appended:
                append_final_report(report_path, summary)
            log(f"timeout after {args.timeout_seconds:.1f}s", log_path)
            return 2

        time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
