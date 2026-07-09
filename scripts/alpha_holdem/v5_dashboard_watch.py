#!/usr/bin/env python3
"""Periodically refresh the V5 run dashboard.

This watcher is read-only with respect to training. It optionally refreshes
progress_status.json via v5_progress.py, then rewrites the consolidated
dashboard JSON/Markdown.
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

from v5_run_dashboard import build_summary, write_markdown
from v5_baseline_gap import build_baseline_gap, write_markdown as write_baseline_gap_markdown
from v5_eval_cadence import build_cadence, write_markdown as write_eval_cadence_markdown
from v5_scorecard import build_scorecard, write_markdown as write_scorecard_markdown
from v5_throughput_audit import build_summary as build_throughput_audit
from v5_throughput_audit import write_markdown as write_throughput_audit_markdown
from v5_trend_ledger import build_trend_ledger, write_markdown as write_trend_ledger_markdown
from v5_preflop_policy_probe import build_summary as build_preflop_probe
from v5_preflop_policy_probe import write_markdown as write_preflop_probe_markdown
from v5_l6_status_brief import build_summary as build_l6_status_brief
from v5_l6_status_brief import write_markdown as write_l6_status_brief_markdown
from v5_cutover_decision import decide as build_cutover_decision
from v5_cutover_decision import write_markdown as write_cutover_decision_markdown
from v5_evidence_watchdog import build_watchdog as build_evidence_watchdog
from v5_evidence_watchdog import write_markdown as write_evidence_watchdog_markdown
from v5_next_action_queue import build_queue as build_next_action_queue
from v5_next_action_queue import write_markdown as write_next_action_queue_markdown
from v5_health_warning_diagnosis import build_diagnosis as build_health_warning_diagnosis
from v5_health_warning_diagnosis import write_markdown as write_health_warning_diagnosis_markdown
from v5_checkpoint_delta import build_delta as build_checkpoint_delta
from v5_checkpoint_delta import write_markdown as write_checkpoint_delta_markdown
from v5_l6_speed_decision import build_speed_decision as build_l6_speed_decision
from v5_l6_speed_decision import write_markdown as write_l6_speed_decision_markdown
from v5_throughput_sweep_plan import evaluate as build_throughput_sweep_plan
from v5_throughput_sweep_plan import write_markdown as write_throughput_sweep_plan_markdown
from v5_l6_claim_audit import build_audit as build_l6_claim_audit
from v5_l6_claim_audit import write_markdown as write_l6_claim_audit_markdown
from v5_checkpoint_promotion_decision import build_decision as build_checkpoint_promotion_decision
from v5_checkpoint_promotion_decision import write_markdown as write_checkpoint_promotion_decision_markdown
from v5_post_gate_review import build_review as build_post_gate_review
from v5_post_gate_review import write_markdown as write_post_gate_review_markdown

POST_GATE_REFRESH_STATES = {"PENDING_EVIDENCE", "DUE_EVIDENCE_REFRESH"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001 - watcher status should survive malformed artifacts.
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} root is not an object", "_path": str(path)}


def finite_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def remaining_to_target(target_hands: Any, current_hands: Any) -> int | None:
    target = finite_int(target_hands)
    current = finite_int(current_hands)
    if target is None or current is None:
        return None
    return max(0, target - current)


def cadence_min_quick_target(run_dir: Path) -> int:
    values = [50_000_000]
    eval_cadence_watch = load_json(run_dir / "v5_eval_cadence_watch_status.json")
    watch_min = finite_int(eval_cadence_watch.get("min_quick_target_hands"))
    if watch_min and watch_min > 0:
        values.append(watch_min)

    quick5k_status = load_json(run_dir / "slumbot_quick5k_launch_status.json")
    plan = quick5k_status.get("plan") if isinstance(quick5k_status.get("plan"), dict) else {}
    if str(plan.get("stage") or "") == "quick5k":
        launcher_min = finite_int(plan.get("min_training_hands"))
        if launcher_min and launcher_min > 0:
            values.append(launcher_min)
    return max(values)


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def normalize_preflop_probe_summary(summary: dict[str, Any]) -> dict[str, Any]:
    checkpoint = summary.get("checkpoint") if isinstance(summary.get("checkpoint"), dict) else {}
    if summary.get("checkpoint_iteration") is None:
        summary["checkpoint_iteration"] = checkpoint.get("iteration")
    if summary.get("checkpoint_hands") is None:
        summary["checkpoint_hands"] = checkpoint.get("total_hands")
    if summary.get("warning_count") is None:
        summary["warning_count"] = len(summary.get("warnings") or [])
    if summary.get("failure_count") is None:
        summary["failure_count"] = len(summary.get("failures") or [])
    return summary


def post_gate_needs_refresh(run_dir: Path, target_iteration: Any) -> bool:
    if target_iteration is None:
        return False
    try:
        target = int(target_iteration)
    except (TypeError, ValueError):
        return False
    review = load_json(run_dir / f"v5_post_gate_review_{target}.json")
    return bool(review.get("_missing") or review.get("overall") in POST_GATE_REFRESH_STATES)


def latest_completed_post_gate_review(run_dir: Path) -> dict[str, Any]:
    latest_target: int | None = None
    latest_review: dict[str, Any] = {}
    for path in run_dir.glob("v5_post_gate_review_*.json"):
        try:
            target = int(path.stem.rsplit("_", 1)[-1])
        except ValueError:
            continue
        review = load_json(path)
        if review.get("_missing") or review.get("_load_error"):
            continue
        overall = review.get("overall")
        if not overall or overall in POST_GATE_REFRESH_STATES:
            continue
        if latest_target is None or target > latest_target:
            latest_target = target
            latest_review = review
    return latest_review


def load_gate_detail(gate_summary: Any) -> dict[str, Any]:
    if not isinstance(gate_summary, dict):
        return {}
    path = gate_summary.get("path")
    if path:
        return load_json(Path(path))
    return {}


def build_gate_aliases(prefix: str, gate_summary: dict[str, Any], gate_detail: dict[str, Any]) -> dict[str, Any]:
    def value(key: str) -> Any:
        detail_value = gate_detail.get(key)
        if detail_value is not None:
            return detail_value
        return gate_summary.get(key)

    return {
        f"{prefix}_target_iteration": value("target_iteration"),
        f"{prefix}_overall": value("overall"),
        f"{prefix}_health_overall": value("health_overall"),
        f"{prefix}_live_iteration": value("live_iteration"),
        f"{prefix}_live_hands": value("live_hands"),
        f"{prefix}_checkpoint_iteration": value("checkpoint_iteration"),
        f"{prefix}_checkpoint_hands": value("checkpoint_hands"),
        f"{prefix}_remaining_live_iterations": value("remaining_live_iterations"),
        f"{prefix}_remaining_checkpoint_iterations": value("remaining_checkpoint_iterations"),
        f"{prefix}_age_seconds": gate_summary.get("age_seconds"),
    }


def build_slumbot_loss_trend_aliases(
    slumbot_loss_trend_item: dict[str, Any],
    official_loss_rows: list[Any],
) -> dict[str, Any]:
    rows = [row for row in official_loss_rows if isinstance(row, dict)]
    latest_official_loss = rows[-1] if rows else {}
    latest_official_loss_position = (
        latest_official_loss.get("position") if isinstance(latest_official_loss.get("position"), dict) else {}
    )
    latest_official_loss_terminal = (
        latest_official_loss.get("terminal") if isinstance(latest_official_loss.get("terminal"), dict) else {}
    )
    latest_official_loss_delta = (
        latest_official_loss.get("delta_vs_previous")
        if isinstance(latest_official_loss.get("delta_vs_previous"), dict)
        else {}
    )
    latest_bb100 = latest_official_loss.get("bb_per_100")
    latest_delta_bb100 = latest_official_loss_delta.get("bb_per_100")
    return {
        "slumbot_loss_trend_status": slumbot_loss_trend_item.get("status"),
        "slumbot_loss_trend_blocks_strength_claim": slumbot_loss_trend_item.get("blocks_strength_claim"),
        "slumbot_loss_trend_reason": slumbot_loss_trend_item.get("reason"),
        "slumbot_loss_trend_rows": len(rows),
        "slumbot_loss_trend_latest_bb100": latest_bb100,
        "slumbot_loss_trend_latest_bb_per_100": latest_bb100,
        "slumbot_loss_trend_latest_delta_bb100": latest_delta_bb100,
        "slumbot_loss_trend_latest_delta_bb_per_100": latest_delta_bb100,
        "slumbot_loss_trend_latest_sb_bb100": latest_official_loss_position.get("sb_bb100"),
        "slumbot_loss_trend_latest_bb_bb100": latest_official_loss_position.get("bb_bb100"),
        "slumbot_loss_trend_latest_hero_fold_bb100": latest_official_loss_terminal.get("hero_fold_bb100"),
        "slumbot_loss_trend_latest_showdown_bb100": latest_official_loss_terminal.get("showdown_bb100"),
    }


def build_slumbot_analysis_coverage_aliases(trend_ledger: dict[str, Any]) -> dict[str, Any]:
    coverage = (
        trend_ledger.get("slumbot_analysis_coverage")
        if isinstance(trend_ledger.get("slumbot_analysis_coverage"), dict)
        else {}
    )
    latest = coverage.get("latest") if isinstance(coverage.get("latest"), dict) else {}
    latest_complete = coverage.get("latest_complete") if isinstance(coverage.get("latest_complete"), dict) else {}
    return {
        "slumbot_analysis_coverage_overall": coverage.get("overall"),
        "slumbot_analysis_coverage_total_count": coverage.get("total_count"),
        "slumbot_analysis_coverage_complete_count": coverage.get("complete_count"),
        "slumbot_analysis_coverage_incomplete_count": coverage.get("incomplete_count"),
        "slumbot_analysis_coverage_latest_stage": latest.get("stage"),
        "slumbot_analysis_coverage_latest_milestone_m": latest.get("milestone_m"),
        "slumbot_analysis_coverage_latest_complete": latest.get("analysis_complete"),
        "slumbot_analysis_coverage_latest_missing_parts": latest.get("missing_parts") or [],
        "slumbot_analysis_coverage_latest_complete_milestone_m": latest_complete.get("milestone_m"),
        "slumbot_analysis_coverage_latest_complete_stage": latest_complete.get("stage"),
        "slumbot_analysis_coverage_latest_complete_bb100": latest_complete.get("bb_per_100"),
    }


def build_eval_cadence_watch_aliases(eval_cadence_watch: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(eval_cadence_watch, dict):
        eval_cadence_watch = {}
    preview = (
        eval_cadence_watch.get("next_external_plan_preview")
        if isinstance(eval_cadence_watch.get("next_external_plan_preview"), dict)
        else {}
    )
    failed_checks = eval_cadence_watch.get("next_external_plan_preview_failed_checks")
    if failed_checks is None:
        failed_checks = preview.get("failed_checks")
    return {
        "eval_cadence_watch_checked_at": eval_cadence_watch.get("checked_at"),
        "eval_cadence_watch_state": eval_cadence_watch.get("state") or eval_cadence_watch.get("overall"),
        "eval_cadence_watch_checkpoint_iteration": eval_cadence_watch.get("current_checkpoint_iteration")
        or eval_cadence_watch.get("checkpoint_iteration"),
        "eval_cadence_watch_checkpoint_hands": eval_cadence_watch.get("current_checkpoint_hands")
        or eval_cadence_watch.get("checkpoint_hands"),
        "eval_cadence_watch_live_hands": eval_cadence_watch.get("live_hands")
        or eval_cadence_watch.get("current_live_hands")
        or eval_cadence_watch.get("current_hands"),
        "next_external_plan_preview_status": eval_cadence_watch.get("next_external_plan_preview_status")
        or preview.get("status"),
        "next_external_plan_preview_key": preview.get("key"),
        "next_external_plan_preview_tag": preview.get("tag"),
        "next_external_plan_preview_json": eval_cadence_watch.get("next_external_plan_preview_json")
        or preview.get("out_json"),
        "next_external_plan_preview_md": eval_cadence_watch.get("next_external_plan_preview_md")
        or preview.get("out_md"),
        "next_external_plan_preview_overall": eval_cadence_watch.get("next_external_plan_preview_overall")
        or preview.get("overall"),
        "next_external_plan_preview_failed_checks": failed_checks if isinstance(failed_checks, list) else [],
        "next_external_plan_preview_checkpoint_iteration": preview.get("checkpoint_iteration"),
        "next_external_plan_preview_checkpoint_hands": preview.get("checkpoint_hands"),
    }


def refresh_progress(run_dir: Path, python: str) -> dict[str, Any]:
    proc = subprocess.run(
        [
            python,
            str(SCRIPT_DIR / "v5_progress.py"),
            "--run-dir",
            str(run_dir),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    return {
        "returncode": proc.returncode,
        "output_tail": proc.stdout[-2000:],
    }


def archive_preflop_probe(run_dir: Path, summary: dict[str, Any]) -> dict[str, str | None]:
    checkpoint = summary.get("checkpoint") or {}
    iteration = checkpoint.get("iteration")
    hands = checkpoint.get("total_hands")
    if iteration is None or hands is None:
        return {"archive_json": None, "archive_md": None}
    archive_dir = run_dir / "preflop_probe_history"
    stem = f"v5_preflop_probe_iter{int(iteration)}_{int(hands) // 1_000_000}M"
    archive_json = archive_dir / f"{stem}.json"
    archive_md = archive_dir / f"{stem}.md"
    write_json(archive_json, summary)
    write_preflop_probe_markdown(summary, archive_md)
    return {"archive_json": str(archive_json), "archive_md": str(archive_md)}


def refresh_preflop_probe(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    checkpoint = run_dir / "latest.pt"
    out_json = run_dir / "v5_preflop_probe_latest.json"
    out_md = run_dir / "v5_preflop_probe_latest.md"
    if not checkpoint.exists():
        return {"status": "SKIP", "reason": "latest.pt missing", "checkpoint": str(checkpoint)}
    if (
        out_json.exists()
        and out_md.exists()
        and out_json.stat().st_mtime >= checkpoint.stat().st_mtime
        and out_md.stat().st_mtime >= checkpoint.stat().st_mtime
    ):
        existing = normalize_preflop_probe_summary(json.loads(out_json.read_text(encoding="utf-8-sig")))
        write_json(out_json, existing)
        write_preflop_probe_markdown(existing, out_md)
        archived = archive_preflop_probe(run_dir, existing)
        return {
            "status": "CACHED",
            "overall": existing.get("overall"),
            "out_json": str(out_json),
            "out_md": str(out_md),
            "checkpoint_mtime": checkpoint.stat().st_mtime,
            **archived,
        }

    probe_args = argparse.Namespace(
        checkpoint=str(checkpoint),
        device=args.preflop_probe_device,
        batch_size=args.preflop_probe_batch_size,
        guarded_temperature=args.preflop_probe_guarded_temperature,
        guarded_allin_max_spr=args.preflop_probe_guarded_allin_max_spr,
        guarded_allin_min_prob=args.preflop_probe_guarded_allin_min_prob,
        callguard_min_prob=args.preflop_probe_callguard_min_prob,
        callguard_ratio=args.preflop_probe_callguard_ratio,
        callguard_include_open=args.preflop_probe_callguard_include_open,
    )
    try:
        summary = build_preflop_probe(probe_args)
        write_json(out_json, summary)
        write_preflop_probe_markdown(summary, out_md)
        archived = archive_preflop_probe(run_dir, summary)
        return {
            "status": "REFRESHED",
            "overall": summary.get("overall"),
            "out_json": str(out_json),
            "out_md": str(out_md),
            "checkpoint": summary.get("checkpoint"),
            **archived,
        }
    except Exception as exc:
        return {
            "status": "ERROR",
            "error": str(exc),
            "out_json": str(out_json),
            "out_md": str(out_md),
        }


def refresh_dashboard(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    progress_result = None
    if not args.no_refresh_progress:
        progress_result = refresh_progress(run_dir, args.python)
    preflop_probe_result = None
    if not args.no_preflop_probe:
        preflop_probe_result = refresh_preflop_probe(args, run_dir)

    summary = build_summary(run_dir, Path(args.output_dir))
    out_json = Path(args.out_json) if args.out_json else run_dir / "v5_run_dashboard.json"
    out_md = Path(args.out_md) if args.out_md else run_dir / "v5_run_dashboard.md"
    write_json(out_json, summary)
    write_markdown(summary, out_md)

    scorecard = build_scorecard(run_dir, Path(args.output_dir))
    scorecard_json = run_dir / "v5_scorecard.json"
    scorecard_md = run_dir / "v5_scorecard.md"
    write_json(scorecard_json, scorecard)
    write_scorecard_markdown(scorecard, scorecard_md)

    baseline_gap = build_baseline_gap(run_dir, Path(args.output_dir))
    baseline_gap_json = run_dir / "v5_baseline_gap.json"
    baseline_gap_md = run_dir / "v5_baseline_gap.md"
    write_json(baseline_gap_json, baseline_gap)
    write_baseline_gap_markdown(baseline_gap, baseline_gap_md)

    trend_ledger = build_trend_ledger(run_dir, Path(args.output_dir))
    trend_ledger_json = run_dir / "v5_trend_ledger.json"
    trend_ledger_md = run_dir / "v5_trend_ledger.md"
    write_json(trend_ledger_json, trend_ledger)
    write_trend_ledger_markdown(trend_ledger, trend_ledger_md)

    throughput_args = argparse.Namespace(
        tail=60,
        long_tail=240,
        min_rows=20,
        target_effective_hps=800.0,
        warn_effective_hps=650.0,
        ppo_share_warn=0.28,
        min_inf_bs_ratio_of_workers=0.45,
        gpu_util_warn=70.0,
        fast_inf_bs=18.0,
        no_gpu_snapshot=False,
    )
    throughput_audit = build_throughput_audit(run_dir, throughput_args)
    throughput_audit_json = run_dir / "v5_throughput_audit.json"
    throughput_audit_md = run_dir / "v5_throughput_audit.md"
    write_json(throughput_audit_json, throughput_audit)
    write_throughput_audit_markdown(throughput_audit, throughput_audit_md)

    throughput_sweep_args = argparse.Namespace(
        source_run_dir=str(run_dir),
        checkpoint="",
        output_root="tmp/v5_throughput_sweeps",
        workers="24,28,32",
        hands_per_iter="16384,32768",
        max_runtime_seconds=900.0,
        device="cuda",
        python=args.python,
        total_hands=2_700_000_000,
        postflop_action_prior_coef=None,
        postflop_action_prior_target="",
        preflop_action_prior_coef=None,
        preflop_action_prior_target="",
        compare_tail=20,
        min_baseline_rows=20,
        min_candidate_rows=20,
        min_hps_ratio=1.05,
        min_inf_bs_ratio=1.0,
        min_candidate_inf_bs=12.0,
        out_json="",
        out_md="",
    )
    throughput_sweep_plan = build_throughput_sweep_plan(throughput_sweep_args)
    throughput_sweep_plan_json = run_dir / "v5_throughput_sweep_plan.json"
    throughput_sweep_plan_md = run_dir / "v5_throughput_sweep_plan.md"
    write_json(throughput_sweep_plan_json, throughput_sweep_plan)
    write_throughput_sweep_plan_markdown(throughput_sweep_plan_md, throughput_sweep_plan)

    cadence_args = argparse.Namespace(
        quick_interval_hands=50_000_000,
        quick_until_hands=200_000_000,
        min_quick_target_hands=cadence_min_quick_target(run_dir),
        promotion_interval_hands=250_000_000,
        promotion_until_hands=1_000_000_000,
        min_promotion_target_hands=250_000_000,
        formal_interval_hands=250_000_000,
        formal_until_hands=1_000_000_000,
        min_formal_target_hands=250_000_000,
    )
    eval_cadence = build_cadence(run_dir, Path(args.output_dir), cadence_args)
    eval_cadence_json = run_dir / "v5_eval_cadence.json"
    eval_cadence_md = run_dir / "v5_eval_cadence.md"
    write_json(eval_cadence_json, eval_cadence)
    write_eval_cadence_markdown(eval_cadence, eval_cadence_md)
    eval_cadence_watch = load_json(run_dir / "v5_eval_cadence_watch_status.json")
    eval_cadence_watch_aliases = build_eval_cadence_watch_aliases(eval_cadence_watch)

    health_warning_args = argparse.Namespace(
        tail=20,
        long_tail=60,
        min_rows=10,
        preflop_allin_warn=0.12,
        preflop_allin_fail=0.25,
        preflop_allin_fail_mean=0.20,
        sustained_warn_fraction=0.50,
        preflop_call_warn=0.08,
        preflop_call_fail=0.03,
        postflop_ra_warn=0.72,
        postflop_ra_fail=0.88,
        postflop_ra_fail_mean=0.78,
        postflop_call_warn=0.08,
        entropy_warn=0.30,
        entropy_fail=0.10,
        value_loss_fail=50000.0,
        intervention_target_iteration=4400,
    )
    health_warning_diagnosis = build_health_warning_diagnosis(run_dir, health_warning_args)
    health_warning_diagnosis_json = run_dir / "v5_health_warning_diagnosis.json"
    health_warning_diagnosis_md = run_dir / "v5_health_warning_diagnosis.md"
    write_json(health_warning_diagnosis_json, health_warning_diagnosis)
    write_health_warning_diagnosis_markdown(health_warning_diagnosis, health_warning_diagnosis_md)

    checkpoint_delta = build_checkpoint_delta(run_dir)
    checkpoint_delta_json = run_dir / "v5_checkpoint_delta.json"
    checkpoint_delta_md = run_dir / "v5_checkpoint_delta.md"
    write_json(checkpoint_delta_json, checkpoint_delta)
    write_checkpoint_delta_markdown(checkpoint_delta, checkpoint_delta_md)

    l6_status_brief = build_l6_status_brief(run_dir)
    l6_status_brief_json = run_dir / "v5_l6_status_brief.json"
    l6_status_brief_md = run_dir / "v5_l6_status_brief.md"
    write_json(l6_status_brief_json, l6_status_brief)
    write_l6_status_brief_markdown(l6_status_brief_md, l6_status_brief)

    cutover_decision = build_cutover_decision(run_dir)
    cutover_decision_json = run_dir / "v5_cutover_decision.json"
    cutover_decision_md = run_dir / "v5_cutover_decision.md"
    write_json(cutover_decision_json, cutover_decision)
    write_cutover_decision_markdown(cutover_decision_md, cutover_decision)

    evidence_watchdog_args = argparse.Namespace(
        max_log_age_seconds=600.0,
        max_dashboard_age_seconds=900.0,
        max_health_age_seconds=900.0,
        max_internal_status_age_seconds=3600.0,
        max_cadence_age_seconds=1800.0,
    )
    evidence_watchdog = build_evidence_watchdog(run_dir, Path(args.output_dir), evidence_watchdog_args)
    evidence_watchdog_json = run_dir / "v5_evidence_watchdog.json"
    evidence_watchdog_md = run_dir / "v5_evidence_watchdog.md"
    write_json(evidence_watchdog_json, evidence_watchdog)
    write_evidence_watchdog_markdown(evidence_watchdog, evidence_watchdog_md)

    speed_decision_args = argparse.Namespace(
        target_hps="800,900",
        target_effective_hps=800.0,
    )
    l6_speed_decision = build_l6_speed_decision(run_dir, speed_decision_args)
    l6_speed_decision_json = run_dir / "v5_l6_speed_decision.json"
    l6_speed_decision_md = run_dir / "v5_l6_speed_decision.md"
    write_json(l6_speed_decision_json, l6_speed_decision)
    write_l6_speed_decision_markdown(l6_speed_decision, l6_speed_decision_md)

    l6_claim_audit = build_l6_claim_audit(run_dir, Path(args.output_dir))
    l6_claim_audit_json = run_dir / "v5_l6_claim_audit.json"
    l6_claim_audit_md = run_dir / "v5_l6_claim_audit.md"
    write_json(l6_claim_audit_json, l6_claim_audit)
    write_l6_claim_audit_markdown(l6_claim_audit, l6_claim_audit_md)

    checkpoint_promotion_decision = build_checkpoint_promotion_decision(run_dir, Path(args.output_dir))
    checkpoint_promotion_decision_json = run_dir / "v5_checkpoint_promotion_decision.json"
    checkpoint_promotion_decision_md = run_dir / "v5_checkpoint_promotion_decision.md"
    write_json(checkpoint_promotion_decision_json, checkpoint_promotion_decision)
    write_checkpoint_promotion_decision_markdown(checkpoint_promotion_decision, checkpoint_promotion_decision_md)

    l6_status_brief = build_l6_status_brief(run_dir)
    write_json(l6_status_brief_json, l6_status_brief)
    write_l6_status_brief_markdown(l6_status_brief_md, l6_status_brief)

    latest_pass_target = ((summary.get("gates", {}).get("latest_pass") or {}).get("target_iteration"))
    post_gate_candidates = []
    if post_gate_needs_refresh(run_dir, latest_pass_target):
        post_gate_candidates.append(int(latest_pass_target))
    post_gate_candidates.extend(
        int(target)
        for target in (
            ((summary.get("gates", {}).get("next_pending") or {}).get("target_iteration")),
            ((l6_status_brief.get("checkpoint") or {}).get("next_pending_target")),
            ((l6_status_brief.get("next_evidence") or {}).get("next_internal_probe_target")),
        )
        if target is not None
    )
    post_gate_target = (
        min(post_gate_candidates)
        if post_gate_candidates
        else ((summary.get("gates", {}).get("latest_pass") or {}).get("target_iteration"))
    )
    post_gate_review = build_post_gate_review(run_dir, post_gate_target)
    post_gate_review_target = post_gate_review.get("target_iteration") or "unknown"
    post_gate_review_json = run_dir / f"v5_post_gate_review_{post_gate_review_target}.json"
    post_gate_review_md = run_dir / f"v5_post_gate_review_{post_gate_review_target}.md"
    write_json(post_gate_review_json, post_gate_review)
    write_post_gate_review_markdown(post_gate_review, post_gate_review_md)
    latest_completed_post_gate = latest_completed_post_gate_review(run_dir)

    next_action_queue = build_next_action_queue(run_dir, Path(args.output_dir))
    next_action_queue_json = run_dir / "v5_next_action_queue.json"
    next_action_queue_md = run_dir / "v5_next_action_queue.md"
    write_json(next_action_queue_json, next_action_queue)
    write_next_action_queue_markdown(next_action_queue, next_action_queue_md)
    next_action_items = next_action_queue.get("queue") if isinstance(next_action_queue.get("queue"), list) else []
    next_action_first = next_action_items[0] if next_action_items and isinstance(next_action_items[0], dict) else {}
    slumbot_loss_trend_item = next(
        (
            entry
            for entry in next_action_items
            if isinstance(entry, dict) and entry.get("key") == "slumbot_loss_trend_latest"
        ),
        {},
    )
    official_loss_rows = trend_ledger.get("official_slumbot_loss_trend")
    official_loss_rows = official_loss_rows if isinstance(official_loss_rows, list) else []
    slumbot_loss_trend_aliases = build_slumbot_loss_trend_aliases(slumbot_loss_trend_item, official_loss_rows)
    slumbot_analysis_coverage_aliases = build_slumbot_analysis_coverage_aliases(trend_ledger)
    checkpoint = summary.get("checkpoint") if isinstance(summary.get("checkpoint"), dict) else {}
    run_dashboard_watchers = summary.get("watchers") if isinstance(summary.get("watchers"), dict) else {}
    run_dashboard_internal = (
        run_dashboard_watchers.get("internal_strength")
        if isinstance(run_dashboard_watchers.get("internal_strength"), dict)
        else {}
    )
    latest_training = (summary.get("training", {}).get("latest") or {})
    training_brief = l6_status_brief.get("training") if isinstance(l6_status_brief.get("training"), dict) else {}
    internal_brief = (
        l6_status_brief.get("internal_strength")
        if isinstance(l6_status_brief.get("internal_strength"), dict)
        else {}
    )
    gates_summary = summary.get("gates") if isinstance(summary.get("gates"), dict) else {}
    latest_gate_summary = gates_summary.get("latest_pass") if isinstance(gates_summary.get("latest_pass"), dict) else {}
    next_gate_summary = gates_summary.get("next_pending") if isinstance(gates_summary.get("next_pending"), dict) else {}
    gate_aliases: dict[str, Any] = {}
    gate_aliases.update(build_gate_aliases("latest_gate", latest_gate_summary, load_gate_detail(latest_gate_summary)))
    gate_aliases.update(build_gate_aliases("next_gate", next_gate_summary, load_gate_detail(next_gate_summary)))
    next_external_eval = (
        eval_cadence.get("next_external_eval")
        if isinstance(eval_cadence.get("next_external_eval"), dict)
        else {}
    )
    next_external_eval_stage = next_external_eval.get("stage")
    next_external_eval_target = next_external_eval.get("target_hands")
    next_external_eval_key = None
    if next_external_eval_stage and next_external_eval_target is not None:
        next_external_eval_key = f"{next_external_eval_stage}_{int(next_external_eval_target) // 1_000_000}M"
    next_external_remaining_checkpoint_hands = next_external_eval.get("remaining_checkpoint_hands")
    if next_external_remaining_checkpoint_hands is None:
        next_external_remaining_checkpoint_hands = remaining_to_target(
            next_external_eval_target,
            next_external_eval.get("checkpoint_hands") or checkpoint.get("total_hands"),
        )
    next_external_remaining_live_hands = next_external_eval.get("remaining_live_hands")
    if next_external_remaining_live_hands is None:
        next_external_remaining_live_hands = remaining_to_target(
            next_external_eval_target,
            next_external_eval.get("current_hands") or summary.get("training", {}).get("current_hands"),
        )

    return {
        "checked_at": now_iso(),
        "run_dashboard_checked_at": summary.get("checked_at"),
        "health_age_seconds": (summary.get("health") or {}).get("age_seconds"),
        "latest_gate_age_seconds": ((summary.get("gates", {}).get("latest_pass") or {}).get("age_seconds")),
        "next_gate_age_seconds": ((summary.get("gates", {}).get("next_pending") or {}).get("age_seconds")),
        "l6_status_brief_checked_at": l6_status_brief.get("checked_at"),
        "post_gate_review_checked_at": post_gate_review.get("checked_at"),
        "next_action_queue_checked_at": next_action_queue.get("checked_at"),
        "next_action_queue_overall": next_action_queue.get("overall"),
        "next_action_queue_recommendation": next_action_queue.get("recommendation"),
        "next_action_first_key": next_action_first.get("key"),
        "next_action_first_status": next_action_first.get("status"),
        "next_action_first_trigger": next_action_first.get("trigger"),
        "next_action_first_action": next_action_first.get("action"),
        "next_action_first_owner": next_action_first.get("owner"),
        "next_action_first_reason": next_action_first.get("reason"),
        "next_action_first_eta": next_action_first.get("eta"),
        "next_action_first_blocks_strength_claim": next_action_first.get("blocks_strength_claim"),
        "out_json": str(out_json),
        "out_md": str(out_md),
        "scorecard_json": str(scorecard_json),
        "scorecard_md": str(scorecard_md),
        "baseline_gap_json": str(baseline_gap_json),
        "baseline_gap_md": str(baseline_gap_md),
        "trend_ledger_json": str(trend_ledger_json),
        "trend_ledger_md": str(trend_ledger_md),
        "throughput_audit_json": str(throughput_audit_json),
        "throughput_audit_md": str(throughput_audit_md),
        "throughput_sweep_plan_json": str(throughput_sweep_plan_json),
        "throughput_sweep_plan_md": str(throughput_sweep_plan_md),
        "eval_cadence_json": str(eval_cadence_json),
        "eval_cadence_md": str(eval_cadence_md),
        "l6_status_brief_json": str(l6_status_brief_json),
        "l6_status_brief_md": str(l6_status_brief_md),
        "training": l6_status_brief.get("training"),
        "readiness": l6_status_brief.get("readiness"),
        "internal_strength": l6_status_brief.get("internal_strength"),
        "score_progression": l6_status_brief.get("score_progression"),
        "internal_latest_iteration": internal_brief.get("latest_iteration"),
        "internal_latest_hands": internal_brief.get("latest_hands"),
        "internal_latest_verdict": internal_brief.get("latest_verdict"),
        "internal_latest_delta_mean_bb100": internal_brief.get("latest_delta_mean_bb100"),
        "internal_latest_delta_lower_bb100": internal_brief.get("latest_delta_lower_bb100"),
        "internal_next_target": internal_brief.get("next_target"),
        "internal_next_state": internal_brief.get("next_state"),
        "internal_watch_selected_status_path": run_dashboard_internal.get("selected_status_path"),
        "internal_watch_status_paths": run_dashboard_internal.get("status_paths"),
        "internal_watch_status_age_seconds": run_dashboard_internal.get("status_age_seconds"),
        "internal_watch_latest_probe_target": run_dashboard_internal.get("latest_probe_target"),
        "internal_watch_next_target": run_dashboard_internal.get("next_target"),
        "internal_watch_next_overall": run_dashboard_internal.get("next_overall"),
        "strength_answer": l6_status_brief.get("strength_answer"),
        "cutover_decision_json": str(cutover_decision_json),
        "cutover_decision_md": str(cutover_decision_md),
        "evidence_watchdog_json": str(evidence_watchdog_json),
        "evidence_watchdog_md": str(evidence_watchdog_md),
        "health_warning_diagnosis_json": str(health_warning_diagnosis_json),
        "health_warning_diagnosis_md": str(health_warning_diagnosis_md),
        "checkpoint_delta_json": str(checkpoint_delta_json),
        "checkpoint_delta_md": str(checkpoint_delta_md),
        "next_action_queue_json": str(next_action_queue_json),
        "next_action_queue_md": str(next_action_queue_md),
        "l6_speed_decision_json": str(l6_speed_decision_json),
        "l6_speed_decision_md": str(l6_speed_decision_md),
        "l6_claim_audit_json": str(l6_claim_audit_json),
        "l6_claim_audit_md": str(l6_claim_audit_md),
        "checkpoint_promotion_decision_json": str(checkpoint_promotion_decision_json),
        "checkpoint_promotion_decision_md": str(checkpoint_promotion_decision_md),
        "post_gate_review_json": str(post_gate_review_json),
        "post_gate_review_md": str(post_gate_review_md),
        "progress_refresh": progress_result,
        "preflop_probe_refresh": preflop_probe_result,
        "health": summary.get("health", {}).get("overall"),
        "live_iteration": latest_training.get("iteration"),
        "live_hands": summary.get("training", {}).get("current_hands"),
        "checkpoint_iteration": checkpoint.get("iteration"),
        "checkpoint_hands": checkpoint.get("total_hands"),
        "recent_hands_per_second": summary.get("training", {}).get("recent_hands_per_second"),
        "brief_live_iteration": training_brief.get("live_iteration"),
        "brief_checkpoint_iteration": training_brief.get("checkpoint_iteration"),
        "brief_live_hands": training_brief.get("live_hands"),
        "brief_checkpoint_hands": training_brief.get("checkpoint_hands"),
        "latest_gate_pass": (summary.get("gates", {}).get("latest_pass") or {}).get("target_iteration"),
        "next_gate_pending": (summary.get("gates", {}).get("next_pending") or {}).get("target_iteration"),
        **gate_aliases,
        "slumbot_quick5k_state": summary.get("watchers", {}).get("slumbot_quick5k_launch", {}).get("state"),
        "slumbot_promotion20k_state": summary.get("watchers", {}).get("slumbot_promotion20k_launch", {}).get("state"),
        "slumbot_formal100k_state": summary.get("watchers", {}).get("slumbot_formal100k_launch", {}).get("state"),
        "archive_latest": (
            (summary.get("watchers", {}).get("checkpoint_archive", {}).get("latest_result") or {}).get("overall")
        ),
        "quality_status": scorecard.get("quality_status"),
        "latest_better": (scorecard.get("is_latest_training_better") or {}).get("answer"),
        "baseline_gap_status": baseline_gap.get("overall"),
        "baseline_comparison": (baseline_gap.get("baseline_comparison") or {}).get("answer"),
        "can_claim_stronger_than_baseline": (baseline_gap.get("claim_rules") or {}).get("can_claim_stronger_than_v4"),
        "l6_gap_bb100": (baseline_gap.get("gap") or {}).get("to_l6_target_bb100"),
        "trend_direction": (trend_ledger.get("direction") or {}).get("answer"),
        "trend_claim_allowed": (trend_ledger.get("direction") or {}).get("claim_allowed"),
        "trend_ledger_overall": trend_ledger.get("overall"),
        "trend_latest_official_hands": (trend_ledger.get("latest_official") or {}).get("hands"),
        "trend_latest_official_bb100": (trend_ledger.get("latest_official") or {}).get("bb_per_100"),
        "trend_latest_official_ci_lower": (trend_ledger.get("latest_official") or {}).get(
            "lower_bound_bb_per_100"
        ),
        "trend_decision_claim_latest_is_better": (trend_ledger.get("decision") or {}).get(
            "claim_latest_is_better"
        ),
        "trend_decision_promote_strength_claim": (trend_ledger.get("decision") or {}).get(
            "promote_strength_claim"
        ),
        **slumbot_loss_trend_aliases,
        **slumbot_analysis_coverage_aliases,
        "throughput_overall": throughput_audit.get("overall")
        or (throughput_audit.get("classification") or {}).get("overall"),
        "throughput_decision": throughput_audit.get("decision"),
        "throughput_recommendation_summary": throughput_audit.get("recommendation_summary"),
        "effective_hps": throughput_audit.get("effective_hps_latest")
        or (throughput_audit.get("latest_window") or {}).get("effective_hps_mean"),
        "effective_hps_latest": throughput_audit.get("effective_hps_latest")
        or (throughput_audit.get("latest_window") or {}).get("effective_hps_mean"),
        "effective_hps_long": throughput_audit.get("effective_hps_long")
        or (throughput_audit.get("long_window") or {}).get("effective_hps_mean"),
        "throughput_sweep_overall": throughput_sweep_plan.get("overall"),
        "throughput_sweep_active_source": throughput_sweep_plan.get("active_source_trainer"),
        "preflop_probe_overall": (summary.get("preflop_probe") or {}).get("overall"),
        "next_external_eval": next_external_eval_target,
        "next_external_eval_key": next_external_eval_key,
        "next_external_eval_stage": next_external_eval_stage,
        "next_external_eval_target_hands": next_external_eval_target,
        "next_external_eval_state": next_external_eval.get("state"),
        "next_external_eval_eta": next_external_eval.get("eta_duration_live"),
        "next_external_eval_checkpoint_hands": next_external_eval.get("checkpoint_hands"),
        "next_external_eval_current_hands": next_external_eval.get("current_hands"),
        "next_external_eval_remaining_checkpoint_hands": next_external_remaining_checkpoint_hands,
        "next_external_eval_remaining_live_hands": next_external_remaining_live_hands,
        "next_eval_key": next_external_eval_key,
        "next_stage": next_external_eval_stage,
        "next_target_hands": next_external_eval_target,
        "next_state": next_external_eval.get("state"),
        "next_eta": next_external_eval.get("eta_duration_live"),
        "remaining_checkpoint_hands": next_external_remaining_checkpoint_hands,
        "remaining_live_hands": next_external_remaining_live_hands,
        **eval_cadence_watch_aliases,
        "internal_probe_overall": (scorecard.get("internal_probes") or {}).get("overall"),
        "slumbot_score_overall": (scorecard.get("slumbot_ci") or {}).get("overall"),
        "l6_strength_answer": l6_status_brief.get("strength_answer"),
        "cutover_decision": cutover_decision.get("decision"),
        "cutover_target": cutover_decision.get("target_iteration"),
        "cutover_intervention_overall": cutover_decision.get("intervention_overall")
        or (cutover_decision.get("intervention") or {}).get("overall"),
        "cutover_intervention_target": (cutover_decision.get("intervention") or {}).get("target_iteration"),
        "cutover_intervention_source": cutover_decision.get("intervention_source")
        or (cutover_decision.get("intervention") or {}).get("source_path"),
        "evidence_overall": evidence_watchdog.get("overall"),
        "evidence_strength": (evidence_watchdog.get("slumbot_strength") or {}).get("status"),
        "health_warning_diagnosis": health_warning_diagnosis.get("overall"),
        "checkpoint_delta_overall": checkpoint_delta.get("overall"),
        "checkpoint_delta_recommendation": checkpoint_delta.get("recommendation"),
        "next_action_overall": next_action_queue.get("overall"),
        "next_action_recommendation": next_action_queue.get("recommendation"),
        "speed_decision": l6_speed_decision.get("decision"),
        "speed_effective_hps": (l6_speed_decision.get("throughput") or {}).get("effective_hps_latest"),
        "speed_effective_hps_latest": l6_speed_decision.get("speed_effective_hps_latest")
        or (l6_speed_decision.get("throughput") or {}).get("effective_hps_latest"),
        "speed_effective_hps_long": l6_speed_decision.get("speed_effective_hps_long")
        or (l6_speed_decision.get("throughput") or {}).get("effective_hps_long"),
        "speed_first_slumbot_milestone": l6_speed_decision.get("first_slumbot_milestone"),
        "speed_remaining_to_first_slumbot_checkpoint_hands": l6_speed_decision.get(
            "remaining_to_first_slumbot_checkpoint_hands"
        ),
        "speed_remaining_to_first_slumbot_live_hands": l6_speed_decision.get(
            "remaining_to_first_slumbot_live_hands"
        ),
        "speed_eta_to_first_slumbot_seconds": l6_speed_decision.get("eta_to_first_slumbot_seconds"),
        "speed_eta_to_first_slumbot": l6_speed_decision.get("eta_to_first_slumbot"),
        "speed_remaining_to_250m_checkpoint_hands": l6_speed_decision.get(
            "remaining_to_250m_checkpoint_hands"
        ),
        "speed_remaining_to_250m_live_hands": l6_speed_decision.get("remaining_to_250m_live_hands"),
        "speed_eta_to_250m_seconds": l6_speed_decision.get("eta_to_250m_seconds"),
        "speed_eta_to_250m": l6_speed_decision.get("eta_to_250m"),
        "speed_remaining_to_1b_checkpoint_hands": l6_speed_decision.get(
            "remaining_to_1b_checkpoint_hands"
        ),
        "speed_remaining_to_1b_live_hands": l6_speed_decision.get("remaining_to_1b_live_hands"),
        "speed_eta_to_1b_seconds": l6_speed_decision.get("eta_to_1b_seconds"),
        "speed_eta_to_1b": l6_speed_decision.get("eta_to_1b"),
        "speed_remaining_to_paper_scale_checkpoint_hands": l6_speed_decision.get(
            "remaining_to_paper_scale_checkpoint_hands"
        ),
        "speed_remaining_to_paper_scale_live_hands": l6_speed_decision.get(
            "remaining_to_paper_scale_live_hands"
        ),
        "speed_eta_to_paper_scale_seconds": l6_speed_decision.get("eta_to_paper_scale_seconds"),
        "speed_eta_to_paper_scale": l6_speed_decision.get("eta_to_paper_scale"),
        "claim_audit_overall": l6_claim_audit.get("overall"),
        "claim_audit_blockers": len(l6_claim_audit.get("blockers") or []),
        "promotion_decision": checkpoint_promotion_decision.get("overall"),
        "post_gate_review_overall": post_gate_review.get("overall"),
        "post_gate_review_target": post_gate_review.get("target_iteration"),
        "post_gate_review_recommendation": post_gate_review.get("recommendation"),
        "post_gate_review_gate": (post_gate_review.get("gate") or {}).get("overall"),
        "post_gate_review_internal": (post_gate_review.get("internal_probe") or {}).get("state"),
        "latest_completed_post_gate_review_overall": latest_completed_post_gate.get("overall"),
        "latest_completed_post_gate_review_target": latest_completed_post_gate.get("target_iteration"),
        "latest_completed_post_gate_review_recommendation": latest_completed_post_gate.get("recommendation"),
        "latest_completed_post_gate_review_gate": (latest_completed_post_gate.get("gate") or {}).get("overall"),
        "latest_completed_post_gate_review_internal": (
            latest_completed_post_gate.get("internal_probe") or {}
        ).get("state"),
        "latest_completed_post_gate_review_checked_at": latest_completed_post_gate.get("checked_at"),
        "l5_proven": summary.get("goal_status", {}).get("l5_formal_win_proven"),
        "l6_proven": summary.get("goal_status", {}).get("l6_near_paper_target_proven"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch and refresh V5 dashboard artifacts.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--status-json", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--sleep-seconds", type=float, default=120.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--no-refresh-progress", action="store_true")
    parser.add_argument("--no-preflop-probe", action="store_true")
    parser.add_argument("--preflop-probe-device", default="cpu")
    parser.add_argument("--preflop-probe-batch-size", type=int, default=256)
    parser.add_argument("--preflop-probe-guarded-temperature", type=float, default=1.0)
    parser.add_argument("--preflop-probe-guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--preflop-probe-guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--preflop-probe-callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--preflop-probe-callguard-ratio", type=float, default=0.65)
    parser.add_argument("--preflop-probe-callguard-include-open", action="store_true")
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--output-dir", default="models", help="Directory containing Slumbot benchmark artifacts.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    status_path = Path(args.status_json) if args.status_json else run_dir / "v5_dashboard_watch_status.json"
    log_path = Path(args.log) if args.log else run_dir / "v5_dashboard_watch.log"
    history: list[dict[str, Any]] = []

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    log(f"dashboard watcher started run_dir={run_dir}")
    while True:
        result = refresh_dashboard(args)
        history.append(result)
        status_payload = {
            "checked_at": now_iso(),
            "run_dir": str(run_dir),
            "latest": result,
            "history_tail": history[-20:],
        }
        for key in (
            "health",
            "health_age_seconds",
            "run_dashboard_checked_at",
            "live_iteration",
            "live_hands",
            "checkpoint_iteration",
            "checkpoint_hands",
            "recent_hands_per_second",
            "brief_live_iteration",
            "brief_checkpoint_iteration",
            "brief_live_hands",
            "brief_checkpoint_hands",
            "latest_gate_pass",
            "next_gate_pending",
            "latest_gate_age_seconds",
            "next_gate_age_seconds",
            "latest_gate_target_iteration",
            "latest_gate_overall",
            "latest_gate_health_overall",
            "latest_gate_live_iteration",
            "latest_gate_live_hands",
            "latest_gate_checkpoint_iteration",
            "latest_gate_checkpoint_hands",
            "latest_gate_remaining_live_iterations",
            "latest_gate_remaining_checkpoint_iterations",
            "next_gate_target_iteration",
            "next_gate_overall",
            "next_gate_health_overall",
            "next_gate_live_iteration",
            "next_gate_live_hands",
            "next_gate_checkpoint_iteration",
            "next_gate_checkpoint_hands",
            "next_gate_remaining_live_iterations",
            "next_gate_remaining_checkpoint_iterations",
            "training",
            "readiness",
            "internal_strength",
            "internal_latest_iteration",
            "internal_latest_hands",
            "internal_latest_verdict",
            "internal_latest_delta_mean_bb100",
            "internal_latest_delta_lower_bb100",
            "internal_next_target",
            "internal_next_state",
            "internal_watch_selected_status_path",
            "internal_watch_status_paths",
            "internal_watch_status_age_seconds",
            "internal_watch_latest_probe_target",
            "internal_watch_next_target",
            "internal_watch_next_overall",
            "score_progression",
            "strength_answer",
            "l6_strength_answer",
            "quality_status",
            "preflop_probe_overall",
            "next_action_overall",
            "next_action_recommendation",
            "next_action_queue_overall",
            "next_action_queue_recommendation",
            "next_action_queue_checked_at",
            "next_action_first_key",
            "next_action_first_status",
            "next_action_first_trigger",
            "next_action_first_action",
            "next_action_first_owner",
            "next_action_first_reason",
            "next_action_first_eta",
            "next_action_first_blocks_strength_claim",
            "post_gate_review_overall",
            "post_gate_review_target",
            "post_gate_review_recommendation",
            "post_gate_review_gate",
            "post_gate_review_internal",
            "post_gate_review_checked_at",
            "latest_completed_post_gate_review_overall",
            "latest_completed_post_gate_review_target",
            "latest_completed_post_gate_review_recommendation",
            "latest_completed_post_gate_review_gate",
            "latest_completed_post_gate_review_internal",
            "latest_completed_post_gate_review_checked_at",
            "l6_status_brief_checked_at",
            "trend_ledger_overall",
            "trend_direction",
            "trend_latest_official_hands",
            "trend_latest_official_bb100",
            "trend_latest_official_ci_lower",
            "trend_decision_claim_latest_is_better",
            "trend_decision_promote_strength_claim",
            "slumbot_loss_trend_status",
            "slumbot_loss_trend_blocks_strength_claim",
            "slumbot_loss_trend_reason",
            "slumbot_loss_trend_rows",
            "slumbot_loss_trend_latest_bb100",
            "slumbot_loss_trend_latest_bb_per_100",
            "slumbot_loss_trend_latest_delta_bb100",
            "slumbot_loss_trend_latest_delta_bb_per_100",
            "slumbot_loss_trend_latest_sb_bb100",
            "slumbot_loss_trend_latest_bb_bb100",
            "slumbot_loss_trend_latest_hero_fold_bb100",
            "slumbot_loss_trend_latest_showdown_bb100",
            "slumbot_analysis_coverage_overall",
            "slumbot_analysis_coverage_total_count",
            "slumbot_analysis_coverage_complete_count",
            "slumbot_analysis_coverage_incomplete_count",
            "slumbot_analysis_coverage_latest_stage",
            "slumbot_analysis_coverage_latest_milestone_m",
            "slumbot_analysis_coverage_latest_complete",
            "slumbot_analysis_coverage_latest_missing_parts",
            "slumbot_analysis_coverage_latest_complete_milestone_m",
            "slumbot_analysis_coverage_latest_complete_stage",
            "slumbot_analysis_coverage_latest_complete_bb100",
            "slumbot_score_overall",
            "throughput_overall",
            "throughput_decision",
            "throughput_recommendation_summary",
            "effective_hps",
            "effective_hps_latest",
            "effective_hps_long",
            "speed_decision",
            "speed_effective_hps",
            "speed_effective_hps_latest",
            "speed_effective_hps_long",
            "speed_first_slumbot_milestone",
            "speed_remaining_to_first_slumbot_checkpoint_hands",
            "speed_remaining_to_first_slumbot_live_hands",
            "speed_eta_to_first_slumbot_seconds",
            "speed_eta_to_first_slumbot",
            "speed_remaining_to_250m_checkpoint_hands",
            "speed_remaining_to_250m_live_hands",
            "speed_eta_to_250m_seconds",
            "speed_eta_to_250m",
            "speed_remaining_to_1b_checkpoint_hands",
            "speed_remaining_to_1b_live_hands",
            "speed_eta_to_1b_seconds",
            "speed_eta_to_1b",
            "speed_remaining_to_paper_scale_checkpoint_hands",
            "speed_remaining_to_paper_scale_live_hands",
            "speed_eta_to_paper_scale_seconds",
            "speed_eta_to_paper_scale",
            "cutover_decision",
            "cutover_target",
            "cutover_intervention_overall",
            "cutover_intervention_target",
            "cutover_intervention_source",
            "claim_audit_overall",
            "promotion_decision",
            "evidence_overall",
            "evidence_strength",
            "next_external_eval",
            "checkpoint_delta_overall",
            "checkpoint_delta_recommendation",
            "next_external_eval_key",
            "next_external_eval_stage",
            "next_external_eval_target_hands",
            "next_external_eval_state",
            "next_external_eval_eta",
            "next_external_eval_checkpoint_hands",
            "next_external_eval_current_hands",
            "next_external_eval_remaining_checkpoint_hands",
            "next_external_eval_remaining_live_hands",
            "next_eval_key",
            "next_stage",
            "next_target_hands",
            "next_state",
            "next_eta",
            "remaining_checkpoint_hands",
            "remaining_live_hands",
            "eval_cadence_watch_checked_at",
            "eval_cadence_watch_state",
            "eval_cadence_watch_checkpoint_iteration",
            "eval_cadence_watch_checkpoint_hands",
            "eval_cadence_watch_live_hands",
            "next_external_plan_preview_status",
            "next_external_plan_preview_key",
            "next_external_plan_preview_tag",
            "next_external_plan_preview_json",
            "next_external_plan_preview_md",
            "next_external_plan_preview_overall",
            "next_external_plan_preview_failed_checks",
            "next_external_plan_preview_checkpoint_iteration",
            "next_external_plan_preview_checkpoint_hands",
        ):
            status_payload[key] = result.get(key)
        write_json(status_path, status_payload)
        log(
            f"health={result.get('health')} iter={result.get('live_iteration')} "
            f"hands={result.get('live_hands')} gate_pass={result.get('latest_gate_pass')} "
            f"next_gate={result.get('next_gate_pending')} "
            f"quick5k={result.get('slumbot_quick5k_state')} "
            f"promotion20k={result.get('slumbot_promotion20k_state')} "
            f"formal100k={result.get('slumbot_formal100k_state')} "
            f"quality={result.get('quality_status')} "
            f"latest_better={result.get('latest_better')} "
            f"baseline={result.get('baseline_comparison')} "
            f"baseline_claim={result.get('can_claim_stronger_than_baseline')} "
            f"trend={result.get('trend_direction')} "
            f"trend_overall={result.get('trend_ledger_overall')} "
            f"trend_bb100={result.get('trend_latest_official_bb100')} "
            f"trend_ci_low={result.get('trend_latest_official_ci_lower')} "
            f"trend_latest_claim={result.get('trend_decision_claim_latest_is_better')} "
            f"trend_promote={result.get('trend_decision_promote_strength_claim')} "
            f"loss_trend={result.get('slumbot_loss_trend_status')}:{result.get('slumbot_loss_trend_latest_delta_bb100')} "
            f"throughput={result.get('throughput_overall')} "
            f"eff_hps={result.get('effective_hps_latest') or result.get('effective_hps')} "
            f"sweep={result.get('throughput_sweep_overall')}:{result.get('throughput_sweep_active_source')} "
            f"preflop={result.get('preflop_probe_overall')} "
            f"strength={result.get('l6_strength_answer')} "
            f"cutover={result.get('cutover_decision')}:{result.get('cutover_target')} "
            f"evidence={result.get('evidence_overall')}:{result.get('evidence_strength')} "
            f"health_diag={result.get('health_warning_diagnosis')} "
            f"ckpt_delta={result.get('checkpoint_delta_overall')} "
            f"speed={result.get('speed_decision')}:{result.get('speed_effective_hps_latest') or result.get('speed_effective_hps')} "
            f"claim_audit={result.get('claim_audit_overall')}:{result.get('claim_audit_blockers')} "
            f"promotion={result.get('promotion_decision')} "
            f"post_gate={result.get('post_gate_review_overall')}:{result.get('post_gate_review_target')} "
            f"action={result.get('next_action_overall')} "
            f"next_eval={result.get('next_external_eval')}:{result.get('next_external_eval_state')} "
            f"next_eval_remaining={result.get('next_external_eval_remaining_checkpoint_hands')}"
        )
        if args.once:
            return 0
        time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
