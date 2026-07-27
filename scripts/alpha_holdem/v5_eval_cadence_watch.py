#!/usr/bin/env python3
"""Watch the V5 evaluation cadence and launch due external benchmarks.

This complements the fixed first-stage watchers:
- the dedicated quick5k watcher is the preferred path for the first 50M screen,
  but this watcher can backstop it when that launcher is intentionally skipped;
- the existing promotion20k/formal100k watchers cover the first 250M screen.

Use this watcher for quick cadence points from 50M onward and for 500M+
promotion/formal screens. It never launches from cadence alone: the
benchmark planner must return clean READY for the exact stage/target/tag.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_eval_cadence import build_cadence
from v5_slumbot_benchmark_plan import evaluate as evaluate_benchmark_plan
from v5_slumbot_benchmark_plan import write_markdown as write_benchmark_plan_markdown


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def exp003_bundle_mutex_status(run_dir: Path) -> dict[str, Any]:
    lock_path = run_dir / "v5_exp003_bundle_watch.lock"
    status_path = run_dir / "v5_exp003_bundle_watch_status.json"
    status = load_json(status_path)
    running = str(status.get("overall") or "").upper() == "RUNNING"
    return {
        "busy": lock_path.exists() or running,
        "lock_path": str(lock_path),
        "lock_exists": lock_path.exists(),
        "status_path": str(status_path),
        "bundle_overall": status.get("overall"),
        "bundle_state": status.get("state"),
    }


def target_m(target_hands: int) -> int:
    return int(target_hands) // 1_000_000


def schedule_key(stage: str, target_hands: int) -> str:
    return f"{stage}_{target_m(target_hands)}M"


def file_age_seconds(path: Path) -> float | None:
    try:
        return time.time() - path.stat().st_mtime
    except OSError:
        return None


def launch_status_stage_target(data: dict[str, Any]) -> tuple[str, int] | None:
    plan = data.get("plan") if isinstance(data.get("plan"), dict) else {}
    stage = str(plan.get("stage") or data.get("stage") or "")
    if not stage:
        return None
    target = plan.get("min_training_hands") or data.get("target_hands")
    try:
        target_hands = int(target or 0)
    except (TypeError, ValueError):
        target_hands = 0
    if target_hands <= 0:
        return None
    return stage, target_hands


def active_launch_for(
    run_dir: Path,
    *,
    stage: str,
    target_hands: int,
    max_age_seconds: float,
) -> dict[str, Any] | None:
    for path in sorted(run_dir.glob("slumbot_*status.json")):
        data = load_json(path)
        status_stage_target = launch_status_stage_target(data)
        if status_stage_target != (stage, target_hands):
            continue
        state = str(data.get("state") or "").upper()
        if state != "RUNNING":
            continue
        age = file_age_seconds(path)
        if age is not None and age > max_age_seconds:
            continue
        return {
            "path": str(path),
            "state": state,
            "age_seconds": age,
        }
    return None


def stage_targets(cadence: dict[str, Any], args: argparse.Namespace) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for item in cadence.get("slumbot_quick_screens") or []:
        if int(item.get("target_hands") or 0) >= args.min_quick_target_hands:
            items.append(item)
    for item in cadence.get("slumbot_promotion_screens") or []:
        if int(item.get("target_hands") or 0) >= args.min_promotion_target_hands:
            items.append(item)
    for item in cadence.get("slumbot_formal_screens") or []:
        if int(item.get("target_hands") or 0) >= args.min_formal_target_hands:
            items.append(item)
    priority = {"quick5k": 0, "promotion20k": 1, "formal100k": 2}
    return sorted(items, key=lambda item: (int(item.get("target_hands") or 0), priority.get(str(item.get("stage")), 99)))


def benchmark_plan_args(
    args: argparse.Namespace,
    stage: str,
    target_hands: int,
    tag: str,
    *,
    checkpoint: str = "",
    promotion_gate_json: str = "",
) -> argparse.Namespace:
    return argparse.Namespace(
        run_dir=args.run_dir,
        checkpoint=checkpoint,
        stage=stage,
        tag=tag,
        output_dir=args.output_dir,
        sessions=0,
        hands_per_session=0,
        min_training_hands=target_hands,
        allow_early=False,
        allow_existing_output=False,
        promotion_gate_json=promotion_gate_json,
        no_require_promotion20k=False,
        no_require_quality_gate=False,
        max_health_age_seconds=args.max_health_age_seconds,
        no_health_age_check=False,
    )


def clean_tag(run_id: str, stage: str, target_hands: int) -> str:
    return f"v5_{run_id}_{target_m(target_hands)}M_{stage}_cadence"


def runnable_plan(args: argparse.Namespace, item: dict[str, Any], tag: str, run_id: str) -> dict[str, Any]:
    stage = str(item.get("stage"))
    target_hands = int(item.get("target_hands") or 0)
    checkpoint = ""
    promotion_gate_json = ""
    if stage == "formal100k":
        promotion_tag = clean_tag(run_id, "promotion20k", target_hands)
        gate_path = Path(args.output_dir) / f"bench_v55_{promotion_tag}_promotion_gate.json"
        promotion_gate_json = str(gate_path)
        gate = load_json(gate_path)
        if not gate.get("_missing") and not gate.get("_load_error"):
            checkpoint = str(gate.get("checkpoint_path") or "")
    return evaluate_benchmark_plan(
        benchmark_plan_args(
            args,
            stage,
            target_hands,
            tag,
            checkpoint=checkpoint,
            promotion_gate_json=promotion_gate_json,
        )
    )


def plan_preview_paths(run_dir: Path, stage: str, target_hands: int) -> tuple[Path, Path]:
    stem = f"slumbot_cadence_{stage}_{target_m(target_hands)}M_plan_preview"
    return run_dir / f"{stem}.json", run_dir / f"{stem}.md"


def failed_check_names(summary: dict[str, Any]) -> list[str]:
    checks = summary.get("checks") if isinstance(summary.get("checks"), list) else []
    return [
        str(check.get("name"))
        for check in checks
        if isinstance(check, dict) and check.get("status") == "FAIL" and check.get("name")
    ]


def summarize_plan_preview(
    *,
    key: str | None,
    tag: str,
    out_json: Path,
    out_md: Path,
    summary: dict[str, Any],
) -> dict[str, Any]:
    return {
        "status": "WRITTEN",
        "key": key,
        "tag": tag,
        "out_json": str(out_json),
        "out_md": str(out_md),
        "checked_at": summary.get("checked_at"),
        "overall": summary.get("overall"),
        "stage": summary.get("stage"),
        "target_hands": summary.get("min_training_hands"),
        "checkpoint_iteration": (summary.get("checkpoint") or {}).get("iteration"),
        "checkpoint_hands": (summary.get("checkpoint") or {}).get("total_hands"),
        "failed_checks": failed_check_names(summary),
    }


def write_next_external_plan_preview(
    args: argparse.Namespace,
    *,
    cadence: dict[str, Any],
    next_external_eval: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(next_external_eval, dict) or not next_external_eval:
        return {"status": "SKIP", "reason": "next_external_eval missing"}
    key = eval_key(next_external_eval)
    stage = str(next_external_eval.get("stage") or "")
    try:
        target_hands = int(next_external_eval.get("target_hands") or 0)
    except (TypeError, ValueError):
        target_hands = 0
    if key is None or not stage or target_hands <= 0:
        return {"status": "SKIP", "reason": "next_external_eval missing stage/target"}

    run_dir = Path(args.run_dir)
    tag = clean_tag(str(cadence.get("run_id") or run_dir.name), stage, target_hands)
    out_json, out_md = plan_preview_paths(run_dir, stage, target_hands)
    try:
        summary = evaluate_benchmark_plan(benchmark_plan_args(args, stage, target_hands, tag))
        write_json(out_json, summary)
        write_benchmark_plan_markdown(out_md, summary)
    except Exception as exc:
        return {
            "status": "ERROR",
            "key": key,
            "tag": tag,
            "out_json": str(out_json),
            "out_md": str(out_md),
            "error": str(exc),
        }
    return summarize_plan_preview(key=key, tag=tag, out_json=out_json, out_md=out_md, summary=summary)


def compact_eval(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(item, dict) or not item:
        return None
    remaining_live = item.get("remaining_live_hands")
    if remaining_live is None:
        remaining_live = remaining_to_target(item, "current_hands")
    return {
        "stage": item.get("stage"),
        "target_hands": item.get("target_hands"),
        "state": item.get("state"),
        "eta_duration_live": item.get("eta_duration_live"),
        "eta_seconds_live": item.get("eta_seconds_live"),
        "checkpoint_hands": item.get("checkpoint_hands"),
        "current_hands": item.get("current_hands"),
        "remaining_checkpoint_hands": item.get("remaining_checkpoint_hands"),
        "remaining_live_hands": remaining_live,
        "existing_ci_count": len(item.get("existing_ci") or []),
    }


def build_progress_aliases(cadence: dict[str, Any]) -> dict[str, Any]:
    current_hands = cadence.get("current_hands")
    checkpoint_hands = cadence.get("checkpoint_hands")
    checkpoint_iteration = cadence.get("checkpoint_iteration")
    return {
        "current_hands": current_hands,
        "current_live_hands": current_hands,
        "live_hands": current_hands,
        "checkpoint_hands": checkpoint_hands,
        "current_checkpoint_hands": checkpoint_hands,
        "checkpoint_iteration": checkpoint_iteration,
        "current_checkpoint_iteration": checkpoint_iteration,
    }


def remaining_to_target(item: dict[str, Any] | None, current_key: str) -> int | None:
    if not isinstance(item, dict) or not item:
        return None
    try:
        target_hands = int(item.get("target_hands") or 0)
        current_hands = int(item.get(current_key) or 0)
    except (TypeError, ValueError):
        return None
    if target_hands <= 0 or current_hands <= 0:
        return None
    return max(0, target_hands - current_hands)


def first_actionable_stage(cadence: dict[str, Any], key: str) -> dict[str, Any] | None:
    rows = cadence.get(key)
    if not isinstance(rows, list):
        return None
    for item in rows:
        if isinstance(item, dict) and item.get("state") in {"DUE", "WAITING"}:
            return item
    return None


def eval_key(item: dict[str, Any] | None) -> str | None:
    if not isinstance(item, dict) or not item:
        return None
    stage = str(item.get("stage") or "")
    try:
        target_hands = int(item.get("target_hands") or 0)
    except (TypeError, ValueError):
        target_hands = 0
    if not stage or target_hands <= 0:
        return None
    return schedule_key(stage, target_hands)


def overall_status(
    *,
    launchable_key: str | None,
    active_launches: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    next_external_eval: dict[str, Any] | None,
) -> str:
    if launchable_key:
        return "READY_TO_LAUNCH"
    if active_launches:
        return "ACTIVE_LAUNCH"
    if candidates:
        return "CANDIDATES_BLOCKED"
    if isinstance(next_external_eval, dict) and next_external_eval.get("state") == "WAITING":
        return "WAITING_FOR_TARGET"
    if isinstance(next_external_eval, dict) and next_external_eval.get("state") == "DUE":
        return "DUE_NO_CANDIDATE"
    return "NO_PENDING_TARGET"


def command_for_launch(
    args: argparse.Namespace,
    *,
    stage: str,
    target_hands: int,
    tag: str,
    run_dir: Path,
    plan: dict[str, Any] | None = None,
) -> list[str]:
    key = schedule_key(stage, target_hands)
    cmd = [
        args.python,
        "-X",
        "utf8",
        "-u",
        str(SCRIPT_DIR / "v5_slumbot_benchmark_watch.py"),
        "--run-dir",
        str(run_dir),
        "--stage",
        stage,
        "--tag",
        tag,
        "--output-dir",
        args.output_dir,
        "--min-training-hands",
        str(target_hands),
        "--sleep-seconds",
        str(args.child_sleep_seconds),
        "--status-json",
        str(run_dir / f"slumbot_cadence_{key}_status.json"),
        "--log",
        str(run_dir / f"slumbot_cadence_{key}.log"),
        "--plan-json",
        str(run_dir / f"slumbot_cadence_{key}_plan.json"),
        "--plan-md",
        str(run_dir / f"slumbot_cadence_{key}_plan.md"),
        "--append-report",
        args.append_report,
    ]
    if stage == "formal100k" and plan:
        checkpoint_path = str(plan.get("checkpoint_path") or "")
        prerequisite = plan.get("promotion20k_prerequisite") or {}
        promotion_gate_json = str(prerequisite.get("path") or "")
        if checkpoint_path:
            cmd.extend(["--checkpoint", checkpoint_path])
        if promotion_gate_json:
            cmd.extend(["--promotion-gate-json", promotion_gate_json])
    return cmd


def launch_due(
    args: argparse.Namespace,
    item: dict[str, Any],
    tag: str,
    plan: dict[str, Any] | None = None,
) -> dict[str, Any]:
    stage = str(item.get("stage"))
    target_hands = int(item.get("target_hands") or 0)
    run_dir = Path(args.run_dir)
    cmd = command_for_launch(
        args,
        stage=stage,
        target_hands=target_hands,
        tag=tag,
        run_dir=run_dir,
        plan=plan,
    )
    mutex = exp003_bundle_mutex_status(run_dir)
    if mutex["busy"]:
        return {
            "key": schedule_key(stage, target_hands),
            "stage": stage,
            "target_hands": target_hands,
            "tag": tag,
            "started_at": now_iso(),
            "finished_at": now_iso(),
            "elapsed_seconds": 0.0,
            "returncode": None,
            "status": "DEFERRED_EXP003_BUNDLE_MUTEX",
            "command": cmd,
            "output_tail": "",
            "exp003_bundle_mutex": mutex,
        }
    started_at = now_iso()
    started = time.time()
    proc = subprocess.run(
        cmd,
        cwd=str(Path.cwd()),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "key": schedule_key(stage, target_hands),
        "stage": stage,
        "target_hands": target_hands,
        "tag": tag,
        "started_at": started_at,
        "finished_at": now_iso(),
        "elapsed_seconds": time.time() - started,
        "returncode": proc.returncode,
        "status": "PASS" if proc.returncode == 0 else "FAIL",
        "command": cmd,
        "output_tail": proc.stdout[-4000:],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch due V5 external eval cadence points.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--status-json", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--append-report", default="reports/v5_zero_l6_fixedenv_launch.md")
    parser.add_argument("--poll-seconds", type=float, default=600.0)
    parser.add_argument("--child-sleep-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--max-health-age-seconds", type=int, default=600)
    parser.add_argument("--active-launch-max-age-seconds", type=float, default=21_600.0)
    parser.add_argument("--min-quick-target-hands", type=int, default=50_000_000)
    parser.add_argument("--min-promotion-target-hands", type=int, default=500_000_000)
    parser.add_argument("--min-formal-target-hands", type=int, default=500_000_000)
    parser.add_argument("--quick-interval-hands", type=int, default=50_000_000)
    parser.add_argument("--quick-until-hands", type=int, default=200_000_000)
    parser.add_argument("--promotion-interval-hands", type=int, default=250_000_000)
    parser.add_argument("--promotion-until-hands", type=int, default=1_000_000_000)
    parser.add_argument("--formal-interval-hands", type=int, default=250_000_000)
    parser.add_argument("--formal-until-hands", type=int, default=1_000_000_000)
    parser.add_argument("--retry-failed", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    status_path = Path(args.status_json) if args.status_json else run_dir / "v5_eval_cadence_watch_status.json"
    log_path = Path(args.log) if args.log else run_dir / "v5_eval_cadence_watch.log"
    state = load_json(status_path)
    history: list[dict[str, Any]] = list(state.get("history_tail") or [])
    completed = set(state.get("completed_keys") or [])
    failed = set(state.get("failed_keys") or [])

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    log(
        "eval cadence watcher started "
        f"run_dir={run_dir} dry_run={args.dry_run} "
        f"min_quick={args.min_quick_target_hands} min_promotion={args.min_promotion_target_hands} "
        f"min_formal={args.min_formal_target_hands}"
    )

    while True:
        cadence_args = argparse.Namespace(
            quick_interval_hands=args.quick_interval_hands,
            quick_until_hands=args.quick_until_hands,
            min_quick_target_hands=args.min_quick_target_hands,
            promotion_interval_hands=args.promotion_interval_hands,
            promotion_until_hands=args.promotion_until_hands,
            min_promotion_target_hands=args.min_promotion_target_hands,
            formal_interval_hands=args.formal_interval_hands,
            formal_until_hands=args.formal_until_hands,
            min_formal_target_hands=args.min_formal_target_hands,
        )
        cadence = build_cadence(run_dir, Path(args.output_dir), cadence_args)
        candidates = []
        active_launches = []
        for item in stage_targets(cadence, args):
            stage = str(item.get("stage"))
            target_hands = int(item.get("target_hands") or 0)
            key = schedule_key(stage, target_hands)
            if key in completed:
                continue
            if key in failed and not args.retry_failed:
                continue
            if item.get("state") != "DUE":
                continue
            active_launch = active_launch_for(
                run_dir,
                stage=stage,
                target_hands=target_hands,
                max_age_seconds=args.active_launch_max_age_seconds,
            )
            if active_launch:
                active_launches.append({"key": key, **active_launch})
                continue
            tag = clean_tag(str(cadence.get("run_id") or run_dir.name), stage, target_hands)
            plan = runnable_plan(args, item, tag, str(cadence.get("run_id") or run_dir.name))
            candidates.append({"key": key, "item": item, "tag": tag, "plan": plan})

        bundle_mutex = exp003_bundle_mutex_status(run_dir)
        launchable = next((row for row in candidates if (row.get("plan") or {}).get("overall") == "READY"), None)
        if bundle_mutex["busy"]:
            launchable = None
        next_external_eval = cadence.get("next_external_eval") if isinstance(cadence.get("next_external_eval"), dict) else None
        plan_preview = write_next_external_plan_preview(args, cadence=cadence, next_external_eval=next_external_eval)
        next_external_eval_remaining_checkpoint_hands = (next_external_eval or {}).get("remaining_checkpoint_hands")
        if next_external_eval_remaining_checkpoint_hands is None:
            next_external_eval_remaining_checkpoint_hands = remaining_to_target(next_external_eval, "checkpoint_hands")
        next_external_eval_remaining_live_hands = (next_external_eval or {}).get("remaining_live_hands")
        if next_external_eval_remaining_live_hands is None:
            next_external_eval_remaining_live_hands = remaining_to_target(next_external_eval, "current_hands")
        next_quick_eval = first_actionable_stage(cadence, "slumbot_quick_screens")
        next_promotion_eval = cadence.get("next_promotion_eval") if isinstance(cadence.get("next_promotion_eval"), dict) else None
        next_formal_eval = cadence.get("next_formal_eval") if isinstance(cadence.get("next_formal_eval"), dict) else None
        launchable_key = launchable.get("key") if launchable else None
        overall = overall_status(
            launchable_key=launchable_key,
            active_launches=active_launches,
            candidates=candidates,
            next_external_eval=next_external_eval,
        )
        if bundle_mutex["busy"]:
            overall = "BLOCKED_EXP003_BUNDLE_MUTEX"
        progress_aliases = build_progress_aliases(cadence)
        latest = {
            "checked_at": now_iso(),
            "run_dir": str(run_dir),
            "dry_run": args.dry_run,
            "overall": overall,
            "state": overall,
            "cadence_checked_at": cadence.get("checked_at"),
            "min_quick_target_hands": args.min_quick_target_hands,
            "min_promotion_target_hands": args.min_promotion_target_hands,
            "min_formal_target_hands": args.min_formal_target_hands,
            **progress_aliases,
            "candidate_count": len(candidates),
            "launchable_key": launchable_key,
            "active_launches": active_launches,
            "exp003_bundle_mutex": bundle_mutex,
            "next_external_plan_preview": plan_preview,
            "next_external_plan_preview_status": plan_preview.get("status"),
            "next_external_plan_preview_json": plan_preview.get("out_json"),
            "next_external_plan_preview_md": plan_preview.get("out_md"),
            "next_external_plan_preview_overall": plan_preview.get("overall"),
            "next_external_plan_preview_failed_checks": plan_preview.get("failed_checks"),
            "next_external_eval": compact_eval(next_external_eval),
            "next_external_eval_key": eval_key(next_external_eval),
            "next_external_eval_stage": (next_external_eval or {}).get("stage"),
            "next_external_eval_target_hands": (next_external_eval or {}).get("target_hands"),
            "next_external_eval_state": (next_external_eval or {}).get("state"),
            "next_external_eval_eta": (next_external_eval or {}).get("eta_duration_live"),
            "next_external_eval_eta_seconds": (next_external_eval or {}).get("eta_seconds_live"),
            "next_external_eval_checkpoint_hands": (next_external_eval or {}).get("checkpoint_hands"),
            "next_external_eval_current_hands": (next_external_eval or {}).get("current_hands"),
            "next_external_eval_remaining_checkpoint_hands": next_external_eval_remaining_checkpoint_hands,
            "next_external_eval_remaining_live_hands": next_external_eval_remaining_live_hands,
            "next_eval_key": eval_key(next_external_eval),
            "next_stage": (next_external_eval or {}).get("stage"),
            "next_target_hands": (next_external_eval or {}).get("target_hands"),
            "next_state": (next_external_eval or {}).get("state"),
            "next_eta": (next_external_eval or {}).get("eta_duration_live"),
            "next_eta_seconds": (next_external_eval or {}).get("eta_seconds_live"),
            "remaining_checkpoint_hands": next_external_eval_remaining_checkpoint_hands,
            "remaining_live_hands": next_external_eval_remaining_live_hands,
            "next_target": (next_external_eval or {}).get("target_hands"),
            "next_target_state": (next_external_eval or {}).get("state"),
            "next_quick_eval": compact_eval(next_quick_eval),
            "next_quick_key": eval_key(next_quick_eval),
            "next_quick_target_hands": (next_quick_eval or {}).get("target_hands"),
            "next_quick_state": (next_quick_eval or {}).get("state"),
            "next_quick_eta": (next_quick_eval or {}).get("eta_duration_live"),
            "next_promotion_eval": compact_eval(next_promotion_eval),
            "next_promotion_key": eval_key(next_promotion_eval),
            "next_formal_eval": compact_eval(next_formal_eval),
            "next_formal_key": eval_key(next_formal_eval),
            "blocked_candidates": [
                {
                    "key": row["key"],
                    "overall": (row.get("plan") or {}).get("overall"),
                    "failed_checks": [
                        check.get("name")
                        for check in (row.get("plan") or {}).get("checks", [])
                        if check.get("status") == "FAIL"
                    ],
                }
                for row in candidates[:10]
            ],
        }
        write_json(
            status_path,
            {
                **latest,
                "completed_keys": sorted(completed),
                "failed_keys": sorted(failed),
                "latest": latest,
                "history_tail": history[-20:],
            },
        )
        log(
            f"checkpoint_hands={cadence.get('checkpoint_hands')} candidates={len(candidates)} "
            f"launchable={latest['launchable_key']}"
        )

        if launchable:
            key = str(launchable["key"])
            if args.dry_run:
                history.append({"key": key, "status": "DRY_RUN_READY", "checked_at": now_iso()})
                log(f"dry-run launchable key={key}")
            else:
                result = launch_due(
                    args,
                    launchable["item"],
                    str(launchable["tag"]),
                    plan=launchable.get("plan"),
                )
                history.append(result)
                if result["status"] == "PASS":
                    completed.add(key)
                elif result["status"] != "DEFERRED_EXP003_BUNDLE_MUTEX":
                    failed.add(key)
                write_json(
                    status_path,
                    {
                        **latest,
                        "completed_keys": sorted(completed),
                        "failed_keys": sorted(failed),
                        "latest_launch": result,
                        "history_tail": history[-20:],
                    },
                )
                log(f"launch finished key={key} status={result['status']} returncode={result['returncode']}")

        if args.once:
            return 0
        time.sleep(max(args.poll_seconds, 1.0))


if __name__ == "__main__":
    raise SystemExit(main())
