#!/usr/bin/env python3
"""Watch until a V5 checkpoint is ready for a planned Slumbot benchmark.

This is read-only. It never calls Slumbot and never starts the benchmark. It
periodically refreshes the benchmark plan JSON/Markdown and exits when the plan
is READY or READY_WITH_WARNINGS.
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

from v5_slumbot_benchmark_plan import evaluate, write_markdown  # noqa: E402


RECOVERABLE_FAILS = {
    "checkpoint_load",
    "version",
    "env_version",
    "obs_version",
    "action_space_version",
    "starting_stack_bb",
    "actual_hand_accounting",
    "fresh_from_zero_lineage",
    "training_hands",
    "quality_gate",
}


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


def failing_check_names(summary: dict) -> set[str]:
    return {
        str(check.get("name"))
        for check in summary.get("checks", [])
        if check.get("status") == "FAIL"
    }


def checkpoint_hands(summary: dict) -> int:
    checkpoint = summary.get("checkpoint")
    if not isinstance(checkpoint, dict):
        return 0
    try:
        return int(checkpoint.get("total_hands") or 0)
    except Exception:
        return 0


def build_plan_args(args: argparse.Namespace) -> argparse.Namespace:
    return argparse.Namespace(
        run_dir=args.run_dir,
        checkpoint=args.checkpoint,
        stage=args.stage,
        tag=args.tag,
        output_dir=args.output_dir,
        sessions=args.sessions,
        hands_per_session=args.hands_per_session,
        min_training_hands=args.min_training_hands,
        allow_early=args.allow_early,
        allow_existing_output=args.allow_existing_output,
        promotion_gate_json=args.promotion_gate_json,
        no_require_promotion20k=args.no_require_promotion20k,
        no_require_quality_gate=args.no_require_quality_gate,
        max_health_age_seconds=args.max_health_age_seconds,
        no_health_age_check=args.no_health_age_check,
        out_json="",
        out_md="",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="")
    parser.add_argument("--stage", choices=["quick5k", "promotion20k", "formal100k"], default="promotion20k")
    parser.add_argument("--tag", default="")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--sessions", type=int, default=0)
    parser.add_argument("--hands-per-session", type=int, default=0)
    parser.add_argument("--min-training-hands", type=int, default=None)
    parser.add_argument("--allow-early", action="store_true")
    parser.add_argument("--allow-existing-output", action="store_true")
    parser.add_argument("--promotion-gate-json", default="")
    parser.add_argument("--no-require-promotion20k", action="store_true")
    parser.add_argument("--no-require-quality-gate", action="store_true")
    parser.add_argument("--max-health-age-seconds", type=int, default=900)
    parser.add_argument("--no-health-age-check", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=1800.0)
    parser.add_argument("--timeout-seconds", type=float, default=0.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--log-path", default="")
    args = parser.parse_args()

    json_path = Path(args.out_json) if args.out_json else None
    md_path = Path(args.out_md) if args.out_md else None
    log_path = Path(args.log_path) if args.log_path else None
    plan_args = build_plan_args(args)

    log(f"slumbot plan watcher started run_dir={args.run_dir} stage={args.stage}", log_path)
    start = time.monotonic()

    while True:
        summary = evaluate(plan_args)
        write_outputs(summary, json_path, md_path)

        overall = str(summary.get("overall"))
        fails = failing_check_names(summary)
        hands = checkpoint_hands(summary)
        min_hands = int(summary.get("min_training_hands") or 0)
        log(
            f"{overall}: stage={args.stage} checkpoint_hands={hands:,} "
            f"min_training_hands={min_hands:,} failing={sorted(fails)}",
            log_path,
        )

        if overall in {"READY", "READY_WITH_WARNINGS"}:
            return 0

        hard_fails = fails - RECOVERABLE_FAILS
        if hard_fails:
            log(f"hard failure(s), exiting: {sorted(hard_fails)}", log_path)
            return 1

        if args.timeout_seconds > 0 and (time.monotonic() - start) >= args.timeout_seconds:
            summary = dict(summary)
            summary["timed_out_at"] = datetime.now(timezone.utc).isoformat()
            write_outputs(summary, json_path, md_path)
            log(f"timeout after {args.timeout_seconds:.1f}s", log_path)
            return 2

        time.sleep(max(args.poll_seconds, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
