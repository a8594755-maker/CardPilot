#!/usr/bin/env python3
"""Summarize a V5 AlphaHoldem long run from watcher artifacts.

This is a read-only dashboard generator. It consolidates training health,
progress, gate status, internal probes, Slumbot readiness/launch state, and
milestone archives into one JSON/Markdown snapshot.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_baseline_gap import build_baseline_gap
from v5_monitor import parse_log


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return now_utc().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    if isinstance(obj, dict):
        return obj
    return {"_load_error": f"JSON root is {type(obj).__name__}, not dict", "_path": str(path)}


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return max(0.0, (now_utc() - mtime).total_seconds())


def latest_gate(run_dir: Path) -> dict[str, Any]:
    paths = sorted(run_dir.glob("gate_*_status.json"))
    gate_summaries = []
    for path in paths:
        if path.name == "gate_sequence_status.json":
            continue
        data = load_json(path)
        target = data.get("target_iteration")
        if target is None:
            continue
        gate_summaries.append(
            {
                "path": str(path),
                "target_iteration": int(target),
                "overall": data.get("overall"),
                "checkpoint_iteration": (data.get("checkpoint") or {}).get("iteration"),
                "checkpoint_hands": (data.get("checkpoint") or {}).get("total_hands"),
                "health_overall": data.get("health_overall"),
                "age_seconds": file_age_seconds(path),
            }
        )
    if not gate_summaries:
        return {"overall": "UNKNOWN", "detail": "no gate_*_status.json files found"}
    passed = [item for item in gate_summaries if item.get("overall") == "PASS"]
    pending = [item for item in gate_summaries if item.get("overall") == "PENDING"]
    latest_pass = max(passed, key=lambda x: x["target_iteration"]) if passed else None
    next_pending = min(pending, key=lambda x: x["target_iteration"]) if pending else None
    return {
        "latest_pass": latest_pass,
        "next_pending": next_pending,
        "all_tail": sorted(gate_summaries, key=lambda x: x["target_iteration"])[-8:],
    }


def eta_for_hands(current_hands: int, target_hands: int, hps: float | None) -> dict[str, Any]:
    remaining = max(0, target_hands - current_hands)
    if not hps or hps <= 0:
        return {"target_hands": target_hands, "remaining_hands": remaining, "eta_seconds": None, "eta_duration": None}
    seconds = remaining / hps
    return {
        "target_hands": target_hands,
        "remaining_hands": remaining,
        "eta_seconds": seconds,
        "eta_duration": format_duration(seconds),
    }


def next_multiple_at_or_after(value: int, interval: int) -> int:
    return ((value + interval - 1) // interval) * interval


def next_multiple_after(value: int, interval: int) -> int:
    return ((value // interval) + 1) * interval


def estimate_hands_per_iteration(rows: list[dict[str, Any]], fallback: Any = None) -> float | None:
    tail = rows[-50:] if rows else []
    if len(tail) >= 2:
        first = tail[0]
        last = tail[-1]
        delta_iter = int(last.get("iteration") or 0) - int(first.get("iteration") or 0)
        delta_hands = int(last.get("hands") or 0) - int(first.get("hands") or 0)
        if delta_iter > 0 and delta_hands > 0:
            return delta_hands / delta_iter
    try:
        value = float(fallback)
        return value if value > 0 else None
    except Exception:
        return None


def estimate_seconds_per_iteration(rows: list[dict[str, Any]]) -> float | None:
    durations: list[float] = []
    tail = rows[-50:] if rows else []
    for prev, cur in zip(tail, tail[1:]):
        delta_hands = int(cur.get("hands") or 0) - int(prev.get("hands") or 0)
        hps = float(cur.get("hands_per_second") or 0.0)
        if delta_hands > 0 and hps > 0:
            durations.append(delta_hands / hps)
    return sum(durations) / len(durations) if durations else None


def checkpoint_eligibility_eta(
    *,
    target_hands: int,
    stage: str,
    rows: list[dict[str, Any]],
    checkpoint: dict[str, Any],
    manifest: dict[str, Any],
) -> dict[str, Any]:
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    save_interval = int(config.get("save_interval") or 0)
    latest = rows[-1] if rows else {}
    current_iteration = int(latest.get("iteration") or checkpoint.get("iteration") or 0)
    current_hands = int(latest.get("hands") or checkpoint.get("total_hands") or 0)
    checkpoint_iteration = int(checkpoint.get("iteration") or 0)
    checkpoint_hands = int(checkpoint.get("total_hands") or 0)

    base = {
        "stage": stage,
        "target_hands": target_hands,
        "checkpoint_hands": checkpoint_hands,
        "checkpoint_iteration": checkpoint_iteration,
        "current_iteration": current_iteration,
        "current_hands": current_hands,
        "eligible": checkpoint_hands >= target_hands,
    }
    if checkpoint_hands >= target_hands:
        return {
            **base,
            "target_checkpoint_iteration": checkpoint_iteration,
            "estimated_checkpoint_hands": checkpoint_hands,
            "remaining_iterations": 0,
            "eta_seconds": 0.0,
            "eta_duration": "0m",
        }
    if save_interval <= 0 or not rows:
        return {**base, "target_checkpoint_iteration": None, "estimated_checkpoint_hands": None, "remaining_iterations": None, "eta_seconds": None, "eta_duration": None}

    hands_per_iteration = estimate_hands_per_iteration(rows, config.get("hands_per_iter"))
    seconds_per_iteration = estimate_seconds_per_iteration(rows)
    if hands_per_iteration is None or hands_per_iteration <= 0:
        return {**base, "target_checkpoint_iteration": None, "estimated_checkpoint_hands": None, "remaining_iterations": None, "eta_seconds": None, "eta_duration": None}

    if current_hands >= target_hands:
        if current_iteration % save_interval == 0 and current_iteration > checkpoint_iteration:
            target_iteration = current_iteration
        else:
            target_iteration = next_multiple_after(current_iteration, save_interval)
    else:
        iterations_to_target = math.ceil((target_hands - current_hands) / hands_per_iteration)
        raw_iteration = current_iteration + max(0, iterations_to_target)
        target_iteration = next_multiple_at_or_after(raw_iteration, save_interval)
        if target_iteration <= checkpoint_iteration:
            target_iteration = next_multiple_after(checkpoint_iteration, save_interval)

    remaining_iterations = max(0, target_iteration - current_iteration)
    eta_seconds = remaining_iterations * seconds_per_iteration if seconds_per_iteration is not None else None
    estimated_checkpoint_hands = int(current_hands + remaining_iterations * hands_per_iteration)
    return {
        **base,
        "target_checkpoint_iteration": target_iteration,
        "estimated_checkpoint_hands": estimated_checkpoint_hands,
        "remaining_iterations": remaining_iterations,
        "eta_seconds": eta_seconds,
        "eta_duration": format_duration(eta_seconds),
        "hands_per_iteration_estimate": hands_per_iteration,
        "seconds_per_iteration_estimate": seconds_per_iteration,
    }


def format_duration(seconds: float | None) -> str | None:
    if seconds is None or not math.isfinite(seconds):
        return None
    seconds = max(0, int(seconds))
    days, rem = divmod(seconds, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, _ = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


def check_artifact_exists(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    if any(ch in value for ch in "*?[]"):
        matches = sorted(glob.glob(value))
        return {"pattern": value, "match_count": len(matches), "matches_tail": matches[-5:]}
    return {"path": value, "exists": Path(value).exists()}


def failed_checks(checks: Any) -> list[dict[str, Any]]:
    if not isinstance(checks, list):
        return []
    return [check for check in checks if isinstance(check, dict) and check.get("status") == "FAIL"]


def summarize_benchmark_result(status: dict[str, Any]) -> dict[str, Any]:
    result = status.get("benchmark_result") if isinstance(status, dict) else None
    preflight = status.get("preflight") if isinstance(status, dict) else None
    if not isinstance(result, dict):
        result = {}
    if not isinstance(preflight, dict):
        preflight = {}
    ci = result.get("ci_summary") if isinstance(result.get("ci_summary"), dict) else {}
    promotion = result.get("promotion_summary") if isinstance(result.get("promotion_summary"), dict) else {}
    return {
        "benchmark_status": result.get("status"),
        "returncode": result.get("returncode"),
        "orchestrator_log": result.get("orchestrator_log"),
        "orchestrator_err": result.get("orchestrator_err"),
        "preflight_overall": preflight.get("overall"),
        "preflight_json": preflight.get("preflight_json"),
        "preflight_md": preflight.get("preflight_md"),
        "preflight_failed_checks": failed_checks(preflight.get("checks")),
        "ci": {
            "hands": ci.get("hands"),
            "bb_per_100": ci.get("bb_per_100"),
            "lower_bound_bb_per_100": ci.get("lower_bound_bb_per_100"),
            "upper_bound_bb_per_100": ci.get("upper_bound_bb_per_100"),
            "milestone_level": ci.get("milestone_level"),
            "l5_formal_win": ci.get("l5_formal_win"),
            "l6_near_paper_target": ci.get("l6_near_paper_target"),
        } if ci else None,
        "promotion": {
            "overall": promotion.get("overall"),
            "decisions": promotion.get("decisions"),
            "failed_checks": failed_checks(promotion.get("checks")),
        } if promotion else None,
    }


def summarize_launch_status(status: dict[str, Any], status_path: Path) -> dict[str, Any]:
    plan = status.get("plan") if isinstance(status, dict) else {}
    if not isinstance(plan, dict):
        plan = {}
    artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), dict) else {}
    return {
        "state": status.get("state") if isinstance(status, dict) else None,
        "plan_overall": plan.get("overall"),
        "checkpoint": plan.get("checkpoint"),
        "planned_hands": plan.get("planned_hands"),
        "min_training_hands": plan.get("min_training_hands"),
        "promotion20k_prerequisite": plan.get("promotion20k_prerequisite"),
        "failed_plan_checks": failed_checks(plan.get("checks")),
        "checks": plan.get("checks"),
        "artifacts": {
            key: check_artifact_exists(value)
            for key, value in artifacts.items()
        },
        "result": summarize_benchmark_result(status),
        "status_age_seconds": file_age_seconds(status_path),
    }


def summarize_latest_cadence_launch(run_dir: Path, cadence_status: dict[str, Any], stage: str) -> dict[str, Any]:
    candidates: list[tuple[int, str, str, Path, dict[str, Any], dict[str, Any]]] = []
    history = cadence_status.get("history_tail") if isinstance(cadence_status, dict) else []
    if isinstance(history, list):
        for item in history:
            if not isinstance(item, dict) or item.get("stage") != stage:
                continue
            key = str(item.get("key") or "")
            if not key:
                continue
            status_path = run_dir / f"slumbot_cadence_{key}_status.json"
            status = load_json(status_path)
            if status.get("_missing") or status.get("_load_error"):
                continue
            target_hands = item.get("target_hands")
            if not isinstance(target_hands, int):
                target_hands = int((status.get("plan") or {}).get("min_training_hands") or 0)
            candidates.append((target_hands, str(item.get("finished_at") or ""), key, status_path, status, item))

    for status_path in sorted(run_dir.glob(f"slumbot_cadence_{stage}_*_status.json")):
        status = load_json(status_path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        plan = status.get("plan") if isinstance(status.get("plan"), dict) else {}
        key = status_path.name.removeprefix("slumbot_cadence_").removesuffix("_status.json")
        target_hands = int(plan.get("min_training_hands") or 0)
        candidates.append((target_hands, str(status.get("checked_at") or ""), key, status_path, status, {}))

    if not candidates:
        return {}

    target_hands, _, key, status_path, status, launch_item = max(
        candidates,
        key=lambda item: (item[0], item[1], item[2]),
    )
    summary = summarize_launch_status(status, status_path)
    summary.update(
        {
            "source": "eval_cadence_watch",
            "key": key,
            "tag": launch_item.get("tag") or status.get("tag"),
            "target_hands": target_hands,
            "started_at": launch_item.get("started_at"),
            "finished_at": launch_item.get("finished_at") or status.get("checked_at"),
            "launch_status": launch_item.get("status") or status.get("state"),
            "status_path": str(status_path),
            "frozen_iteration": (status.get("frozen_summary") or {}).get("iteration"),
            "frozen_hands": (status.get("frozen_summary") or {}).get("total_hands"),
        }
    )
    return summary


def summarize_preflight_probe(status: dict[str, Any], status_path: Path) -> dict[str, Any]:
    preflight = status.get("preflight") if isinstance(status, dict) else {}
    if not isinstance(preflight, dict):
        preflight = {}
    frozen = status.get("frozen_summary") if isinstance(status, dict) else {}
    if not isinstance(frozen, dict):
        frozen = {}
    return {
        "state": status.get("state") if isinstance(status, dict) else None,
        "checked_at": status.get("checked_at") if isinstance(status, dict) else None,
        "frozen_checkpoint": status.get("frozen_checkpoint") if isinstance(status, dict) else None,
        "frozen_iteration": frozen.get("iteration"),
        "frozen_hands": frozen.get("total_hands"),
        "preflight_overall": preflight.get("overall"),
        "preflight_json": preflight.get("preflight_json"),
        "preflight_md": preflight.get("preflight_md"),
        "failed_checks": failed_checks(preflight.get("checks")),
        "status_age_seconds": file_age_seconds(status_path),
    }


def summarize_eval_cadence_watch(status: dict[str, Any], status_path: Path) -> dict[str, Any]:
    preview = (
        status.get("next_external_plan_preview")
        if isinstance(status.get("next_external_plan_preview"), dict)
        else {}
    )
    failed_preview_checks = status.get("next_external_plan_preview_failed_checks")
    if failed_preview_checks is None:
        failed_preview_checks = preview.get("failed_checks")
    return {
        "dry_run": status.get("dry_run"),
        "candidate_count": status.get("candidate_count"),
        "launchable_key": status.get("launchable_key"),
        "completed_keys": status.get("completed_keys"),
        "failed_keys": status.get("failed_keys"),
        "checkpoint_iteration": status.get("current_checkpoint_iteration") or status.get("checkpoint_iteration"),
        "checkpoint_hands": status.get("current_checkpoint_hands") or status.get("checkpoint_hands"),
        "current_hands": status.get("current_hands"),
        "live_hands": status.get("live_hands") or status.get("current_live_hands") or status.get("current_hands"),
        "status_age_seconds": file_age_seconds(status_path),
        "next_external_plan_preview": {
            "status": status.get("next_external_plan_preview_status") or preview.get("status"),
            "key": preview.get("key"),
            "tag": preview.get("tag"),
            "json": status.get("next_external_plan_preview_json") or preview.get("out_json"),
            "md": status.get("next_external_plan_preview_md") or preview.get("out_md"),
            "overall": status.get("next_external_plan_preview_overall") or preview.get("overall"),
            "failed_checks": failed_preview_checks if isinstance(failed_preview_checks, list) else [],
            "checkpoint_iteration": preview.get("checkpoint_iteration"),
            "checkpoint_hands": preview.get("checkpoint_hands"),
        },
    }


def internal_probe_target_from_path(path: Path) -> int | None:
    prefix = "internal_strength_probe_iter"
    stem = path.stem
    if not stem.startswith(prefix):
        return None
    token = stem[len(prefix) :].split("_", 1)[0]
    try:
        return int(token)
    except ValueError:
        return None


def collect_internal_probe(
    probe_rows: list[tuple[int, str, Path, dict[str, Any]]],
    completed: set[int],
    targets: set[int],
    path: Path,
    probe: dict[str, Any],
    *,
    checked_at_fallback: str = "",
) -> None:
    target = probe.get("target_iteration")
    if not isinstance(target, int):
        checkpoint = probe.get("checkpoint") if isinstance(probe.get("checkpoint"), dict) else {}
        target = checkpoint.get("iteration")
    if not isinstance(target, int):
        target = internal_probe_target_from_path(path)
    if not isinstance(target, int):
        return

    status = probe.get("status") or probe.get("overall")
    if status is None and (probe.get("results") or probe.get("checkpoint")):
        status = "PASS"

    normalized = dict(probe)
    normalized["target_iteration"] = target
    if status is not None:
        normalized["status"] = status

    targets.add(target)
    if status == "PASS":
        completed.add(target)
    checked_at = str(normalized.get("checked_at") or checked_at_fallback or "")
    probe_rows.append((target, checked_at, path, normalized))


def summarize_internal_strength(run_dir: Path) -> dict[str, Any]:
    paths = sorted(run_dir.glob("internal_strength_watch*_status.json"))
    statuses: list[tuple[Path, dict[str, Any]]] = []
    completed: set[int] = set()
    targets: set[int] = set()
    readiness_rows: list[tuple[int, Path, dict[str, Any]]] = []
    probe_rows: list[tuple[int, str, Path, dict[str, Any]]] = []

    for path in paths:
        status = load_json(path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        statuses.append((path, status))
        for target in status.get("targets") or []:
            if isinstance(target, int):
                targets.add(target)
        for target in status.get("completed") or []:
            if isinstance(target, int):
                completed.add(target)
        readiness = status.get("latest_readiness")
        if isinstance(readiness, dict):
            target = readiness.get("target_iteration")
            if isinstance(target, int):
                readiness_rows.append((target, path, readiness))
        probe = status.get("latest_probe")
        if isinstance(probe, dict):
            collect_internal_probe(
                probe_rows,
                completed,
                targets,
                path,
                probe,
                checked_at_fallback=str(status.get("checked_at") or ""),
            )
        for item in status.get("history_tail") or []:
            if not isinstance(item, dict) or not isinstance(item.get("probe"), dict):
                continue
            collect_internal_probe(
                probe_rows,
                completed,
                targets,
                path,
                item["probe"],
                checked_at_fallback=str(status.get("checked_at") or ""),
            )

    for probe_path in sorted(run_dir.glob("internal_strength_probe_iter*_*.json")):
        probe = load_json(probe_path)
        if probe.get("_missing") or probe.get("_load_error"):
            continue
        collect_internal_probe(probe_rows, completed, targets, probe_path, probe)

    fallback_path = run_dir / "internal_strength_watch_status.json"
    if not statuses and not probe_rows:
        missing = load_json(fallback_path)
        return {
            "completed": missing.get("completed"),
            "targets": missing.get("targets"),
            "latest_target": (missing.get("latest_readiness") or {}).get("target_iteration"),
            "latest_overall": (missing.get("latest_readiness") or {}).get("overall"),
            "latest_checkpoint": (missing.get("latest_readiness") or {}).get("checkpoint"),
            "latest_probe_target": (missing.get("latest_probe") or {}).get("target_iteration"),
            "latest_probe_status": (missing.get("latest_probe") or {}).get("status"),
            "next_target": None,
            "next_overall": None,
            "status_age_seconds": file_age_seconds(fallback_path),
            "selected_status_path": str(fallback_path),
            "status_paths": [str(fallback_path)],
        }

    completed_sorted = sorted(completed)
    target_sorted = sorted(targets)
    pending_readiness = [
        (target, path, readiness)
        for target, path, readiness in readiness_rows
        if target not in completed and readiness.get("overall") != "PASS"
    ]
    if pending_readiness:
        next_target, next_path, next_readiness = min(pending_readiness, key=lambda item: item[0])
    else:
        next_target = next((target for target in target_sorted if target not in completed), None)
        next_path = statuses[-1][0] if statuses else (latest_probe_path or fallback_path)
        next_readiness = {}

    if probe_rows:
        latest_probe_target, _, latest_probe_path, latest_probe = max(probe_rows, key=lambda item: (item[0], item[1]))
    else:
        latest_probe_target = None
        latest_probe_path = None
        latest_probe = {}

    selected_age_path = next_path if next_target is not None else (
        latest_probe_path or (statuses[-1][0] if statuses else fallback_path)
    )
    return {
        "completed": completed_sorted,
        "targets": target_sorted,
        "latest_target": latest_probe_target,
        "latest_overall": latest_probe.get("status"),
        "latest_checkpoint": latest_probe.get("checkpoint"),
        "latest_probe_target": latest_probe_target,
        "latest_probe_status": latest_probe.get("status"),
        "latest_probe": latest_probe,
        "next_target": next_target,
        "next_overall": next_readiness.get("overall") if next_readiness else None,
        "next_checkpoint": next_readiness.get("checkpoint") if next_readiness else None,
        "status_age_seconds": file_age_seconds(selected_age_path),
        "selected_status_path": str(selected_age_path),
        "status_paths": [str(path) for path, _ in statuses],
    }


def summarize_watcher_state(run_dir: Path) -> dict[str, Any]:
    internal = summarize_internal_strength(run_dir)
    slumbot_launch = load_json(run_dir / "slumbot_quick5k_launch_status.json")
    promotion_launch = load_json(run_dir / "slumbot_promotion20k_launch_status.json")
    formal_launch = load_json(run_dir / "slumbot_formal100k_launch_status.json")
    quick5k_probe_path = run_dir / "quick5k_preflight_only_probe_status.json"
    quick5k_probe = load_json(quick5k_probe_path)
    archive = load_json(run_dir / "checkpoint_archive_status.json")
    slumbot_plan = load_json(run_dir / "slumbot_plan_quick5k.json")
    eval_cadence = load_json(run_dir / "v5_eval_cadence.json")
    eval_cadence_watch = load_json(run_dir / "v5_eval_cadence_watch_status.json")
    legacy_quick5k = summarize_launch_status(slumbot_launch, run_dir / "slumbot_quick5k_launch_status.json")
    cadence_quick5k = summarize_latest_cadence_launch(run_dir, eval_cadence_watch, "quick5k")

    return {
        "internal_strength": {
            "completed": internal.get("completed"),
            "targets": internal.get("targets"),
            "latest_target": internal.get("latest_target"),
            "latest_overall": internal.get("latest_overall"),
            "latest_checkpoint": internal.get("latest_checkpoint"),
            "latest_probe_target": internal.get("latest_probe_target"),
            "latest_probe_status": internal.get("latest_probe_status"),
            "next_target": internal.get("next_target"),
            "next_overall": internal.get("next_overall"),
            "next_checkpoint": internal.get("next_checkpoint"),
            "status_age_seconds": internal.get("status_age_seconds"),
            "selected_status_path": internal.get("selected_status_path"),
            "status_paths": internal.get("status_paths"),
        },
        "slumbot_quick5k_launch": legacy_quick5k,
        "slumbot_quick5k_latest": cadence_quick5k or legacy_quick5k,
        "slumbot_quick5k_preflight_probe": summarize_preflight_probe(quick5k_probe, quick5k_probe_path),
        "slumbot_promotion20k_launch": summarize_launch_status(promotion_launch, run_dir / "slumbot_promotion20k_launch_status.json"),
        "slumbot_formal100k_launch": summarize_launch_status(formal_launch, run_dir / "slumbot_formal100k_launch_status.json"),
        "slumbot_quick5k_plan": {
            "overall": slumbot_plan.get("overall"),
            "checkpoint": slumbot_plan.get("checkpoint"),
            "checks": slumbot_plan.get("checks"),
            "status_age_seconds": file_age_seconds(run_dir / "slumbot_plan_quick5k.json"),
        },
        "eval_cadence": {
            "next_external_eval": eval_cadence.get("next_external_eval"),
            "next_promotion_eval": eval_cadence.get("next_promotion_eval"),
            "next_formal_eval": eval_cadence.get("next_formal_eval"),
            "policy": eval_cadence.get("policy"),
            "status_age_seconds": file_age_seconds(run_dir / "v5_eval_cadence.json"),
        },
        "eval_cadence_watch": summarize_eval_cadence_watch(
            eval_cadence_watch,
            run_dir / "v5_eval_cadence_watch_status.json",
        ),
        "checkpoint_archive": {
            "completed": archive.get("completed"),
            "milestones": archive.get("milestones"),
            "latest_result": archive.get("latest_result") or (archive.get("history_tail") or [None])[-1],
            "status_age_seconds": file_age_seconds(run_dir / "checkpoint_archive_status.json"),
        },
    }


def infer_goal_status(summary: dict[str, Any]) -> dict[str, Any]:
    slumbot_launch = (
        summary["watchers"].get("slumbot_quick5k_latest")
        or summary["watchers"].get("slumbot_quick5k_launch")
        or {}
    )
    promotion_launch = summary["watchers"].get("slumbot_promotion20k_launch") or {}
    ci = None
    promotion = None
    result_summary = slumbot_launch.get("result") if isinstance(slumbot_launch.get("result"), dict) else {}
    if result_summary:
        ci = result_summary.get("ci")
        promotion = result_summary.get("promotion")
    result = slumbot_launch.get("benchmark_result")
    if isinstance(result, dict):
        ci = ci or result.get("ci_summary")
        promotion = promotion or result.get("promotion_summary")
    artifacts = slumbot_launch.get("artifacts") if isinstance(slumbot_launch, dict) else {}
    if isinstance(artifacts, dict):
        ci_artifact = artifacts.get("ci_json") if isinstance(artifacts.get("ci_json"), dict) else {}
        promotion_artifact = artifacts.get("promotion_json") if isinstance(artifacts.get("promotion_json"), dict) else {}
        if not ci and ci_artifact.get("exists") and ci_artifact.get("path"):
            ci = load_json(Path(str(ci_artifact["path"])))
        if not promotion and promotion_artifact.get("exists") and promotion_artifact.get("path"):
            promotion = load_json(Path(str(promotion_artifact["path"])))

    baseline_gap = summary.get("baseline_gap") or {}
    latest_slumbot = baseline_gap.get("latest_slumbot") or {}
    target_gap = baseline_gap.get("gap") or {}
    if not ci and latest_slumbot.get("exists"):
        ci = {
            "hands": latest_slumbot.get("hands"),
            "bb_per_100": latest_slumbot.get("bb_per_100"),
            "lower_bound_bb_per_100": latest_slumbot.get("lower_bound_bb_per_100"),
            "upper_bound_bb_per_100": latest_slumbot.get("upper_bound_bb_per_100"),
            "milestone_level": latest_slumbot.get("milestone_level"),
            "l5_formal_win": target_gap.get("formal_l5_ready"),
            "l6_near_paper_target": target_gap.get("formal_l6_ready"),
        }

    blockers = []
    checkpoint_hands = int((summary.get("checkpoint") or {}).get("total_hands") or 0)
    if checkpoint_hands < 50_000_000:
        blockers.append("quick5k not eligible until checkpoint hands >= 50M")
    if checkpoint_hands < 250_000_000:
        blockers.append("promotion20k/formal100k not eligible until later staged training")
    if promotion_launch.get("state") != "PASS":
        blockers.append("promotion20k Slumbot screen has not passed")
    formal_launch = summary["watchers"].get("slumbot_formal100k_launch") or {}
    formal_prereq = formal_launch.get("promotion20k_prerequisite") or {}
    if formal_launch.get("state") not in {"PASS", "RUNNING"}:
        blockers.append("formal100k Slumbot benchmark has not passed")
    if formal_prereq and formal_prereq.get("status") != "PASS":
        blockers.append("formal100k blocked until promotion20k strong gate passes")
    if not ci:
        blockers.append("no Slumbot CI result yet")
    if not promotion:
        blockers.append("no Slumbot promotion-gate result yet")
    elif promotion.get("overall") != "PASS":
        blockers.append("Slumbot quick5k promotion gate did not pass")

    return {
        "l5_formal_win_proven": bool(ci and ci.get("l5_formal_win")),
        "l6_near_paper_target_proven": bool(ci and ci.get("l6_near_paper_target")),
        "current_milestone_level": ci.get("milestone_level") if isinstance(ci, dict) else "UNPROVEN",
        "blockers": blockers,
    }


def build_summary(run_dir: Path, output_dir: Path | None = None) -> dict[str, Any]:
    health = load_json(run_dir / "health_status.json")
    progress = load_json(run_dir / "progress_status.json")
    manifest = load_json(run_dir / "run_manifest.json")
    rows = parse_log(run_dir / "latest_train.log")
    latest_log = rows[-1] if rows else None
    checkpoint = progress.get("checkpoint") if isinstance(progress.get("checkpoint"), dict) else {}
    progress_latest = progress.get("latest") if isinstance(progress.get("latest"), dict) else None
    if latest_log and (
        not progress_latest
        or int(latest_log.get("iteration") or 0) >= int(progress_latest.get("iteration") or 0)
    ):
        latest = latest_log
    else:
        latest = progress_latest

    current_hands = int((latest or {}).get("hands") or checkpoint.get("total_hands") or manifest.get("total_hands") or 0)
    hps = progress.get("recent_hands_per_second") or (latest or {}).get("hands_per_second")

    slumbot_output_dir = output_dir or Path("models")
    try:
        baseline_gap = build_baseline_gap(run_dir, slumbot_output_dir)
    except Exception as exc:
        baseline_gap = {
            "overall": "ERROR",
            "error": str(exc),
            "run_dir": str(run_dir),
            "output_dir": str(slumbot_output_dir),
        }

    summary = {
        "checked_at": iso_now(),
        "run_dir": str(run_dir),
        "run_id": manifest.get("run_id") or run_dir.name,
        "health": {
            "overall": health.get("overall"),
            "latest": health.get("latest"),
            "recent_means": health.get("recent_means"),
            "age_seconds": file_age_seconds(run_dir / "health_status.json"),
        },
        "training": {
            "latest": latest,
            "current_hands": current_hands,
            "recent_hands_per_second": hps,
            "log_age_seconds": file_age_seconds(run_dir / "latest_train.log"),
        },
        "checkpoint": checkpoint,
        "progress": {
            "upcoming_gates": progress.get("upcoming_gates"),
            "milestones": progress.get("milestones"),
            "eta_50m": eta_for_hands(current_hands, 50_000_000, float(hps) if hps else None),
            "eta_250m": eta_for_hands(current_hands, 250_000_000, float(hps) if hps else None),
            "eta_1b": eta_for_hands(current_hands, 1_000_000_000, float(hps) if hps else None),
            "eta_2p7b": eta_for_hands(current_hands, 2_700_000_000, float(hps) if hps else None),
            "checkpoint_eligibility": {
                "quick5k": checkpoint_eligibility_eta(
                    target_hands=50_000_000,
                    stage="quick5k",
                    rows=rows,
                    checkpoint=checkpoint,
                    manifest=manifest,
                ),
                "promotion20k": checkpoint_eligibility_eta(
                    target_hands=250_000_000,
                    stage="promotion20k",
                    rows=rows,
                    checkpoint=checkpoint,
                    manifest=manifest,
                ),
                "formal100k": checkpoint_eligibility_eta(
                    target_hands=250_000_000,
                    stage="formal100k",
                    rows=rows,
                    checkpoint=checkpoint,
                    manifest=manifest,
                ),
            },
        },
        "gates": latest_gate(run_dir),
        "watchers": summarize_watcher_state(run_dir),
        "baseline_gap": baseline_gap,
        "preflop_probe": {
            **load_json(run_dir / "v5_preflop_probe_latest.json"),
            "path": str(run_dir / "v5_preflop_probe_latest.json"),
            "status_age_seconds": file_age_seconds(run_dir / "v5_preflop_probe_latest.json"),
        },
    }
    summary["goal_status"] = infer_goal_status(summary)
    return summary


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    training = summary["training"]
    latest = training.get("latest") or {}
    checkpoint = summary.get("checkpoint") or {}
    progress = summary.get("progress") or {}
    gates = summary.get("gates") or {}
    watchers = summary.get("watchers") or {}
    goal = summary.get("goal_status") or {}
    checkpoint_eligibility = progress.get("checkpoint_eligibility") or {}
    quick5k_checkpoint_eta = checkpoint_eligibility.get("quick5k") or {}
    promotion20k_checkpoint_eta = checkpoint_eligibility.get("promotion20k") or {}
    eval_cadence = watchers.get("eval_cadence") or {}
    eval_cadence_watch = watchers.get("eval_cadence_watch") or {}
    eval_cadence_preview = eval_cadence_watch.get("next_external_plan_preview") or {}
    next_external_eval = eval_cadence.get("next_external_eval") or {}
    next_promotion_eval = eval_cadence.get("next_promotion_eval") or {}
    next_formal_eval = eval_cadence.get("next_formal_eval") or {}
    baseline_gap = summary.get("baseline_gap") or {}
    latest_slumbot = baseline_gap.get("latest_slumbot") or {}
    baseline_comparison = baseline_gap.get("baseline_comparison") or {}
    reference_baseline = baseline_gap.get("reference_baseline") or {}
    target_gap = baseline_gap.get("gap") or {}
    targets = baseline_gap.get("targets") or {}
    claim_rules = baseline_gap.get("claim_rules") or {}
    internal_strength = watchers.get("internal_strength") or {}
    quick5k_launch = watchers.get("slumbot_quick5k_latest") or watchers.get("slumbot_quick5k_launch") or {}
    legacy_quick5k_launch = watchers.get("slumbot_quick5k_launch") or {}
    quick5k_probe = watchers.get("slumbot_quick5k_preflight_probe") or {}
    promotion20k_launch = watchers.get("slumbot_promotion20k_launch") or {}
    formal100k_launch = watchers.get("slumbot_formal100k_launch") or {}
    checkpoint_archive = watchers.get("checkpoint_archive") or {}
    preflop_probe = summary.get("preflop_probe") or {}

    lines = [
        "# V5 Run Dashboard",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Run: `{summary['run_id']}`",
        f"- Health: `{summary['health'].get('overall')}`",
        f"- Live iteration: `{latest.get('iteration')}`",
        f"- Live hands: `{training.get('current_hands'):,}`",
        f"- Recent h/s: `{training.get('recent_hands_per_second')}`",
        f"- Checkpoint iteration: `{checkpoint.get('iteration')}`",
        f"- Checkpoint hands: `{checkpoint.get('total_hands'):,}`" if checkpoint.get("total_hands") is not None else "- Checkpoint hands: `unknown`",
        "",
        "## Next",
        "",
    ]
    for gate in progress.get("upcoming_gates") or []:
        lines.append(f"- Gate `{gate.get('target_iteration')}` `{gate.get('name')}` ETA `{gate.get('eta_duration')}`")
    lines.extend(
        [
            f"- 50M ETA: `{(progress.get('eta_50m') or {}).get('eta_duration')}`",
            f"- quick5k checkpoint ETA: iter `{quick5k_checkpoint_eta.get('target_checkpoint_iteration')}` / `{quick5k_checkpoint_eta.get('eta_duration')}`",
            f"- 250M ETA: `{(progress.get('eta_250m') or {}).get('eta_duration')}`",
            f"- promotion20k checkpoint ETA: iter `{promotion20k_checkpoint_eta.get('target_checkpoint_iteration')}` / `{promotion20k_checkpoint_eta.get('eta_duration')}`",
            "",
            "## Gates",
            "",
            f"- Latest PASS: `{((gates.get('latest_pass') or {}).get('target_iteration'))}`",
            f"- Next pending: `{((gates.get('next_pending') or {}).get('target_iteration'))}`",
            "",
            "## Watchers",
            "",
            f"- Internal strength: `{internal_strength.get('latest_overall')}` target `{internal_strength.get('latest_target')}` age `{format_duration(internal_strength.get('status_age_seconds'))}`",
            f"- Latest Slumbot quick5k: `{quick5k_launch.get('state')}` / plan `{quick5k_launch.get('plan_overall')}` / source `{quick5k_launch.get('source') or 'legacy'}` / key `{quick5k_launch.get('key')}` age `{format_duration(quick5k_launch.get('status_age_seconds'))}`",
            f"- Legacy Slumbot quick5k launcher: `{legacy_quick5k_launch.get('state')}` / plan `{legacy_quick5k_launch.get('plan_overall')}` age `{format_duration(legacy_quick5k_launch.get('status_age_seconds'))}`",
            f"- Slumbot quick5k launch-path probe: `{quick5k_probe.get('state')}` / preflight `{quick5k_probe.get('preflight_overall')}` age `{format_duration(quick5k_probe.get('status_age_seconds'))}`",
            f"- Slumbot promotion20k launcher: `{promotion20k_launch.get('state')}` / plan `{promotion20k_launch.get('plan_overall')}` age `{format_duration(promotion20k_launch.get('status_age_seconds'))}`",
            f"- Slumbot formal100k launcher: `{formal100k_launch.get('state')}` / plan `{formal100k_launch.get('plan_overall')}` age `{format_duration(formal100k_launch.get('status_age_seconds'))}`",
            f"- Eval cadence launcher: dry_run `{eval_cadence_watch.get('dry_run')}` / candidates `{eval_cadence_watch.get('candidate_count')}` / launchable `{eval_cadence_watch.get('launchable_key')}`",
            f"- Eval cadence next-preview: `{eval_cadence_preview.get('status')}` / overall `{eval_cadence_preview.get('overall')}` / failed `{eval_cadence_preview.get('failed_checks')}`",
            f"- Eval cadence preview checkpoint: iter `{eval_cadence_preview.get('checkpoint_iteration')}` / hands `{eval_cadence_preview.get('checkpoint_hands')}` / json `{eval_cadence_preview.get('json')}`",
            f"- Eval cadence launcher age: `{format_duration(eval_cadence_watch.get('status_age_seconds'))}`",
            f"- Checkpoint archive: latest `{(checkpoint_archive.get('latest_result') or {}).get('overall')}` age `{format_duration(checkpoint_archive.get('status_age_seconds'))}`",
            f"- quick5k probe frozen checkpoint: iter `{quick5k_probe.get('frozen_iteration')}` / hands `{quick5k_probe.get('frozen_hands')}` / json `{quick5k_probe.get('preflight_json')}`",
            f"- Preflop policy probe: `{preflop_probe.get('overall')}` iter `{(preflop_probe.get('checkpoint') or {}).get('iteration')}` age `{format_duration(preflop_probe.get('status_age_seconds'))}`",
            "",
            "## Evaluation Cadence",
            "",
            f"- Next external eval: `{next_external_eval.get('stage')}` target `{next_external_eval.get('target_hands')}` state `{next_external_eval.get('state')}` ETA `{next_external_eval.get('eta_duration_live')}`",
            f"- Next promotion eval: `{next_promotion_eval.get('stage')}` target `{next_promotion_eval.get('target_hands')}` state `{next_promotion_eval.get('state')}` ETA `{next_promotion_eval.get('eta_duration_live')}`",
            f"- Next formal eval: `{next_formal_eval.get('stage')}` target `{next_formal_eval.get('target_hands')}` state `{next_formal_eval.get('state')}` ETA `{next_formal_eval.get('eta_duration_live')}`",
            f"- Cadence watcher checkpoint/current hands: `{eval_cadence_watch.get('checkpoint_hands')}` / `{eval_cadence_watch.get('current_hands')}`",
            f"- Cadence watcher checkpoint iteration: `{eval_cadence_watch.get('checkpoint_iteration')}`",
            f"- Cadence watcher status age: `{format_duration(eval_cadence_watch.get('status_age_seconds'))}`",
            f"- Cadence completed keys: `{eval_cadence_watch.get('completed_keys')}`",
            f"- Cadence failed keys: `{eval_cadence_watch.get('failed_keys')}`",
            "",
            "## Baseline And L6 Gap",
            "",
            f"- Baseline gap status: `{baseline_gap.get('overall')}`",
            f"- Reference baseline: `{reference_baseline.get('bb_per_100')}` bb/100 over `{reference_baseline.get('hands')}` hands",
            f"- Latest Slumbot hands: `{latest_slumbot.get('hands')}`",
            f"- Latest Slumbot bb/100: `{latest_slumbot.get('bb_per_100')}`",
            f"- Latest Slumbot CI lower: `{latest_slumbot.get('lower_bound_bb_per_100')}`",
            f"- Stronger than V4/BC baseline: `{baseline_comparison.get('answer')}`",
            f"- Can claim stronger than V4/BC baseline: `{claim_rules.get('can_claim_stronger_than_v4')}`",
            f"- L6 target: `{targets.get('l6_target_bb_per_100')}` bb/100",
            f"- Gap to L6 target bb/100: `{target_gap.get('to_l6_target_bb100')}`",
            f"- Gap blockers: `{target_gap.get('blockers')}`",
            "",
            "## Preflop Guardrail",
            "",
            f"- Overall: `{preflop_probe.get('overall')}`",
            f"- Probe JSON: `{preflop_probe.get('path')}`",
        ]
    )
    for warning in preflop_probe.get("warnings") or []:
        lines.append(f"- Warning: `{warning.get('case')}` `{warning.get('name')}` - {warning.get('detail')}")
    lines.extend(
        [
            "",
            "## Goal Status",
            "",
            f"- L5 proven: `{goal.get('l5_formal_win_proven')}`",
            f"- L6 proven: `{goal.get('l6_near_paper_target_proven')}`",
            f"- Current Slumbot level: `{goal.get('current_milestone_level')}`",
        ]
    )
    for blocker in goal.get("blockers") or []:
        lines.append(f"- Blocker: {blocker}")
    lines.extend(["", "## Launch Diagnostics", ""])
    for label, key in [
        ("quick5k latest", "slumbot_quick5k_latest"),
        ("quick5k legacy", "slumbot_quick5k_launch"),
        ("promotion20k", "slumbot_promotion20k_launch"),
        ("formal100k", "slumbot_formal100k_launch"),
    ]:
        launch = watchers.get(key) or {}
        result = launch.get("result") or {}
        failed_plan = launch.get("failed_plan_checks") or []
        artifacts = launch.get("artifacts") or {}
        ci_artifact = artifacts.get("ci_json")
        promotion_artifact = artifacts.get("promotion_json")
        dump_artifact = artifacts.get("dump_analysis")
        dump_glob_artifact = artifacts.get("dump_glob")
        audit_artifact = artifacts.get("artifact_audit_json")
        hand_review_artifact = artifacts.get("hand_review_json")
        selector_replay_artifact = artifacts.get("selector_replay_json")
        ci_path = ci_artifact.get("path") if isinstance(ci_artifact, dict) else ci_artifact
        promotion_path = promotion_artifact.get("path") if isinstance(promotion_artifact, dict) else promotion_artifact
        dump_path = dump_artifact.get("path") if isinstance(dump_artifact, dict) else dump_artifact
        dump_exists = dump_artifact.get("exists") if isinstance(dump_artifact, dict) else None
        dump_count = dump_glob_artifact.get("match_count") if isinstance(dump_glob_artifact, dict) else None
        audit_path = audit_artifact.get("path") if isinstance(audit_artifact, dict) else audit_artifact
        audit_exists = audit_artifact.get("exists") if isinstance(audit_artifact, dict) else None
        hand_review_path = hand_review_artifact.get("path") if isinstance(hand_review_artifact, dict) else hand_review_artifact
        hand_review_exists = hand_review_artifact.get("exists") if isinstance(hand_review_artifact, dict) else None
        selector_replay_path = selector_replay_artifact.get("path") if isinstance(selector_replay_artifact, dict) else selector_replay_artifact
        selector_replay_exists = selector_replay_artifact.get("exists") if isinstance(selector_replay_artifact, dict) else None
        lines.extend(
            [
                f"- `{label}` state `{launch.get('state')}` / plan `{launch.get('plan_overall')}` / source `{launch.get('source') or 'legacy'}` / key `{launch.get('key')}`",
                f"  - failed plan checks: `{[item.get('name') for item in failed_plan]}`",
                f"  - frozen checkpoint: iter `{launch.get('frozen_iteration') or ((launch.get('checkpoint') or {}).get('iteration'))}` / hands `{launch.get('frozen_hands') or ((launch.get('checkpoint') or {}).get('total_hands'))}`",
                f"  - preflight: `{result.get('preflight_overall')}` `{result.get('preflight_json')}`",
                f"  - orchestrator log: `{result.get('orchestrator_log')}`",
                f"  - CI artifact: `{ci_path}`",
                f"  - promotion artifact: `{promotion_path}`",
                f"  - dump artifact: `{dump_path}` exists `{dump_exists}` dumps `{dump_count}`",
                f"  - artifact audit: `{audit_path}` exists `{audit_exists}`",
                f"  - hand review: `{hand_review_path}` exists `{hand_review_exists}`",
                f"  - selector replay: `{selector_replay_path}` exists `{selector_replay_exists}`",
            ]
        )
        ci = result.get("ci")
        if ci:
            lines.append(
                f"  - CI result: hands `{ci.get('hands')}`, bb/100 `{ci.get('bb_per_100')}`, lower `{ci.get('lower_bound_bb_per_100')}`, level `{ci.get('milestone_level')}`"
            )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a V5 run dashboard.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models", help="Directory containing Slumbot benchmark artifacts.")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_summary(Path(args.run_dir), Path(args.output_dir))
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
