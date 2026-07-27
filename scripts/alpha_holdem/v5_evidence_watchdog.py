#!/usr/bin/env python3
"""Read-only watchdog for V5 evidence quality.

This answers operational questions that are easy to conflate:
- is training alive and healthy?
- are scheduled tests producing evidence?
- is the latest model proven better?
- are we allowed to claim V4/L5/L6 strength?

It never starts or stops training and never launches benchmarks.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_baseline_gap import build_baseline_gap
from v5_run_dashboard import build_summary, format_duration
from v5_scorecard import build_scorecard
from v5_trend_ledger import build_trend_ledger


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now_utc().isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} root is not an object"}


def file_age_seconds(path: Path) -> float | None:
    if not path.exists():
        return None
    try:
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    except OSError:
        return None
    return max(0.0, (now_utc() - mtime).total_seconds())


def pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def age_status(path: Path, max_age_seconds: float) -> dict[str, Any]:
    age = file_age_seconds(path)
    if age is None:
        return {"path": str(path), "age_seconds": None, "status": "MISSING"}
    status = "PASS" if age <= max_age_seconds else "STALE"
    return {
        "path": str(path),
        "age_seconds": round(age, 3),
        "age": format_duration(age),
        "status": status,
    }


def latest_internal_status_path(run_dir: Path) -> Path:
    paths = [path for path in run_dir.glob("internal_strength_watch*_status.json") if path.exists()]
    if not paths:
        return run_dir / "internal_strength_watch_status.json"
    return max(paths, key=lambda path: path.stat().st_mtime)


def add_check(checks: list[dict[str, Any]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def load_latest_selector_pair_status(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    records: list[tuple[float, str, float, Path, dict[str, Any]]] = []
    for path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = load_json(path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        frozen_hands = pick(status, "frozen_summary", "total_hands")
        frozen_sort = float(frozen_hands) if isinstance(frozen_hands, (int, float)) else -1.0
        checked_at = str(status.get("checked_at") or "")
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        records.append((frozen_sort, checked_at, mtime, path, status))
    if not records:
        path = run_dir / "slumbot_selector_pair_75M_status.json"
        return path, load_json(path)
    records.sort(key=lambda item: (item[0], item[1], item[2]))
    _, _, _, selected_path, selected_status = records[-1]
    return selected_path, selected_status


def selector_pair_token(path: Path) -> str:
    name = path.name
    prefix = "slumbot_selector_pair_"
    suffix = "_status.json"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    return path.stem


def load_active_selector_pair_status(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    records: list[tuple[str, float, Path, dict[str, Any]]] = []
    for path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = load_json(path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        if status.get("state") == "PASS":
            continue
        checked_at = str(status.get("checked_at") or "")
        try:
            mtime = path.stat().st_mtime
        except OSError:
            mtime = 0.0
        records.append((checked_at, mtime, path, status))
    if not records:
        path = run_dir / "slumbot_selector_pair_active_status.json"
        return path, {"_missing": True, "_path": str(path)}
    _, _, selected_path, selected_status = sorted(records, key=lambda item: (item[0], item[1]))[-1]
    return selected_path, selected_status


def build_watchdog(run_dir: Path, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    dashboard = build_summary(run_dir, output_dir)
    scorecard = build_scorecard(run_dir, output_dir)
    baseline = build_baseline_gap(run_dir, output_dir)
    trend = build_trend_ledger(run_dir, output_dir)
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    cutover = load_json(run_dir / "v5_cutover_decision.json")
    l6 = load_json(run_dir / "v5_l6_status_brief.json")
    selector_pair_path, selector_pair = load_latest_selector_pair_status(run_dir)
    active_selector_pair_path, active_selector_pair = load_active_selector_pair_status(run_dir)

    health = pick(dashboard, "health", "overall")
    latest = pick(dashboard, "training", "latest", default={}) or {}
    live_iteration = latest.get("iteration")
    live_hands = pick(dashboard, "training", "current_hands")
    log_age = pick(dashboard, "training", "log_age_seconds")
    latest_gate_pass = pick(dashboard, "gates", "latest_pass", default={}) or {}
    next_gate_pending = pick(dashboard, "gates", "next_pending", default={}) or {}
    watchers = dashboard.get("watchers") if isinstance(dashboard.get("watchers"), dict) else {}

    internal = watchers.get("internal_strength") if isinstance(watchers.get("internal_strength"), dict) else {}
    l6_next_evidence = l6.get("next_evidence") if isinstance(l6.get("next_evidence"), dict) else {}
    internal_latest_target = l6_next_evidence.get("internal_probe_target") or internal.get("latest_target")
    internal_latest_overall = l6_next_evidence.get("internal_probe_state") or internal.get("latest_overall")
    internal_latest_verdict = l6_next_evidence.get("internal_probe_verdict")
    latest_quick5k = watchers.get("slumbot_quick5k_latest")
    legacy_quick5k = watchers.get("slumbot_quick5k_launch")
    if isinstance(latest_quick5k, dict) and latest_quick5k:
        quick5k = latest_quick5k
    elif isinstance(legacy_quick5k, dict):
        quick5k = legacy_quick5k
    else:
        quick5k = {}
    promotion20k = (
        watchers.get("slumbot_promotion20k_launch")
        if isinstance(watchers.get("slumbot_promotion20k_launch"), dict)
        else {}
    )
    formal100k = (
        watchers.get("slumbot_formal100k_launch")
        if isinstance(watchers.get("slumbot_formal100k_launch"), dict)
        else {}
    )
    eval_watch = watchers.get("eval_cadence_watch") if isinstance(watchers.get("eval_cadence_watch"), dict) else {}
    selector_pair_age = file_age_seconds(selector_pair_path)
    selector_pair_state = selector_pair.get("state")
    selector_pair_readiness = selector_pair.get("readiness_by_policy") if isinstance(selector_pair.get("readiness_by_policy"), dict) else {}
    active_selector_pair_state = active_selector_pair.get("state")
    active_selector_pair_age = file_age_seconds(active_selector_pair_path)
    active_selector_pair_readiness = (
        active_selector_pair.get("readiness_by_policy")
        if isinstance(active_selector_pair.get("readiness_by_policy"), dict)
        else {}
    )
    selector_pair_max_age = float(getattr(args, "max_selector_pair_status_age_seconds", 900.0))

    latest_slumbot = baseline.get("latest_slumbot") or {}
    baseline_cmp = baseline.get("baseline_comparison") or {}
    claim_rules = baseline.get("claim_rules") or {}
    gap = baseline.get("gap") or {}
    latest_better = scorecard.get("is_latest_training_better") or {}
    trend_direction = trend.get("direction") or {}
    next_external = cadence.get("next_external_eval") if isinstance(cadence.get("next_external_eval"), dict) else {}
    next_promotion = cadence.get("next_promotion_eval") if isinstance(cadence.get("next_promotion_eval"), dict) else {}
    next_formal = cadence.get("next_formal_eval") if isinstance(cadence.get("next_formal_eval"), dict) else {}

    checks: list[dict[str, Any]] = []

    if health == "PASS":
        health_status = "PASS"
    elif health == "WARN":
        health_status = "WARN"
    else:
        health_status = "BLOCK"
    add_check(checks, "training_health", health_status, f"health={health}")
    log_status = "PASS" if log_age is not None and float(log_age) <= args.max_log_age_seconds else "BLOCK"
    add_check(checks, "training_log_fresh", log_status, f"log_age={format_duration(log_age) if log_age is not None else 'missing'}")

    gate_status = "PASS" if latest_gate_pass else "WARN"
    gate_detail = (
        f"latest_pass={latest_gate_pass.get('target_iteration')}; "
        f"next_pending={next_gate_pending.get('target_iteration')}"
    )
    add_check(checks, "gate_cadence", gate_status, gate_detail)

    internal_age = internal.get("status_age_seconds")
    internal_age_ok = internal_age is not None and float(internal_age) <= args.max_internal_status_age_seconds
    internal_status = "PASS" if internal_age_ok else "WARN"
    add_check(
        checks,
        "internal_probe_watch",
        internal_status,
        (
            f"latest_target={internal_latest_target}; "
            f"latest_overall={internal_latest_overall}; "
            f"verdict={internal_latest_verdict}; "
            f"age={format_duration(internal_age) if internal_age is not None else 'missing'}"
        ),
    )

    cadence_state = next_external.get("state")
    cadence_status = "PASS" if cadence_state in {"WAITING", "DUE", "DONE"} else "WARN"
    add_check(
        checks,
        "external_eval_cadence",
        cadence_status,
        f"next={next_external.get('target_hands')}; state={cadence_state}; eta={next_external.get('eta_duration_live')}",
    )

    quick_state = quick5k.get("state")
    promotion_state = promotion20k.get("state")
    formal_state = formal100k.get("state")
    quick_status = "PASS" if quick_state in {"PASS", "WAITING", "RUNNING", "DUE", "DRY_RUN_READY"} else "WARN"
    add_check(
        checks,
        "slumbot_watchers",
        quick_status,
        (
            f"quick5k={quick_state}"
            f"/{quick5k.get('source') or 'legacy'}"
            f"/{quick5k.get('key')}; "
            f"promotion20k={promotion_state}; formal100k={formal_state}"
        ),
    )

    eval_watch_status = "PASS"
    eval_watch_detail = (
        f"launchable={eval_watch.get('launchable_key')}; "
        f"completed={eval_watch.get('completed_keys')}; failed={eval_watch.get('failed_keys')}"
    )
    if eval_watch.get("failed_keys"):
        eval_watch_status = "WARN"
    add_check(checks, "eval_cadence_watch", eval_watch_status, eval_watch_detail)

    selector_pair_age_ok = (
        selector_pair_state == "PASS"
        or (selector_pair_age is not None and float(selector_pair_age) <= selector_pair_max_age)
    )
    selector_pair_state_ok = selector_pair_state in {"WAITING", "READY", "RUNNING", "PASS"}
    selector_pair_status = "PASS" if selector_pair_age_ok and selector_pair_state_ok else "WARN"
    selector_pair_detail = (
        f"state={selector_pair_state}; "
        f"age={format_duration(selector_pair_age) if selector_pair_age is not None else 'missing'}; "
        f"readiness={selector_pair_readiness}; "
        f"delta={selector_pair.get('delta_callguard_vs_greedy_bb_per_100')}"
    )
    add_check(checks, "selector_pair_diagnostic", selector_pair_status, selector_pair_detail)

    if not active_selector_pair.get("_missing") and not active_selector_pair.get("_load_error"):
        active_selector_pair_state_ok = active_selector_pair_state in {"WAITING", "READY", "RUNNING"}
        active_selector_pair_age_ok = active_selector_pair_age is not None and float(active_selector_pair_age) <= selector_pair_max_age
        active_selector_pair_status = "PASS" if active_selector_pair_state_ok and active_selector_pair_age_ok else "WARN"
        if active_selector_pair_state == "FAIL":
            active_selector_pair_status = "WARN"
        active_checkpoint = pick(active_selector_pair, "plans", "greedy", "checkpoint", default={}) or {}
        active_min_hands = pick(active_selector_pair, "plans", "greedy", "min_training_hands")
        add_check(
            checks,
            "active_selector_pair_diagnostic",
            active_selector_pair_status,
            (
                f"token={selector_pair_token(active_selector_pair_path)}; "
                f"state={active_selector_pair_state}; "
                f"age={format_duration(active_selector_pair_age) if active_selector_pair_age is not None else 'missing'}; "
                f"checkpoint={active_checkpoint.get('iteration')}/{active_checkpoint.get('total_hands')}; "
                f"min_hands={active_min_hands}; readiness={active_selector_pair_readiness}"
            ),
        )

    slumbot_hands = int(latest_slumbot.get("hands") or 0)
    slumbot_bb100 = latest_slumbot.get("bb_per_100")
    slumbot_lower = latest_slumbot.get("lower_bound_bb_per_100")
    if claim_rules.get("can_claim_l6"):
        strength_status = "L6_PROVEN"
    elif claim_rules.get("can_claim_l5"):
        strength_status = "L5_PROVEN"
    elif claim_rules.get("can_claim_stronger_than_v4"):
        strength_status = "BASELINE_PROVEN"
    else:
        strength_status = "UNPROVEN"
    add_check(
        checks,
        "strength_claim",
        "PASS" if strength_status in {"L5_PROVEN", "L6_PROVEN"} else "BLOCK",
        f"status={strength_status}; hands={slumbot_hands}; bb100={fmt(slumbot_bb100)}; lower={fmt(slumbot_lower)}",
    )

    better_answer = latest_better.get("answer")
    better_status = "PASS" if better_answer in {"LATEST_STRONGER_BY_SLUMBOT_CI", "FORMAL_L5_OR_L6"} else "BLOCK"
    add_check(checks, "latest_better", better_status, f"answer={better_answer}")

    direction_answer = trend_direction.get("answer")
    trend_status = "PASS" if trend_direction.get("claim_allowed") else "WARN"
    add_check(checks, "trend_claim", trend_status, f"answer={direction_answer}; claim_allowed={trend_direction.get('claim_allowed')}")

    cutover_decision = cutover.get("decision")
    cutover_status = "PASS" if cutover_decision == "WAIT_FOR_TARGET" else "WARN"
    if cutover_decision in {"HOLD_NO_CUTOVER", "REVIEW_CUTOVER"}:
        cutover_status = "WARN"
    add_check(
        checks,
        "optimization_decision",
        cutover_status,
        f"decision={cutover_decision}; target={cutover.get('target_iteration')}",
    )

    statuses = {item["status"] for item in checks}
    if health not in {"PASS", "WARN"} or "MISSING" in statuses:
        overall = "EVIDENCE_SYSTEM_ATTENTION"
    elif strength_status == "L6_PROVEN":
        overall = "L6_PROVEN"
    elif strength_status == "L5_PROVEN":
        overall = "L5_PROVEN"
    elif "BLOCK" in statuses:
        overall = "EVIDENCE_ACTIVE_STRENGTH_UNPROVEN"
    elif "WARN" in statuses:
        overall = "EVIDENCE_ACTIVE_WITH_WARNINGS"
    else:
        overall = "EVIDENCE_ACTIVE"

    if active_selector_pair_state == "RUNNING":
        next_action = "Let the active selector pair diagnostic finish, then compare greedy vs callguard before changing training."
    elif active_selector_pair_state == "READY":
        next_action = "Let the active selector pair watcher freeze the checkpoint and run the planned diagnostic."
    elif active_selector_pair_state == "FAIL":
        next_action = "Inspect the active selector pair diagnostic failure before trusting the testing cadence."
    elif selector_pair_state == "RUNNING":
        next_action = "Let the latest selector pair diagnostic finish, then compare greedy vs callguard before changing training."
    elif selector_pair_state == "FAIL":
        next_action = "Inspect the latest selector pair diagnostic failure before trusting the testing cadence."
    elif cutover_decision == "WAIT_FOR_TARGET":
        next_action = "Keep the current trainer running until the planned gate/probe target."
    elif next_external.get("state") == "DUE":
        next_action = "Run the due Slumbot screen before making a strength claim."
    elif health not in {"PASS", "WARN"}:
        next_action = "Stop optimization decisions and inspect training health first."
    else:
        next_action = "Continue collecting scheduled evidence; do not promote without Slumbot CI."

    selector_pair_age_summary = age_status(selector_pair_path, selector_pair_max_age)
    if selector_pair_state == "PASS" and selector_pair_age_summary.get("status") == "STALE":
        selector_pair_age_summary = dict(selector_pair_age_summary)
        selector_pair_age_summary["status"] = "PASS"
        selector_pair_age_summary["note"] = "completed selector-pair diagnostics are historical evidence; age is not a freshness failure"

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "overall": overall,
        "strength_answer": baseline_cmp.get("answer"),
        "strength_status": strength_status,
        "latest_better_answer": better_answer,
        "trend_answer": direction_answer,
        "trend_claim_allowed": trend_direction.get("claim_allowed"),
        "latest_slumbot_hands": slumbot_hands,
        "latest_slumbot_bb_per_100": slumbot_bb100,
        "latest_slumbot_ci_lower": slumbot_lower,
        "latest_slumbot_milestone_level": latest_slumbot.get("milestone_level"),
        "can_claim_stronger_than_v4": claim_rules.get("can_claim_stronger_than_v4"),
        "can_claim_l5": claim_rules.get("can_claim_l5"),
        "can_claim_l6": claim_rules.get("can_claim_l6"),
        "next_action": next_action,
        "training": {
            "health": health,
            "live_iteration": live_iteration,
            "live_hands": live_hands,
            "log_age_seconds": log_age,
            "recent_hps": pick(dashboard, "training", "recent_hands_per_second"),
        },
        "cadence": {
            "latest_gate_pass": latest_gate_pass.get("target_iteration"),
            "next_gate_pending": next_gate_pending.get("target_iteration"),
            "internal_latest_target": internal_latest_target,
            "internal_latest_overall": internal_latest_overall,
            "internal_latest_verdict": internal_latest_verdict,
            "next_external_eval": next_external,
            "next_promotion_eval": next_promotion,
            "next_formal_eval": next_formal,
            "selector_pair_diagnostic": {
                "state": selector_pair_state,
                "age_seconds": selector_pair_age,
                "readiness_by_policy": selector_pair_readiness,
                "planned_hands_per_policy": selector_pair.get("planned_hands_per_policy"),
                "frozen_iteration": pick(selector_pair, "frozen_summary", "iteration"),
                "frozen_hands": pick(selector_pair, "frozen_summary", "total_hands"),
                "delta_callguard_vs_greedy_bb_per_100": selector_pair.get("delta_callguard_vs_greedy_bb_per_100"),
            },
            "active_selector_pair_diagnostic": {
                "state": active_selector_pair_state,
                "token": selector_pair_token(active_selector_pair_path) if not active_selector_pair.get("_missing") else None,
                "path": str(active_selector_pair_path) if not active_selector_pair.get("_missing") else None,
                "age_seconds": active_selector_pair_age,
                "readiness_by_policy": active_selector_pair_readiness,
                "planned_hands_per_policy": active_selector_pair.get("planned_hands_per_policy"),
                "checkpoint_iteration": pick(active_selector_pair, "plans", "greedy", "checkpoint", "iteration"),
                "checkpoint_hands": pick(active_selector_pair, "plans", "greedy", "checkpoint", "total_hands"),
                "min_training_hands": pick(active_selector_pair, "plans", "greedy", "min_training_hands"),
            },
        },
        "slumbot_strength": {
            "status": strength_status,
            "hands": slumbot_hands,
            "bb_per_100": slumbot_bb100,
            "ci_lower": slumbot_lower,
            "milestone_level": latest_slumbot.get("milestone_level"),
            "baseline_answer": baseline_cmp.get("answer"),
            "can_claim_stronger_than_v4": claim_rules.get("can_claim_stronger_than_v4"),
            "can_claim_l5": claim_rules.get("can_claim_l5"),
            "can_claim_l6": claim_rules.get("can_claim_l6"),
            "gap_to_l6_bb100": gap.get("to_l6_target_bb100"),
        },
        "learning_direction": {
            "latest_better": better_answer,
            "trend": direction_answer,
            "trend_claim_allowed": trend_direction.get("claim_allowed"),
        },
        "watcher_ages": {
            "dashboard": age_status(run_dir / "v5_dashboard_watch_status.json", args.max_dashboard_age_seconds),
            "health": age_status(run_dir / "health_status.json", args.max_health_age_seconds),
            "internal_strength": age_status(latest_internal_status_path(run_dir), args.max_internal_status_age_seconds),
            "eval_cadence": age_status(run_dir / "v5_eval_cadence.json", args.max_cadence_age_seconds),
            "selector_pair": selector_pair_age_summary,
            "active_selector_pair": age_status(active_selector_pair_path, selector_pair_max_age),
            "cutover": age_status(run_dir / "v5_cutover_decision.json", args.max_cadence_age_seconds),
        },
        "cutover": {
            "decision": cutover_decision,
            "target_iteration": cutover.get("target_iteration"),
            "intervention_overall": cutover.get("intervention_overall"),
        },
        "checks": checks,
        "claim_rule": "V4/L5/L6 strength is not proven by training health, self-play, or 5k Slumbot. L5 needs 100k+ Slumbot hands with bb/100 > 0 and CI lower > 0; L6 also needs near +11.1 bb/100.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    training = summary["training"]
    cadence = summary["cadence"]
    strength = summary["slumbot_strength"]
    direction = summary["learning_direction"]
    cutover = summary["cutover"]
    active_selector = (
        cadence.get("active_selector_pair_diagnostic")
        if isinstance(cadence.get("active_selector_pair_diagnostic"), dict)
        else {}
    )
    lines = [
        "# V5 Evidence Watchdog",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Next action: {summary['next_action']}",
        "",
        "Training:",
        "",
        f"- Health: `{training['health']}`",
        f"- Iteration / hands: `{training['live_iteration']}` / `{training['live_hands']}`",
        f"- Recent h/s: `{fmt(training['recent_hps'])}`",
        f"- Log age: `{format_duration(training['log_age_seconds']) if training['log_age_seconds'] is not None else 'missing'}`",
        "",
        "Testing cadence:",
        "",
        f"- Latest gate PASS: `{cadence['latest_gate_pass']}`",
        f"- Next gate pending: `{cadence['next_gate_pending']}`",
        f"- Internal probe latest: target `{cadence['internal_latest_target']}`, overall `{cadence['internal_latest_overall']}`, verdict `{cadence.get('internal_latest_verdict')}`",
        f"- Selector pair diagnostic: `{pick(cadence, 'selector_pair_diagnostic', 'state')}`; readiness `{pick(cadence, 'selector_pair_diagnostic', 'readiness_by_policy')}`; delta `{fmt(pick(cadence, 'selector_pair_diagnostic', 'delta_callguard_vs_greedy_bb_per_100'))}`",
        f"- Active selector pair diagnostic: `{active_selector.get('state')}`; token `{active_selector.get('token')}`; readiness `{active_selector.get('readiness_by_policy')}`; checkpoint `{active_selector.get('checkpoint_iteration')}` / `{active_selector.get('checkpoint_hands')}`; min hands `{active_selector.get('min_training_hands')}`",
        f"- Next Slumbot external eval: `{pick(cadence, 'next_external_eval', 'target_hands')}` hands, `{pick(cadence, 'next_external_eval', 'state')}`, ETA `{pick(cadence, 'next_external_eval', 'eta_duration_live')}`",
        f"- Next promotion / formal eval: `{pick(cadence, 'next_promotion_eval', 'target_hands')}` / `{pick(cadence, 'next_formal_eval', 'target_hands')}` hands",
        "",
        "Strength:",
        "",
        f"- Status: `{strength['status']}`",
        f"- Slumbot hands / bb100 / lower: `{strength['hands']}` / `{fmt(strength['bb_per_100'])}` / `{fmt(strength['ci_lower'])}`",
        f"- Milestone: `{strength['milestone_level']}`",
        f"- Baseline answer: `{strength['baseline_answer']}`",
        f"- Can claim stronger than V4 / L5 / L6: `{strength['can_claim_stronger_than_v4']}` / `{strength['can_claim_l5']}` / `{strength['can_claim_l6']}`",
        f"- Gap to L6 bb/100: `{fmt(strength['gap_to_l6_bb100'])}`",
        "",
        "Direction:",
        "",
        f"- Latest better: `{direction['latest_better']}`",
        f"- Trend: `{direction['trend']}`",
        f"- Trend claim allowed: `{direction['trend_claim_allowed']}`",
        "",
        "Optimization:",
        "",
        f"- Cutover decision / target: `{cutover['decision']}` / `{cutover['target_iteration']}`",
        f"- Intervention state: `{cutover['intervention_overall']}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.extend(["", "Claim rule:", "", f"- {summary['claim_rule']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only V5 evidence watchdog report.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--max-log-age-seconds", type=float, default=600.0)
    parser.add_argument("--max-dashboard-age-seconds", type=float, default=900.0)
    parser.add_argument("--max-health-age-seconds", type=float, default=900.0)
    parser.add_argument("--max-internal-status-age-seconds", type=float, default=3600.0)
    parser.add_argument("--max-cadence-age-seconds", type=float, default=1800.0)
    parser.add_argument("--max-selector-pair-status-age-seconds", type=float, default=900.0)
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    summary = build_watchdog(run_dir, Path(args.output_dir), args)
    print(f"overall={summary['overall']}")
    print(f"next_action={summary['next_action']}")
    print(f"strength={summary['slumbot_strength']['status']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
