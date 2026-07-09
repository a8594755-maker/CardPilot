#!/usr/bin/env python3
"""Emit a concise L6-oriented status brief for a V5 AlphaHoldem run.

This is a read-only aggregation of existing evidence. It deliberately separates
training health from strength claims so quick updates do not overstate progress.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v5_scorecard import summarize_probe


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} is not a JSON object"}


def load_intervention_plan(run_dir: Path) -> tuple[Path, dict[str, Any]]:
    candidates: list[tuple[int, str, Path, dict[str, Any]]] = []
    patterns = [
        "v5_context_preflop_intervention_plan_*.json",
        "v5_preflop_intervention_plan.json",
    ]
    for priority, pattern in enumerate(patterns):
        for path in sorted(run_dir.glob(pattern)):
            plan = load_json(path)
            if plan.get("_missing") or plan.get("_load_error"):
                continue
            checked_at = str(plan.get("checked_at") or "")
            target_iteration = plan.get("target_iteration")
            target_sort = int(target_iteration) if isinstance(target_iteration, int) else -1
            candidates.append((priority, f"{target_sort:010d}:{checked_at}", path, plan))
    if not candidates:
        path = run_dir / "v5_preflop_intervention_plan.json"
        return path, load_json(path)
    candidates.sort(key=lambda item: (-item[0], item[1]))
    _, _, selected_path, selected_plan = candidates[-1]
    return selected_path, selected_plan


def pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def load_internal_strength_status(run_dir: Path) -> dict[str, Any]:
    paths = sorted(run_dir.glob("internal_strength_watch*_status.json"))
    statuses: list[dict[str, Any]] = []
    completed: set[int] = set()
    readiness_candidates: list[tuple[int, Path, dict[str, Any]]] = []
    probe_candidates: list[tuple[int, str, Path, dict[str, Any]]] = []

    for path in paths:
        status = load_json(path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        status["_path"] = str(path)
        statuses.append(status)
        for target in status.get("completed") or []:
            if isinstance(target, int):
                completed.add(target)
        readiness = status.get("latest_readiness")
        if isinstance(readiness, dict):
            target = readiness.get("target_iteration")
            if isinstance(target, int):
                readiness_candidates.append((target, path, readiness))
        probe = status.get("latest_probe")
        if isinstance(probe, dict):
            target = probe.get("target_iteration")
            if isinstance(target, int):
                if probe.get("status") == "PASS":
                    completed.add(target)
                checked_at = str(probe.get("checked_at") or status.get("checked_at") or "")
                probe_candidates.append((target, checked_at, path, probe))

    if not statuses:
        fallback_path = run_dir / "internal_strength_watch_status.json"
        missing = load_json(fallback_path)
        missing["_selected_path"] = str(fallback_path)
        return missing

    completed_sorted = sorted(completed)
    pending = [
        item for item in readiness_candidates
        if item[2].get("overall") != "PASS" and item[0] not in completed
    ]
    if pending:
        selected_target, selected_path, selected_readiness = min(pending, key=lambda item: item[0])
    elif readiness_candidates:
        selected_target, selected_path, selected_readiness = max(readiness_candidates, key=lambda item: item[0])
    else:
        selected_target = -1
        selected_path = Path(statuses[-1].get("_path", ""))
        selected_readiness = {}
    if probe_candidates:
        latest_probe_target, _, latest_probe_path, latest_probe = max(probe_candidates, key=lambda item: (item[0], item[1]))
    else:
        latest_probe_target = None
        latest_probe_path = None
        latest_probe = {}

    return {
        "checked_at": max(str(status.get("checked_at") or "") for status in statuses),
        "completed": completed_sorted,
        "latest_readiness": selected_readiness,
        "latest_probe": latest_probe,
        "latest_probe_target": latest_probe_target,
        "latest_probe_path": str(latest_probe_path) if latest_probe_path else None,
        "selected_target": selected_target if selected_target >= 0 else None,
        "_selected_path": str(selected_path),
        "_paths": [str(path) for path in paths],
        "_watcher_count": len(statuses),
    }


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def gate_target_from(path: Path, gate: dict[str, Any]) -> int | None:
    target = gate.get("target_iteration")
    if isinstance(target, int):
        return target
    stem = path.stem
    parts = stem.split("_")
    if len(parts) >= 3 and parts[0] == "gate":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def selector_pair_token(path: Path) -> str:
    name = path.name
    prefix = "slumbot_selector_pair_"
    suffix = "_status.json"
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    return path.stem


def selector_ci_entry(result: dict[str, Any], policy_mode: str) -> dict[str, Any]:
    ci = result.get("ci_summary") if isinstance(result.get("ci_summary"), dict) else {}
    promotion = result.get("promotion_summary") if isinstance(result.get("promotion_summary"), dict) else {}
    slumbot = promotion.get("slumbot") if isinstance(promotion.get("slumbot"), dict) else {}
    ci_path = promotion.get("ci_json_path") or result.get("ci_json_path")
    return {
        "baseline_delta_bb_per_100": ci.get("baseline_delta_bb_per_100") or slumbot.get("baseline_delta_bb_per_100"),
        "bb_per_100": ci.get("bb_per_100") or slumbot.get("bb_per_100"),
        "diagnostic": True,
        "hands": ci.get("hands") or slumbot.get("hands"),
        "input_files": ci.get("input_files"),
        "kind": "diagnostic",
        "l5_formal_win": ci.get("l5_formal_win"),
        "l6_near_paper_target": ci.get("l6_near_paper_target"),
        "lower_bound_bb_per_100": ci.get("lower_bound_bb_per_100") or slumbot.get("lower_bound_bb_per_100"),
        "milestone_level": ci.get("milestone_level") or slumbot.get("milestone_level"),
        "path": ci_path,
        "policy_mode": policy_mode,
        "upper_bound_bb_per_100": ci.get("upper_bound_bb_per_100") or slumbot.get("upper_bound_bb_per_100"),
    }


def load_selector_pair_statuses(run_dir: Path) -> list[dict[str, Any]]:
    pairs: list[dict[str, Any]] = []
    for status_path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = load_json(status_path)
        if status.get("state") != "PASS":
            continue
        results = status.get("results") if isinstance(status.get("results"), dict) else {}
        greedy = results.get("greedy") if isinstance(results.get("greedy"), dict) else {}
        callguard = (
            results.get("preflop-callguard")
            if isinstance(results.get("preflop-callguard"), dict)
            else results.get("preflop_callguard")
            if isinstance(results.get("preflop_callguard"), dict)
            else {}
        )
        if not greedy or not callguard:
            continue
        frozen = status.get("frozen_summary") if isinstance(status.get("frozen_summary"), dict) else {}
        frozen_iteration = frozen.get("iteration")
        frozen_hands = frozen.get("total_hands")
        token = selector_pair_token(status_path)
        if frozen_iteration is not None and frozen_hands is not None:
            target_label = f"iter {frozen_iteration} / {float(frozen_hands) / 1_000_000.0:.3f}M"
        else:
            target_label = token
        pair = {
            "checked_at": status.get("checked_at"),
            "combined_hands": (selector_ci_entry(greedy, "greedy").get("hands") or 0)
            + (selector_ci_entry(callguard, "preflop-callguard").get("hands") or 0),
            "delta_callguard_vs_greedy_bb_per_100": status.get("delta_callguard_vs_greedy_bb_per_100"),
            "frozen_iteration": frozen_iteration,
            "frozen_hands": frozen_hands,
            "greedy": selector_ci_entry(greedy, "greedy"),
            "preflop_callguard": selector_ci_entry(callguard, "preflop-callguard"),
            "source_status": str(status_path),
            "target_label": target_label,
            "target_m": float(frozen_hands) / 1_000_000.0 if isinstance(frozen_hands, (int, float)) else None,
            "token": token,
        }
        pairs.append(pair)
    pairs.sort(
        key=lambda pair: (
            pair.get("frozen_hands") if isinstance(pair.get("frozen_hands"), (int, float)) else -1,
            pair.get("checked_at") or "",
        )
    )
    return pairs


def load_active_selector_pair_status(run_dir: Path) -> dict[str, Any]:
    candidates: list[tuple[str, float, Path, dict[str, Any]]] = []
    for status_path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = load_json(status_path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        if status.get("state") == "PASS":
            continue
        checked_at = str(status.get("checked_at") or "")
        try:
            mtime = status_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((checked_at, mtime, status_path, status))
    if not candidates:
        return {}
    _, _, status_path, status = sorted(candidates, key=lambda item: (item[0], item[1]))[-1]
    greedy_plan = pick(status, "plans", "greedy", default={}) or {}
    checkpoint = greedy_plan.get("checkpoint") if isinstance(greedy_plan.get("checkpoint"), dict) else {}
    return {
        "state": status.get("state"),
        "checked_at": status.get("checked_at"),
        "path": str(status_path),
        "token": selector_pair_token(status_path),
        "base_tag": status.get("base_tag"),
        "readiness_by_policy": status.get("readiness_by_policy"),
        "planned_hands_per_policy": status.get("planned_hands_per_policy"),
        "checkpoint_iteration": checkpoint.get("iteration"),
        "checkpoint_hands": checkpoint.get("total_hands"),
        "min_training_hands": greedy_plan.get("min_training_hands"),
        "frozen_iteration": pick(status, "frozen_summary", "iteration"),
        "frozen_hands": pick(status, "frozen_summary", "total_hands"),
    }


def build_summary(run_dir: Path) -> dict[str, Any]:
    gate_files = sorted(run_dir.glob("gate_*_status.json"))
    gate_records = []
    for gate_file in gate_files:
        gate_obj = load_json(gate_file)
        target = gate_target_from(gate_file, gate_obj)
        gate_records.append({"path": gate_file, "target": target, "gate": gate_obj})
    gate_records.sort(key=lambda item: -1 if item["target"] is None else int(item["target"]))
    latest_pass_record = None
    for item in gate_records:
        if item["gate"].get("overall") == "PASS":
            if latest_pass_record is None or int(item["target"] or -1) > int(latest_pass_record["target"] or -1):
                latest_pass_record = item
    next_pending_record = None
    latest_pass_target = latest_pass_record["target"] if latest_pass_record else None
    for item in gate_records:
        if item["gate"].get("overall") != "PENDING":
            continue
        if isinstance(latest_pass_target, int) and isinstance(item["target"], int) and item["target"] <= latest_pass_target:
            continue
        if next_pending_record is None or int(item["target"] or 10**18) < int(next_pending_record["target"] or 10**18):
            next_pending_record = item
    current_gate_record = next_pending_record or latest_pass_record or (gate_records[-1] if gate_records else None)
    gate = current_gate_record["gate"] if current_gate_record else {"_missing": True}
    health = load_json(run_dir / "health_status.json")
    scorecard = load_json(run_dir / "v5_scorecard.json")
    baseline = load_json(run_dir / "v5_baseline_gap.json")
    trend = load_json(run_dir / "v5_trend_ledger.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    intervention_path, intervention = load_intervention_plan(run_dir)
    action_trend = load_json(run_dir / "v5_action_prior_trend.json")
    internal_strength = load_internal_strength_status(run_dir)
    health_warning_diagnosis = load_json(run_dir / "v5_health_warning_diagnosis.json")
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    checkpoint_delta = load_json(run_dir / "v5_checkpoint_delta.json")
    speed_decision = load_json(run_dir / "v5_l6_speed_decision.json")
    claim_audit = load_json(run_dir / "v5_l6_claim_audit.json")
    promotion_decision = load_json(run_dir / "v5_checkpoint_promotion_decision.json")

    latest = pick(health, "latest", default={}) or {}
    gate_latest = pick(gate, "latest", default={}) or {}
    gate_ckpt = pick(gate, "checkpoint", default={}) or {}
    latest_pass_gate = latest_pass_record["gate"] if latest_pass_record else {}
    latest_pass_ckpt = pick(latest_pass_gate, "checkpoint", default={}) or {}
    next_pending_gate = next_pending_record["gate"] if next_pending_record else {}
    next_pending_ckpt = pick(next_pending_gate, "checkpoint", default={}) or {}
    latest_slumbot = pick(baseline, "latest_slumbot", default={}) or {}
    latest_slumbot_diagnostic = pick(scorecard, "slumbot_ci", "latest_diagnostic", default={}) or {}
    latest_diagnostic_by_policy = pick(scorecard, "slumbot_ci", "latest_diagnostic_by_policy", default={}) or {}
    diagnostic_pairs = load_selector_pair_statuses(run_dir) or pick(scorecard, "slumbot_ci", "diagnostic_pairs", default=[]) or []
    active_selector_pair = load_active_selector_pair_status(run_dir)
    comparison = (
        pick(baseline, "baseline_comparison", default=None)
        or pick(baseline, "comparison", default={})
        or {}
    )
    l6_gap = pick(baseline, "gap", default=None) or pick(baseline, "l5_l6_gap", default={}) or {}
    claim_rules = pick(baseline, "claim_rules", default={}) or {}

    can_claim_stronger = bool(
        claim_rules.get("can_claim_stronger_than_v4")
        or baseline.get("can_claim_stronger_than_baseline")
    )
    can_claim_l5 = bool(claim_rules.get("can_claim_l5") or baseline.get("can_claim_l5") or l6_gap.get("formal_l5_ready"))
    can_claim_l6 = bool(claim_rules.get("can_claim_l6") or baseline.get("can_claim_l6") or l6_gap.get("formal_l6_ready"))

    if can_claim_l6:
        strength_answer = "L6_PROVEN"
    elif can_claim_l5:
        strength_answer = "L5_PROVEN_NOT_L6"
    elif can_claim_stronger:
        strength_answer = "BASELINE_BEATEN_NOT_FORMAL_L5"
    else:
        strength_answer = "NOT_PROVEN_STRONGER_THAN_V4"

    blockers = []
    for item in scorecard.get("blockers") or []:
        blockers.append(str(item))
    if not blockers:
        if not can_claim_l5:
            blockers.append("formal L5/L6 Slumbot evidence is not available")
        if gate.get("overall") != "PASS":
            blockers.append(f"latest gate is {gate.get('overall')}")

    internal_completed = internal_strength.get("completed") or []
    latest_internal_score = pick(scorecard, "internal_probes", "latest", default={}) or {}
    max_completed_internal = max(internal_completed) if internal_completed else None
    latest_score_target = latest_internal_score.get("checkpoint_iteration")
    if (
        isinstance(max_completed_internal, int)
        and (latest_score_target is None or int(latest_score_target) < max_completed_internal)
    ):
        probe_path = run_dir / f"internal_strength_probe_iter{max_completed_internal}_200h.json"
        summarized_probe = summarize_probe(probe_path)
        if summarized_probe:
            latest_internal_score = summarized_probe
    last_internal_probe_target = latest_internal_score.get("checkpoint_iteration")
    if last_internal_probe_target is None:
        last_internal_probe_target = max_completed_internal
    last_internal_probe_state = "COMPLETED" if latest_internal_score else None
    next_internal_probe_target = pick(internal_strength, "latest_readiness", "target_iteration")
    next_internal_probe_state = pick(internal_strength, "latest_readiness", "overall")
    health_diag_metrics = (
        health_warning_diagnosis.get("metrics")
        if isinstance(health_warning_diagnosis.get("metrics"), dict)
        else {}
    )
    preflop_probe_ckpt = preflop_probe.get("checkpoint") if isinstance(preflop_probe.get("checkpoint"), dict) else {}
    speed_milestones = speed_decision.get("milestones") if isinstance(speed_decision.get("milestones"), list) else []
    paper_scale_speed = {}
    quick_speed = {}
    for milestone in speed_milestones:
        if not isinstance(milestone, dict):
            continue
        if milestone.get("target_hands") == 100_000_000:
            quick_speed = milestone
        if milestone.get("target_hands") == 2_700_000_000:
            paper_scale_speed = milestone
    paper_target_alternatives = (
        paper_scale_speed.get("target_hps_alternatives")
        if isinstance(paper_scale_speed.get("target_hps_alternatives"), list)
        else []
    )
    paper_eta_900 = {}
    for alt in paper_target_alternatives:
        if isinstance(alt, dict) and float(alt.get("hps") or 0.0) == 900.0:
            paper_eta_900 = alt
    internal_probe_history = trend.get("internal_probe_history")
    if not isinstance(internal_probe_history, list):
        internal_probe_history = []
    latest_internal_trend = internal_probe_history[-1] if internal_probe_history else {}
    if (
        latest_internal_score
        and latest_internal_score.get("checkpoint_iteration") is not None
        and int(latest_internal_score.get("checkpoint_iteration") or 0)
        > int(latest_internal_trend.get("checkpoint_iteration") or -1)
    ):
        latest_internal_trend = {
            "checkpoint_iteration": latest_internal_score.get("checkpoint_iteration"),
            "checkpoint_hands": latest_internal_score.get("checkpoint_hands"),
            "hands_per_match": latest_internal_score.get("hands_per_match"),
            "mean_latest_bb100": latest_internal_score.get("mean_latest_bb100"),
            "mean_latest_lower_bound_bb100": latest_internal_score.get("mean_latest_lower_bound_bb100"),
            "delta_mean_vs_previous": None,
            "delta_lower_vs_previous": None,
            "latest_is_best_opponents": latest_internal_score.get("latest_is_best_opponents"),
            "opponent_count": latest_internal_score.get("opponent_count"),
            "verdict": latest_internal_score.get("verdict"),
            "path": latest_internal_score.get("path"),
        }
        internal_probe_history = [*internal_probe_history, latest_internal_trend]
    slumbot_history = trend.get("slumbot_history")
    if not isinstance(slumbot_history, list):
        slumbot_history = []

    official_bb100 = latest_slumbot.get("bb_per_100")
    diagnostic_bb100 = latest_slumbot_diagnostic.get("bb_per_100")
    diagnostic_delta_vs_official = None
    if official_bb100 is not None and diagnostic_bb100 is not None:
        diagnostic_delta_vs_official = float(diagnostic_bb100) - float(official_bb100)

    summary = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "health": health.get("overall"),
        "health_warning_diagnosis": {
            "overall": health_warning_diagnosis.get("overall"),
            "recommendation": health_warning_diagnosis.get("recommendation"),
            "preflop_allin_latest": health_diag_metrics.get("preflop_allin_latest"),
            "preflop_allin_mean": health_diag_metrics.get("preflop_allin_mean"),
            "preflop_allin_warn_fraction": health_diag_metrics.get("preflop_allin_warn_fraction"),
            "preflop_call_mean": health_diag_metrics.get("preflop_call_mean"),
            "postflop_ra_mean": health_diag_metrics.get("postflop_ra_mean"),
        },
        "preflop_probe": {
            "overall": preflop_probe.get("overall"),
            "checkpoint_iteration": preflop_probe_ckpt.get("iteration"),
            "checkpoint_hands": preflop_probe_ckpt.get("total_hands"),
        },
        "checkpoint_delta": {
            "overall": checkpoint_delta.get("overall"),
            "recommendation": checkpoint_delta.get("recommendation"),
            "previous_probe_overall": pick(checkpoint_delta, "previous_probe", "overall"),
            "latest_probe_overall": pick(checkpoint_delta, "latest_probe", "overall"),
            "warning_delta": pick(checkpoint_delta, "probe_delta", "warning_count"),
        },
        "speed_decision": {
            "decision": speed_decision.get("decision"),
            "recommendation": speed_decision.get("recommendation"),
            "effective_hps_latest": pick(speed_decision, "throughput", "effective_hps_latest"),
            "effective_hps_long": pick(speed_decision, "throughput", "effective_hps_long"),
            "quick100m_eta": quick_speed.get("measured_eta_duration"),
            "paper_scale_eta": paper_scale_speed.get("measured_eta_duration"),
            "paper_scale_900_eta": paper_eta_900.get("eta_duration"),
            "paper_scale_900_saved": paper_eta_900.get("time_saved_duration"),
        },
        "claim_audit": {
            "overall": claim_audit.get("overall"),
            "blocker_count": len(claim_audit.get("blockers") or []),
            "watch_count": len(claim_audit.get("watches") or []),
            "can_claim_l5": pick(claim_audit, "summary", "can_claim_l5"),
            "can_claim_l6": pick(claim_audit, "summary", "can_claim_l6"),
        },
        "promotion_decision": {
            "overall": promotion_decision.get("overall"),
            "recommendation": promotion_decision.get("recommendation"),
            "target_iteration": promotion_decision.get("target_iteration"),
        },
        "score_progression": {
            "latest_better_answer": pick(scorecard, "is_latest_training_better", "answer"),
            "trend_overall": trend.get("overall"),
            "trend_direction": pick(trend, "direction", "answer"),
            "trend_claim_allowed": pick(trend, "direction", "claim_allowed"),
            "trend_basis": pick(trend, "direction", "basis"),
            "latest_official_hands": pick(trend, "latest_official", "hands"),
            "latest_official_bb100": pick(trend, "latest_official", "bb_per_100"),
            "latest_official_ci_lower": pick(trend, "latest_official", "lower_bound_bb_per_100"),
            "trend_decision_claim_latest_is_better": pick(trend, "decision", "claim_latest_is_better"),
            "trend_decision_promote_strength_claim": pick(trend, "decision", "promote_strength_claim"),
            "internal_probe_count": len(internal_probe_history),
            "latest_internal_probe_iteration": latest_internal_trend.get("checkpoint_iteration"),
            "latest_internal_probe_hands": latest_internal_trend.get("checkpoint_hands"),
            "latest_internal_delta_mean_bb100": latest_internal_trend.get("delta_mean_vs_previous"),
            "latest_internal_delta_lower_bb100": latest_internal_trend.get("delta_lower_vs_previous"),
            "latest_internal_verdict": latest_internal_trend.get("verdict"),
            "slumbot_evidence_count": len(slumbot_history),
        },
        "quality_status": scorecard.get("quality_status"),
        "strength_answer": strength_answer,
        "claims": {
            "can_claim_stronger_than_v4": can_claim_stronger,
            "can_claim_l5": can_claim_l5,
            "can_claim_l6": can_claim_l6,
            "claim_rule": "L5/L6 requires 100k+ Slumbot hands, bb/100 > 0, and CI lower > 0; L6 also needs near +11.1 bb/100.",
        },
        "live": {
            "iteration": latest.get("iteration") or gate_latest.get("iteration"),
            "hands": latest.get("hands") or gate_latest.get("hands"),
            "hands_per_second": latest.get("hands_per_second") or pick(health, "latest", "hands_per_second"),
            "reward_window_100": latest.get("reward_window_100"),
            "entropy": latest.get("entropy"),
            "preflop_action_mix": latest.get("preflop_action_mix"),
            "postflop_action_mix": latest.get("postflop_action_mix"),
        },
        "checkpoint": {
            "gate_target": gate.get("target_iteration"),
            "gate_overall": gate.get("overall"),
            "checkpoint_iteration": gate_ckpt.get("iteration"),
            "checkpoint_hands": gate_ckpt.get("total_hands"),
            "pool_snapshots": gate_ckpt.get("pool_snapshots"),
            "latest_pass_target": latest_pass_gate.get("target_iteration"),
            "latest_pass_checkpoint_iteration": latest_pass_ckpt.get("iteration"),
            "latest_pass_checkpoint_hands": latest_pass_ckpt.get("total_hands"),
            "next_pending_target": next_pending_gate.get("target_iteration"),
            "next_pending_overall": next_pending_gate.get("overall"),
            "next_pending_checkpoint_iteration": next_pending_ckpt.get("iteration"),
            "next_pending_checkpoint_hands": next_pending_ckpt.get("total_hands"),
        },
        "slumbot": {
            "hands": latest_slumbot.get("hands"),
            "bb_per_100": latest_slumbot.get("bb_per_100"),
            "ci_lower": latest_slumbot.get("lower_bound_bb_per_100"),
            "level": latest_slumbot.get("milestone_level") or latest_slumbot.get("derived_level"),
            "baseline_comparison": comparison.get("answer"),
            "point_delta_vs_v4_bb100": comparison.get("point_delta_bb100"),
            "gap_to_l6_target_bb100": l6_gap.get("to_l6_target_bb100") or l6_gap.get("gap_to_l6_target_bb100"),
            "latest_diagnostic": {
                "hands": latest_slumbot_diagnostic.get("hands"),
                "bb_per_100": latest_slumbot_diagnostic.get("bb_per_100"),
                "ci_lower": latest_slumbot_diagnostic.get("lower_bound_bb_per_100"),
                "level": latest_slumbot_diagnostic.get("milestone_level"),
                "kind": latest_slumbot_diagnostic.get("kind"),
                "policy_mode": latest_slumbot_diagnostic.get("policy_mode"),
                "path": latest_slumbot_diagnostic.get("path"),
                "baseline_delta_vs_v4_bb100": latest_slumbot_diagnostic.get("baseline_delta_bb_per_100"),
                "delta_vs_official_bb100": diagnostic_delta_vs_official,
            },
            "latest_diagnostic_by_policy": latest_diagnostic_by_policy,
            "diagnostic_pairs": diagnostic_pairs,
            "active_selector_pair": active_selector_pair,
        },
        "next_evidence": {
            "internal_probe_target": last_internal_probe_target or pick(cadence, "internal_probe", "latest_target"),
            "internal_probe_state": last_internal_probe_state or pick(cadence, "internal_probe", "latest_overall"),
            "internal_probe_verdict": latest_internal_score.get("verdict"),
            "internal_probe_latest_is_best_opponents": latest_internal_score.get("latest_is_best_opponents"),
            "internal_probe_opponent_count": latest_internal_score.get("opponent_count"),
            "internal_probe_mean_latest_bb100": latest_internal_score.get("mean_latest_bb100"),
            "internal_probe_mean_lower_bound_bb100": latest_internal_score.get("mean_latest_lower_bound_bb100"),
            "next_internal_probe_target": next_internal_probe_target or pick(cadence, "internal_probe", "next_due"),
            "next_internal_probe_state": next_internal_probe_state,
            "next_external_eval_target_hands": pick(cadence, "next_external_eval", "target_hands"),
            "next_external_eval_state": pick(cadence, "next_external_eval", "state"),
            "next_external_eval_eta": pick(cadence, "next_external_eval", "eta_duration_live"),
            "next_promotion_target_hands": pick(cadence, "next_promotion_eval", "target_hands"),
            "next_promotion_eta": pick(cadence, "next_promotion_eval", "eta_duration_live"),
        },
        "preflop_intervention": {
            "source_plan": str(intervention_path),
            "overall": intervention.get("overall"),
            "recommendation": intervention.get("recommendation"),
            "target_iteration": intervention.get("target_iteration"),
            "checkpoint_iteration": intervention.get("checkpoint_iteration"),
            "live_iteration": intervention.get("live_iteration"),
            "current_live_iteration": latest.get("iteration") or gate_latest.get("iteration"),
            "current_checkpoint_iteration": latest_pass_ckpt.get("iteration") or gate_ckpt.get("iteration"),
            "dry_run_command_emitted": bool(intervention.get("dry_run_command")),
            "context_preflop_intervention_needed": intervention.get("context_preflop_intervention_needed"),
            "sb_open_weak": intervention.get("sb_open_weak"),
            "selector_preflop_leak_confirmed": intervention.get("selector_preflop_leak_confirmed"),
            "planned_action_priors": intervention.get("planned_action_priors"),
            "trend_overall": action_trend.get("overall"),
            "trend_latest_iteration": pick(action_trend, "candidate", "latest_iteration"),
            "trend_preflop_allin_delta": pick(action_trend, "comparison", "preflop_allin_delta"),
            "trend_preflop_call_delta": pick(action_trend, "comparison", "preflop_call_delta"),
        },
        "trend": {
            "overall": trend.get("overall"),
            "direction": pick(trend, "direction", "answer"),
            "claim_allowed": pick(trend, "direction", "claim_allowed"),
            "latest_official": trend.get("latest_official"),
            "decision": trend.get("decision"),
        },
        "blockers": blockers,
        "source_artifacts": {
            "gate": str(current_gate_record["path"]) if current_gate_record else None,
            "latest_pass_gate": str(latest_pass_record["path"]) if latest_pass_record else None,
            "next_pending_gate": str(next_pending_record["path"]) if next_pending_record else None,
            "health": str(run_dir / "health_status.json"),
            "scorecard": str(run_dir / "v5_scorecard.json"),
            "baseline_gap": str(run_dir / "v5_baseline_gap.json"),
            "eval_cadence": str(run_dir / "v5_eval_cadence.json"),
            "internal_strength": internal_strength.get("_selected_path") or str(run_dir / "internal_strength_watch_status.json"),
            "internal_strength_all": internal_strength.get("_paths", []),
            "intervention": str(intervention_path),
            "health_warning_diagnosis": str(run_dir / "v5_health_warning_diagnosis.json"),
            "preflop_probe": str(run_dir / "v5_preflop_probe_latest.json"),
            "checkpoint_delta": str(run_dir / "v5_checkpoint_delta.json"),
            "speed_decision": str(run_dir / "v5_l6_speed_decision.json"),
            "claim_audit": str(run_dir / "v5_l6_claim_audit.json"),
            "promotion_decision": str(run_dir / "v5_checkpoint_promotion_decision.json"),
        },
    }
    summary["training"] = {
        "live_iteration": pick(summary, "live", "iteration"),
        "live_hands": pick(summary, "live", "hands"),
        "hands_per_second": pick(summary, "live", "hands_per_second"),
        "health": summary["health"],
        "checkpoint_iteration": pick(summary, "checkpoint", "checkpoint_iteration"),
        "checkpoint_hands": pick(summary, "checkpoint", "checkpoint_hands"),
    }
    summary["readiness"] = {
        "latest_gate_target": pick(summary, "checkpoint", "latest_pass_target"),
        "latest_gate_overall": latest_pass_gate.get("overall"),
        "latest_gate_checkpoint_iteration": pick(summary, "checkpoint", "latest_pass_checkpoint_iteration"),
        "latest_gate_checkpoint_hands": pick(summary, "checkpoint", "latest_pass_checkpoint_hands"),
        "next_gate_target": pick(summary, "checkpoint", "next_pending_target"),
        "next_gate_overall": pick(summary, "checkpoint", "next_pending_overall"),
        "current_gate_target": pick(summary, "checkpoint", "gate_target"),
        "current_gate_overall": pick(summary, "checkpoint", "gate_overall"),
    }
    summary["internal_strength"] = {
        "latest_iteration": pick(summary, "score_progression", "latest_internal_probe_iteration"),
        "latest_hands": pick(summary, "score_progression", "latest_internal_probe_hands"),
        "latest_verdict": pick(summary, "score_progression", "latest_internal_verdict"),
        "latest_delta_mean_bb100": pick(summary, "score_progression", "latest_internal_delta_mean_bb100"),
        "latest_delta_lower_bb100": pick(summary, "score_progression", "latest_internal_delta_lower_bb100"),
        "next_target": pick(summary, "next_evidence", "next_internal_probe_target"),
        "next_state": pick(summary, "next_evidence", "next_internal_probe_state"),
    }
    return summary


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    live = summary["live"]
    ckpt = summary["checkpoint"]
    slumbot = summary["slumbot"]
    slumbot_diagnostic = slumbot.get("latest_diagnostic") or {}
    diagnostic_pairs = slumbot.get("diagnostic_pairs") or []
    active_selector_pair = slumbot.get("active_selector_pair") if isinstance(slumbot.get("active_selector_pair"), dict) else {}
    latest_selector_pair = diagnostic_pairs[-1] if diagnostic_pairs else {}
    selector_pair_greedy = latest_selector_pair.get("greedy") or {}
    selector_pair_callguard = latest_selector_pair.get("preflop_callguard") or {}
    selector_pair_target = latest_selector_pair.get("target_label")
    if not selector_pair_target:
        target_m = latest_selector_pair.get("target_m")
        selector_pair_target = f"{fmt(target_m)}M" if target_m is not None else "n/a"
    next_evidence = summary["next_evidence"]
    intervention = summary["preflop_intervention"]
    health_diag = summary["health_warning_diagnosis"]
    preflop_probe = summary["preflop_probe"]
    checkpoint_delta = summary["checkpoint_delta"]
    speed_decision = summary["speed_decision"]
    claim_audit = summary["claim_audit"]
    promotion_decision = summary["promotion_decision"]
    score_progression = summary["score_progression"]
    lines = [
        "# V5 L6 Status Brief",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Health: `{summary['health']}`",
        f"- Rolling health diagnosis: `{health_diag['overall']}`",
        f"- Preflop probe: `{preflop_probe['overall']}` at checkpoint `{preflop_probe['checkpoint_iteration']}` / `{preflop_probe['checkpoint_hands']}`",
        f"- Quality: `{summary['quality_status']}`",
        f"- Strength answer: **{summary['strength_answer']}**",
        "",
        "Live training:",
        "",
        f"- Iteration / hands: `{live['iteration']}` / `{live['hands']}`",
        f"- Reward100 / entropy: `{fmt(live['reward_window_100'])}` / `{fmt(live['entropy'])}`",
        f"- Preflop mix: `{live['preflop_action_mix']}`",
        f"- Postflop mix: `{live['postflop_action_mix']}`",
        f"- Rolling preflop all-in latest / mean / warn fraction: `{fmt(health_diag['preflop_allin_latest'])}` / `{fmt(health_diag['preflop_allin_mean'])}` / `{fmt(health_diag['preflop_allin_warn_fraction'])}`",
        f"- Rolling preflop call mean / postflop RA mean: `{fmt(health_diag['preflop_call_mean'])}` / `{fmt(health_diag['postflop_ra_mean'])}`",
        "",
        "Gate:",
        "",
        f"- Latest PASS: target `{ckpt['latest_pass_target']}` checkpoint `{ckpt['latest_pass_checkpoint_iteration']}` / `{ckpt['latest_pass_checkpoint_hands']}`",
        f"- Next pending: target `{ckpt['next_pending_target']}` overall `{ckpt['next_pending_overall']}` checkpoint `{ckpt['next_pending_checkpoint_iteration']}` / `{ckpt['next_pending_checkpoint_hands']}`",
        f"- Current gate view: target `{ckpt['gate_target']}` / `{ckpt['gate_overall']}`; checkpoint `{ckpt['checkpoint_iteration']}` / `{ckpt['checkpoint_hands']}`",
        f"- Pool snapshots: `{ckpt['pool_snapshots']}`",
        "",
        "Checkpoint delta:",
        "",
        f"- Local guardrail delta: `{checkpoint_delta['overall']}`",
        f"- Probe status: `{checkpoint_delta['previous_probe_overall']}` -> `{checkpoint_delta['latest_probe_overall']}`; warning delta `{fmt(checkpoint_delta['warning_delta'])}`",
        f"- Note: {checkpoint_delta['recommendation']}",
        "",
        "Strength progression:",
        "",
        f"- Latest better answer: `{score_progression['latest_better_answer']}`",
        f"- Trend overall: `{score_progression['trend_overall']}`",
        f"- Trend direction: `{score_progression['trend_direction']}`",
        f"- Trend claim allowed: `{score_progression['trend_claim_allowed']}`",
        f"- Latest official Slumbot hands / bb100 / CI lower: `{score_progression['latest_official_hands']}` / `{fmt(score_progression['latest_official_bb100'])}` / `{fmt(score_progression['latest_official_ci_lower'])}`",
        f"- Decision claim/promote: `{score_progression['trend_decision_claim_latest_is_better']}` / `{score_progression['trend_decision_promote_strength_claim']}`",
        f"- Basis: {score_progression['trend_basis']}",
        f"- Internal probe history count: `{score_progression['internal_probe_count']}`; latest iter `{score_progression['latest_internal_probe_iteration']}` / hands `{score_progression['latest_internal_probe_hands']}`",
        f"- Latest internal delta mean/lower bb/100: `{fmt(score_progression['latest_internal_delta_mean_bb100'])}` / `{fmt(score_progression['latest_internal_delta_lower_bb100'])}`; verdict `{score_progression['latest_internal_verdict']}`",
        f"- Slumbot evidence count: `{score_progression['slumbot_evidence_count']}`",
        "",
        "Speed decision:",
        "",
        f"- Decision: `{speed_decision['decision']}`",
        f"- Effective h/s latest / long: `{fmt(speed_decision['effective_hps_latest'])}` / `{fmt(speed_decision['effective_hps_long'])}`",
        f"- ETA: 100M `{speed_decision['quick100m_eta']}`, 2.7B `{speed_decision['paper_scale_eta']}`",
        f"- 2.7B at 900 h/s: `{speed_decision['paper_scale_900_eta']}`; saved `{speed_decision['paper_scale_900_saved']}`",
        "",
        "Claim audit:",
        "",
        f"- Overall: `{claim_audit['overall']}`",
        f"- Blockers / watches: `{claim_audit['blocker_count']}` / `{claim_audit['watch_count']}`",
        f"- Can claim L5 / L6: `{claim_audit['can_claim_l5']}` / `{claim_audit['can_claim_l6']}`",
        "",
        "Promotion decision:",
        "",
        f"- Overall: `{promotion_decision['overall']}`",
        f"- Target: `{promotion_decision['target_iteration']}`",
        f"- Recommendation: {promotion_decision['recommendation']}",
        "",
        "Slumbot evidence:",
        "",
        f"- Hands: `{slumbot['hands']}`",
        f"- bb/100: `{fmt(slumbot['bb_per_100'])}`",
        f"- CI lower: `{fmt(slumbot['ci_lower'])}`",
        f"- Level: `{slumbot['level']}`",
        f"- Baseline comparison: `{slumbot['baseline_comparison']}`",
        f"- Point delta vs V4 bb/100: `{fmt(slumbot['point_delta_vs_v4_bb100'])}`",
        f"- Gap to L6 target bb/100: `{fmt(slumbot['gap_to_l6_target_bb100'])}`",
        f"- Latest diagnostic: policy `{slumbot_diagnostic.get('policy_mode')}`, hands `{slumbot_diagnostic.get('hands')}`, bb/100 `{fmt(slumbot_diagnostic.get('bb_per_100'))}`, CI lower `{fmt(slumbot_diagnostic.get('ci_lower'))}`, kind `{slumbot_diagnostic.get('kind')}`",
        f"- Diagnostic delta vs official bb/100: `{fmt(slumbot_diagnostic.get('delta_vs_official_bb100'))}`",
        "- Diagnostic note: excluded from L5/L6 claims; use it only to debug selector/policy leaks.",
        f"- Paired selector diagnostic: `{len(diagnostic_pairs)}` completed pair(s)",
        f"- Latest selector pair target: `{selector_pair_target}`",
        f"- Latest selector pair greedy bb/100: `{fmt(selector_pair_greedy.get('bb_per_100'))}` over `{selector_pair_greedy.get('hands')}` hands",
        f"- Latest selector pair callguard bb/100: `{fmt(selector_pair_callguard.get('bb_per_100'))}` over `{selector_pair_callguard.get('hands')}` hands",
        f"- Latest selector pair callguard-greedy delta bb/100: `{fmt(latest_selector_pair.get('delta_callguard_vs_greedy_bb_per_100'))}`",
    ]
    if active_selector_pair:
        lines.extend(
            [
                f"- Active selector pair: `{active_selector_pair.get('token')}` state `{active_selector_pair.get('state')}`; checkpoint `{active_selector_pair.get('checkpoint_iteration')}` / `{active_selector_pair.get('checkpoint_hands')}`; min hands `{active_selector_pair.get('min_training_hands')}`",
                f"- Active selector readiness: `{active_selector_pair.get('readiness_by_policy')}`; planned hands per policy `{active_selector_pair.get('planned_hands_per_policy')}`",
            ]
        )
    lines.extend([
        "",
        "Next evidence:",
        "",
        f"- Internal probe: last target `{next_evidence['internal_probe_target']}` command `{next_evidence['internal_probe_state']}`; verdict `{next_evidence['internal_probe_verdict']}`; latest-best `{next_evidence['internal_probe_latest_is_best_opponents']}/{next_evidence['internal_probe_opponent_count']}`; mean bb/100 `{fmt(next_evidence['internal_probe_mean_latest_bb100'])}`; mean lower `{fmt(next_evidence['internal_probe_mean_lower_bound_bb100'])}`",
        f"- Next internal probe: target `{next_evidence['next_internal_probe_target']}` state `{next_evidence['next_internal_probe_state']}`",
        f"- Next external eval: `{next_evidence['next_external_eval_target_hands']}` hands, `{next_evidence['next_external_eval_state']}`, ETA `{next_evidence['next_external_eval_eta']}`",
        f"- Promotion eval: `{next_evidence['next_promotion_target_hands']}` hands, ETA `{next_evidence['next_promotion_eta']}`",
        "",
        "Preflop intervention:",
        "",
        f"- Source plan: `{intervention['source_plan']}`",
        f"- Overall: `{intervention['overall']}`",
        f"- Recommendation: {intervention['recommendation']}",
        f"- Plan target / plan live / plan checkpoint iteration: `{intervention['target_iteration']}` / `{intervention['live_iteration']}` / `{intervention['checkpoint_iteration']}`",
        f"- Current live / checkpoint iteration: `{intervention.get('current_live_iteration')}` / `{intervention.get('current_checkpoint_iteration')}`",
        f"- Dry-run command emitted: `{intervention['dry_run_command_emitted']}`",
        f"- Context needed / SB-open weak / BB selector leak: `{intervention['context_preflop_intervention_needed']}` / `{intervention['sb_open_weak']}` / `{intervention['selector_preflop_leak_confirmed']}`",
        f"- Planned priors: `{intervention['planned_action_priors']}`",
        f"- Trend overall / latest iteration: `{intervention['trend_overall']}` / `{intervention['trend_latest_iteration']}`",
        f"- Trend preflop all-in delta / call delta: `{fmt(intervention['trend_preflop_allin_delta'])}` / `{fmt(intervention['trend_preflop_call_delta'])}`",
        "",
        "Blockers:",
        "",
    ])
    for blocker in summary["blockers"]:
        lines.append(f"- {blocker}")
    lines.extend(["", "Claim rule:", ""])
    lines.append(f"- {summary['claims']['claim_rule']}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_summary(Path(args.run_dir))
    print(f"strength={summary['strength_answer']}")
    print(f"health={summary['health']} quality={summary['quality_status']}")
    print(f"live_iter={summary['live']['iteration']} ckpt_iter={summary['checkpoint']['checkpoint_iteration']}")
    print(f"slumbot_level={summary['slumbot']['level']} bb100={summary['slumbot']['bb_per_100']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(Path(args.out_md), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
