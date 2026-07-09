#!/usr/bin/env python3
"""
Watch a sequence of V5 checkpoint/pool gates.

This is read-only with respect to training. It reuses v5_gate_watch's gate
evaluator, writes the normal per-gate status JSON/Markdown, appends PASS gates
to the launch report, then advances to the next target iteration.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_gate_watch import (  # noqa: E402
    append_report_if_pass,
    evaluate_gate,
    expected_stored_pool_snapshots,
    refresh_health_status,
    write_outputs,
)


def should_require_current_pool_snapshot(
    target_iteration: int,
    snapshot_every: int,
    enabled: bool,
    pool_strategy: str,
) -> bool:
    if str(pool_strategy or "").lower() == "loss-kbest":
        return False
    return enabled and snapshot_every > 0 and target_iteration % snapshot_every == 0


def run_gate(args: argparse.Namespace, target_iteration: int) -> str:
    run_dir = Path(args.run_dir)
    start = time.monotonic()
    expected_pool = expected_stored_pool_snapshots(
        target_iteration,
        args.snapshot_every,
        args.k_best,
    )
    if expected_pool is None:
        expected_pool = args.expected_pool_snapshots

    require_current = should_require_current_pool_snapshot(
        target_iteration,
        args.snapshot_every,
        args.require_current_pool_snapshot_on_snapshot_gates,
        args.expected_pool_strategy,
    )

    while True:
        health_refresh = None
        if args.refresh_health:
            health_refresh = refresh_health_status(run_dir, args.python)

        summary = evaluate_gate(
            run_dir=run_dir,
            target_iteration=target_iteration,
            expected_pool_snapshots=expected_pool,
            expected_env_version=args.expected_env_version,
            expected_obs_version=args.expected_obs_version,
            expected_action_space_version=args.expected_action_space_version,
            expected_stack_bb=args.expected_stack_bb,
            expected_opponent_assignment=args.expected_opponent_assignment,
            expected_pool_strategy=args.expected_pool_strategy,
            checkpoint_load_grace_seconds=args.checkpoint_load_grace_seconds,
            require_current_pool_snapshot=require_current,
        )
        if health_refresh is not None:
            summary["health_refresh"] = health_refresh
            if health_refresh.get("exit_code") != 0:
                summary["checks"].append(
                    {
                        "name": "health_refresh",
                        "status": "WARN",
                        "detail": f"v5_monitor.py exited {health_refresh.get('exit_code')}",
                    }
                )
                if summary["overall"] == "PASS":
                    summary["overall"] = "WARN"

        write_outputs(run_dir, target_iteration, summary)
        latest = summary.get("latest") or {}
        checkpoint = summary.get("checkpoint") or {}
        overall = str(summary.get("overall"))
        print(
            f"{overall}: gate={target_iteration} "
            f"live_iter={latest.get('iteration')} "
            f"ckpt_iter={checkpoint.get('iteration')} "
            f"pool_snapshots={checkpoint.get('pool_snapshots')} "
            f"require_current_pool_snapshot={require_current}",
            flush=True,
        )

        if overall == "PASS":
            if args.append_report:
                appended = append_report_if_pass(Path(args.append_report), target_iteration, summary)
                print(f"gate={target_iteration} report_appended={appended}", flush=True)
            return "PASS"
        if overall in {"FAIL", "WARN"}:
            return overall

        if args.timeout_seconds <= 0:
            return "PENDING"

        elapsed = time.monotonic() - start
        if elapsed >= args.timeout_seconds:
            return "PENDING"

        sleep_for = min(args.poll_seconds, args.timeout_seconds - elapsed)
        if sleep_for > 0:
            time.sleep(sleep_for)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--start-iteration", type=int, required=True)
    parser.add_argument("--max-iteration", type=int, default=0)
    parser.add_argument("--step", type=int, default=100)
    parser.add_argument("--snapshot-every", type=int, default=200)
    parser.add_argument("--k-best", type=int, default=5)
    parser.add_argument("--expected-pool-snapshots", type=int, default=5)
    parser.add_argument("--expected-env-version", default="v55")
    parser.add_argument("--expected-obs-version", default="v55")
    parser.add_argument("--expected-action-space-version", default="9slot_v5")
    parser.add_argument("--expected-stack-bb", type=float, default=200.0)
    parser.add_argument("--expected-opponent-assignment", default="")
    parser.add_argument("--expected-pool-strategy", default="")
    parser.add_argument("--require-current-pool-snapshot-on-snapshot-gates", action="store_true")
    parser.add_argument("--checkpoint-load-grace-seconds", type=float, default=300.0)
    parser.add_argument("--poll-seconds", type=float, default=60.0)
    parser.add_argument("--timeout-seconds", type=float, default=14400.0)
    parser.add_argument("--refresh-health", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--append-report", default="")
    args = parser.parse_args()

    target = args.start_iteration
    while True:
        if args.max_iteration > 0 and target > args.max_iteration:
            print(f"sequence complete: target {target} > max {args.max_iteration}", flush=True)
            return 0

        result = run_gate(args, target)
        if result == "PASS":
            target += args.step
            continue
        if result == "PENDING":
            return 2
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
