#!/usr/bin/env python3
"""Plan a guarded V5 preflop-prior intervention without launching training.

The normal continuation path requires a gate PASS. When the only blocker is a
known preflop health WARN, this helper emits an explicit human-review plan
instead of silently doing nothing or auto-cutting over.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} is not a JSON object"}


def as_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def resolve_path(path_text: Any, repo: str) -> Path:
    path = Path(str(path_text or ""))
    if path.is_absolute():
        return path
    return Path(repo) / path


def ps_quote(value: str) -> str:
    if value == "":
        return "''"
    if all(ch.isalnum() or ch in "_-./:\\" for ch in value):
        return value
    return "'" + value.replace("'", "''") + "'"


def ps_command(parts: list[str]) -> str:
    return " ".join(ps_quote(str(part)) for part in parts)


def nonpass_gate_checks(gate: dict[str, Any]) -> list[dict[str, str]]:
    checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
    result = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        if check.get("status") != "PASS":
            result.append(
                {
                    "name": str(check.get("name")),
                    "status": str(check.get("status")),
                    "detail": str(check.get("detail")),
                }
            )
    return result


def gate_target_from(path: Path, gate: dict[str, Any]) -> int | None:
    target = gate.get("target_iteration")
    if isinstance(target, int):
        return target
    parts = path.stem.split("_")
    if len(parts) >= 3 and parts[0] == "gate":
        try:
            return int(parts[1])
        except ValueError:
            return None
    return None


def selector_pair_token(path: Path) -> str:
    prefix = "slumbot_selector_pair_"
    suffix = "_status.json"
    name = path.name
    if name.startswith(prefix) and name.endswith(suffix):
        return name[len(prefix) : -len(suffix)]
    return path.stem


def selector_pair_sort_key(item: dict[str, Any], target_iteration: int) -> tuple[int, int, int, float, str]:
    status = item["status"]
    frozen = status.get("frozen_summary") if isinstance(status.get("frozen_summary"), dict) else {}
    frozen_iteration = frozen.get("iteration")
    frozen_hands = frozen.get("total_hands")
    state = status.get("state")
    exact_target = 1 if isinstance(frozen_iteration, int) and frozen_iteration == target_iteration else 0
    pass_state = 1 if state == "PASS" else 0
    iteration_value = int(frozen_iteration) if isinstance(frozen_iteration, int) else -1
    hands_value = float(frozen_hands) if isinstance(frozen_hands, (int, float)) else -1.0
    return (exact_target, pass_state, iteration_value, hands_value, str(status.get("checked_at") or ""))


def load_selector_pair_status(run_dir: Path, target_iteration: int) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = load_json(path)
        if status.get("_missing") or status.get("_load_error"):
            continue
        frozen = status.get("frozen_summary") if isinstance(status.get("frozen_summary"), dict) else {}
        frozen_iteration = frozen.get("iteration")
        if isinstance(frozen_iteration, int) and target_iteration > 0 and frozen_iteration > target_iteration:
            continue
        candidates.append({"path": path, "status": status})
    if not candidates:
        return {"_missing": True}
    candidates.sort(key=lambda item: selector_pair_sort_key(item, target_iteration))
    selected = candidates[-1]
    selected["status"]["source_status"] = str(selected["path"])
    selected["status"]["source_token"] = selector_pair_token(selected["path"])
    return selected["status"]


def resolve_target_iteration(run_dir: Path, requested: int, auto_target: bool) -> tuple[int, str]:
    if not auto_target and requested > 0:
        return requested, "explicit"

    internal = load_json(run_dir / "internal_strength_watch_status.json")
    internal_target = (
        internal.get("latest_readiness", {}).get("target_iteration")
        if isinstance(internal.get("latest_readiness"), dict)
        else None
    )
    if isinstance(internal_target, int) and internal_target > 0:
        return internal_target, "internal_strength_latest_readiness"

    records = []
    for path in sorted(run_dir.glob("gate_*_status.json")):
        gate = load_json(path)
        target = gate_target_from(path, gate)
        if target is None:
            continue
        records.append({"target": target, "overall": gate.get("overall")})
    if records:
        latest_pass = max((item["target"] for item in records if item["overall"] == "PASS"), default=None)
        pending_after_pass = [
            item["target"]
            for item in records
            if item["overall"] == "PENDING" and (latest_pass is None or item["target"] > latest_pass)
        ]
        if pending_after_pass:
            return min(pending_after_pass), "next_pending_gate"
        if latest_pass is not None:
            return latest_pass, "latest_pass_gate"

    if requested > 0:
        return requested, "explicit_fallback"
    return 4200, "default_fallback"


def health_preflop_warnings(health: dict[str, Any]) -> list[dict[str, str]]:
    checks = health.get("checks") if isinstance(health.get("checks"), list) else []
    warnings = []
    for check in checks:
        if not isinstance(check, dict):
            continue
        if check.get("status") in {"WARN", "FAIL"} and "preflop" in str(check.get("name", "")).lower():
            warnings.append(
                {
                    "name": str(check.get("name")),
                    "status": str(check.get("status")),
                    "detail": str(check.get("detail")),
                }
            )
    return warnings


def build_continue_dry_run_command(args: argparse.Namespace, *, skip_gate_check: bool) -> str:
    parts = [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        "scripts\\alpha_holdem\\v5_continue_after_gate.ps1",
        "-Repo",
        args.repo,
        "-SourceRunDir",
        str(Path(args.run_dir)),
        "-TargetIteration",
        str(args.target_iteration),
        "-ExpectedPoolSnapshots",
        str(args.expected_pool_snapshots),
        "-NewRunId",
        args.new_run_id,
        "-NewRunDir",
        args.new_run_dir,
        "-Python",
        args.python,
        "-Workers",
        str(args.workers),
        "-NextGateIteration",
        str(args.next_gate_iteration),
        "-PostflopActionPriorCoef",
        str(args.postflop_action_prior_coef),
        "-PostflopActionPriorTarget",
        args.postflop_action_prior_target,
        "-PreflopActionPriorCoef",
        str(args.preflop_action_prior_coef),
        "-PreflopActionPriorTarget",
        args.preflop_action_prior_target,
        "-PreflopSbOpenActionPriorCoef",
        str(args.preflop_sb_open_action_prior_coef),
        "-PreflopSbOpenActionPriorTarget",
        args.preflop_sb_open_action_prior_target,
        "-PreflopBbVsOpenActionPriorCoef",
        str(args.preflop_bb_vs_open_action_prior_coef),
        "-PreflopBbVsOpenActionPriorTarget",
        args.preflop_bb_vs_open_action_prior_target,
        "-StartNextGateWatcher",
        "-StartGateSequenceWatcher",
        "-StartHealthWatcher",
        "-StartThroughputWatcher",
        "-StartDashboardWatcher",
        "-StartEvalCadenceWatcher",
        "-StartSlumbotQuick5kWatcher",
        "-StartSlumbotPromotion20kWatcher",
        "-StartSlumbotFormal100kWatcher",
        "-StartInternalStrengthWatcher",
        "-StartCheckpointArchiveWatcher",
        "-ReportPath",
        args.report_path,
    ]
    if skip_gate_check:
        parts.append("-SkipGateCheck")
    return ps_command(parts)


def selector_pair_summary(args: argparse.Namespace, run_dir: Path) -> dict[str, Any]:
    selector_pair = load_selector_pair_status(run_dir, args.target_iteration)
    results = selector_pair.get("results") if isinstance(selector_pair.get("results"), dict) else {}
    plans = selector_pair.get("plans") if isinstance(selector_pair.get("plans"), dict) else {}
    greedy = results.get("greedy") if isinstance(results.get("greedy"), dict) else {}
    callguard = (
        results.get("preflop-callguard")
        if isinstance(results.get("preflop-callguard"), dict)
        else {}
    )
    greedy_ci = greedy.get("ci_summary") if isinstance(greedy.get("ci_summary"), dict) else {}
    callguard_ci = (
        callguard.get("ci_summary") if isinstance(callguard.get("ci_summary"), dict) else {}
    )

    def loss_report(policy: str) -> dict[str, Any]:
        plan = plans.get(policy) if isinstance(plans.get(policy), dict) else {}
        artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), dict) else {}
        loss_path = artifacts.get("loss_report_json")
        if not loss_path:
            return {"_missing": True}
        return load_json(resolve_path(loss_path, args.repo))

    greedy_loss = loss_report("greedy")
    callguard_loss = loss_report("preflop-callguard")
    greedy_rates = greedy_loss.get("rates") if isinstance(greedy_loss.get("rates"), dict) else {}
    callguard_rates = (
        callguard_loss.get("rates") if isinstance(callguard_loss.get("rates"), dict) else {}
    )

    delta = as_float(selector_pair.get("delta_callguard_vs_greedy_bb_per_100"))
    greedy_call = as_float(greedy_rates.get("bb_vs_open_call_rate"))
    greedy_raise = as_float(greedy_rates.get("bb_vs_open_raise_rate"))
    callguard_call = as_float(callguard_rates.get("bb_vs_open_call_rate"))
    callguard_raise = as_float(callguard_rates.get("bb_vs_open_raise_rate"))
    greedy_sb_fold = as_float(greedy_rates.get("sb_open_fold_rate"))
    greedy_sb_call = as_float(greedy_rates.get("sb_open_call_rate"))
    greedy_sb_raise = as_float(greedy_rates.get("sb_open_raise_rate"))
    greedy_sb_allin = as_float(greedy_rates.get("sb_open_allin_rate"))
    callguard_sb_fold = as_float(callguard_rates.get("sb_open_fold_rate"))
    callguard_sb_call = as_float(callguard_rates.get("sb_open_call_rate"))
    callguard_sb_raise = as_float(callguard_rates.get("sb_open_raise_rate"))
    callguard_sb_allin = as_float(callguard_rates.get("sb_open_allin_rate"))

    return {
        "state": selector_pair.get("state"),
        "checked_at": selector_pair.get("checked_at"),
        "source_status": selector_pair.get("source_status"),
        "source_token": selector_pair.get("source_token"),
        "planned_hands_per_policy": selector_pair.get("planned_hands_per_policy"),
        "frozen_iteration": (selector_pair.get("frozen_summary") or {}).get("iteration")
        if isinstance(selector_pair.get("frozen_summary"), dict)
        else None,
        "frozen_hands": (selector_pair.get("frozen_summary") or {}).get("total_hands")
        if isinstance(selector_pair.get("frozen_summary"), dict)
        else None,
        "greedy_bb_per_100": as_float(greedy_ci.get("bb_per_100")),
        "greedy_hands": greedy_ci.get("hands"),
        "greedy_ci_lower": as_float(greedy_ci.get("lower_bound_bb_per_100")),
        "callguard_bb_per_100": as_float(callguard_ci.get("bb_per_100")),
        "callguard_hands": callguard_ci.get("hands"),
        "callguard_ci_lower": as_float(callguard_ci.get("lower_bound_bb_per_100")),
        "delta_callguard_vs_greedy_bb_per_100": delta,
        "greedy_bb_vs_open_call_rate": greedy_call,
        "greedy_bb_vs_open_raise_rate": greedy_raise,
        "callguard_bb_vs_open_call_rate": callguard_call,
        "callguard_bb_vs_open_raise_rate": callguard_raise,
        "greedy_sb_open_fold_rate": greedy_sb_fold,
        "greedy_sb_open_call_rate": greedy_sb_call,
        "greedy_sb_open_raise_rate": greedy_sb_raise,
        "greedy_sb_open_allin_rate": greedy_sb_allin,
        "callguard_sb_open_fold_rate": callguard_sb_fold,
        "callguard_sb_open_call_rate": callguard_sb_call,
        "callguard_sb_open_raise_rate": callguard_sb_raise,
        "callguard_sb_open_allin_rate": callguard_sb_allin,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir)
    gate = load_json(run_dir / f"gate_{args.target_iteration}_status.json")
    health = load_json(run_dir / "health_status.json")
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    action_prior_trend = load_json(run_dir / "v5_action_prior_trend.json")
    scorecard = load_json(run_dir / "v5_scorecard.json")
    health_warning_diagnosis = load_json(run_dir / "v5_health_warning_diagnosis.json")
    selector_pair = selector_pair_summary(args, run_dir)

    gate_overall = gate.get("overall")
    gate_checkpoint = gate.get("checkpoint") if isinstance(gate.get("checkpoint"), dict) else {}
    gate_latest = gate.get("latest") if isinstance(gate.get("latest"), dict) else {}
    health_latest = health.get("latest") if isinstance(health.get("latest"), dict) else {}
    ckpt_iter = gate_checkpoint.get("iteration")
    gate_live_iter = gate_latest.get("iteration")
    health_live_iter = health_latest.get("iteration")
    live_iter_candidates = [item for item in (gate_live_iter, health_live_iter) if isinstance(item, int)]
    live_iter = max(live_iter_candidates) if live_iter_candidates else gate_live_iter
    ckpt_reached = isinstance(ckpt_iter, int) and ckpt_iter >= args.target_iteration
    gate_nonpass = nonpass_gate_checks(gate)
    nonpass_names = {item["name"] for item in gate_nonpass}
    only_health_warn = (
        gate_overall == "WARN"
        and ckpt_reached
        and bool(gate_nonpass)
        and nonpass_names.issubset({"health_status", "health_refresh"})
    )

    preflop_warnings = health_preflop_warnings(health)
    health_diag_overall = health_warning_diagnosis.get("overall")
    health_diag_metrics = (
        health_warning_diagnosis.get("metrics")
        if isinstance(health_warning_diagnosis.get("metrics"), dict)
        else {}
    )
    preflop_probe_overall = preflop_probe.get("overall")
    action_trend_overall = action_prior_trend.get("overall")
    action_trend_candidate = (
        action_prior_trend.get("candidate")
        if isinstance(action_prior_trend.get("candidate"), dict)
        else {}
    )
    action_trend_latest_iteration = action_trend_candidate.get("latest_iteration")
    trend_lag_iterations = (
        int(live_iter) - int(action_trend_latest_iteration)
        if isinstance(live_iter, int) and isinstance(action_trend_latest_iteration, int)
        else None
    )
    internal_probe_latest = (
        scorecard.get("internal_probes", {}).get("latest", {})
        if isinstance(scorecard.get("internal_probes"), dict)
        else {}
    ) or {}
    internal_probe_verdict = internal_probe_latest.get("verdict")
    internal_latest_is_best = internal_probe_latest.get("latest_is_best_opponents")
    internal_opponent_count = internal_probe_latest.get("opponent_count")
    internal_mean_lower = internal_probe_latest.get("mean_latest_lower_bound_bb100")
    selector_state = selector_pair.get("state")
    selector_delta = selector_pair.get("delta_callguard_vs_greedy_bb_per_100")
    greedy_call_rate = selector_pair.get("greedy_bb_vs_open_call_rate")
    greedy_raise_rate = selector_pair.get("greedy_bb_vs_open_raise_rate")
    callguard_call_rate = selector_pair.get("callguard_bb_vs_open_call_rate")
    callguard_raise_rate = selector_pair.get("callguard_bb_vs_open_raise_rate")
    greedy_sb_open_fold_rate = selector_pair.get("greedy_sb_open_fold_rate")
    greedy_sb_open_call_rate = selector_pair.get("greedy_sb_open_call_rate")
    greedy_sb_open_raise_rate = selector_pair.get("greedy_sb_open_raise_rate")
    greedy_sb_open_allin_rate = selector_pair.get("greedy_sb_open_allin_rate")
    selector_pair_pass = selector_state == "PASS"
    selector_gap_large = (
        selector_delta is not None and selector_delta >= args.selector_delta_warn_bb100
    )
    greedy_defense_suppressed = (
        greedy_call_rate is not None
        and greedy_raise_rate is not None
        and greedy_call_rate <= args.selector_greedy_call_max
        and greedy_raise_rate >= args.selector_greedy_raise_min
    )
    callguard_restores_calls = (
        callguard_call_rate is not None
        and callguard_call_rate >= args.selector_callguard_call_min
    )
    selector_preflop_leak_confirmed = (
        selector_pair_pass
        and selector_gap_large
        and greedy_defense_suppressed
        and callguard_restores_calls
    )
    sb_open_weak = (
        selector_pair_pass
        and greedy_sb_open_fold_rate is not None
        and greedy_sb_open_call_rate is not None
        and greedy_sb_open_raise_rate is not None
        and (
            greedy_sb_open_fold_rate >= args.sb_open_fold_warn
            or greedy_sb_open_call_rate >= args.sb_open_call_warn
            or greedy_sb_open_raise_rate <= args.sb_open_raise_warn
        )
    )
    context_preflop_intervention_needed = selector_preflop_leak_confirmed or sb_open_weak
    if sb_open_weak and args.preflop_sb_open_action_prior_coef <= 0.0:
        args.preflop_sb_open_action_prior_coef = args.recommended_preflop_sb_open_action_prior_coef
    if selector_preflop_leak_confirmed and args.preflop_bb_vs_open_action_prior_coef <= 0.0:
        args.preflop_bb_vs_open_action_prior_coef = args.recommended_preflop_bb_vs_open_action_prior_coef

    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if gate.get("_missing"):
        add("gate_status", "PENDING", f"gate_{args.target_iteration}_status.json missing")
    elif gate.get("_load_error"):
        add("gate_status", "FAIL", str(gate["_load_error"]))
    else:
        add("gate_status", "PASS" if gate_overall == "PASS" else str(gate_overall), f"gate overall {gate_overall}")

    if ckpt_reached:
        add("checkpoint_reached", "PASS", f"checkpoint iteration {ckpt_iter} >= {args.target_iteration}")
    else:
        add("checkpoint_reached", "PENDING", f"checkpoint iteration {ckpt_iter} < {args.target_iteration}")

    if gate_overall == "PASS":
        add("strict_gate", "PASS", "normal continuation gate passed")
    elif only_health_warn:
        add("strict_gate", "WARN", "gate WARN is limited to health/preflop intervention evidence")
    elif gate.get("_missing") or gate_overall is None:
        add("strict_gate", "PENDING", "target gate status is not available yet")
    else:
        add("strict_gate", "PENDING" if gate_overall == "PENDING" else "FAIL", f"non-pass checks: {gate_nonpass}")

    if preflop_warnings:
        add("preflop_health_signal", "WARN", "; ".join(item["detail"] for item in preflop_warnings))
    else:
        add("preflop_health_signal", "PASS", "no health preflop WARN/FAIL checks")

    if health_diag_overall == "FAIL_COLLAPSE_RISK":
        add("health_warning_diagnosis", "FAIL", "rolling health diagnosis reports collapse risk")
    elif health_diag_overall == "PREFLOP_ALLIN_SUSTAINED_WARN":
        add(
            "health_warning_diagnosis",
            "WARN",
            "rolling preflop all-in warning: "
            f"mean={health_diag_metrics.get('preflop_allin_mean')}, "
            f"latest={health_diag_metrics.get('preflop_allin_latest')}, "
            f"warn_fraction={health_diag_metrics.get('preflop_allin_warn_fraction')}",
        )
    elif health_diag_overall:
        add("health_warning_diagnosis", "PASS", f"rolling health diagnosis {health_diag_overall}")
    else:
        add("health_warning_diagnosis", "PENDING", "rolling health diagnosis unavailable")

    if preflop_probe_overall in {"WARN", "FAIL"}:
        add("preflop_probe", "WARN", f"preflop probe {preflop_probe_overall}")
    elif preflop_probe_overall:
        add("preflop_probe", "PASS", f"preflop probe {preflop_probe_overall}")
    else:
        add("preflop_probe", "PENDING", "preflop probe unavailable")

    if action_trend_overall in {"WARN", "FAIL"}:
        add("action_prior_trend", "WARN", f"action-prior trend {action_trend_overall}")
    elif action_trend_overall:
        add("action_prior_trend", "PASS", f"action-prior trend {action_trend_overall}")
    else:
        add("action_prior_trend", "PENDING", "action-prior trend unavailable")

    if trend_lag_iterations is None:
        add("action_prior_trend_freshness", "PENDING", "cannot compute trend iteration lag")
    elif trend_lag_iterations > args.max_trend_iteration_lag:
        add(
            "action_prior_trend_freshness",
            "WARN",
            f"trend latest iteration {action_trend_latest_iteration} lags live iteration {live_iter} by {trend_lag_iterations}",
        )
    else:
        add(
            "action_prior_trend_freshness",
            "PASS",
            f"trend latest iteration {action_trend_latest_iteration}; live iteration {live_iter}",
        )

    if internal_probe_verdict == "REGRESSION_RISK_INTERNAL":
        add(
            "internal_probe_verdict",
            "WARN",
            f"{internal_probe_verdict}; latest-best {internal_latest_is_best}/{internal_opponent_count}; mean lower {internal_mean_lower}",
        )
    elif internal_probe_verdict:
        add(
            "internal_probe_verdict",
            "PASS" if internal_probe_verdict == "LATEST_BEST_INTERNAL" else "WARN",
            f"{internal_probe_verdict}; latest-best {internal_latest_is_best}/{internal_opponent_count}; mean lower {internal_mean_lower}",
        )
    else:
        add("internal_probe_verdict", "PENDING", "internal probe scorecard unavailable")

    if selector_state:
        add(
            "selector_pair_state",
            "PASS" if selector_pair_pass else "PENDING" if selector_state == "RUNNING" else "WARN",
            f"state={selector_state}; frozen_iter={selector_pair.get('frozen_iteration')}; planned_hands={selector_pair.get('planned_hands_per_policy')}",
        )
    else:
        add("selector_pair_state", "PENDING", "selector pair diagnostic unavailable")

    if selector_delta is None:
        add("selector_pair_delta", "PENDING", "callguard-greedy delta unavailable")
    elif selector_gap_large:
        add("selector_pair_delta", "WARN", f"callguard-greedy delta {selector_delta:.3f} bb/100")
    else:
        add("selector_pair_delta", "PASS", f"callguard-greedy delta {selector_delta:.3f} bb/100")

    if greedy_defense_suppressed:
        add(
            "greedy_bb_defense",
            "WARN",
            f"BB vs open call={greedy_call_rate:.3f}, raise={greedy_raise_rate:.3f}",
        )
    elif greedy_call_rate is None or greedy_raise_rate is None:
        add("greedy_bb_defense", "PENDING", "greedy loss-report rates unavailable")
    else:
        add(
            "greedy_bb_defense",
            "PASS",
            f"BB vs open call={greedy_call_rate:.3f}, raise={greedy_raise_rate:.3f}",
        )

    if callguard_restores_calls:
        add(
            "callguard_bb_defense",
            "WARN",
            f"callguard BB vs open call={callguard_call_rate:.3f}, raise={callguard_raise_rate}",
        )
    elif callguard_call_rate is None:
        add("callguard_bb_defense", "PENDING", "callguard loss-report rates unavailable")
    else:
        add(
            "callguard_bb_defense",
            "PASS",
            f"callguard BB vs open call={callguard_call_rate:.3f}, raise={callguard_raise_rate}",
        )

    if sb_open_weak:
        add(
            "greedy_sb_open",
            "WARN",
            "SB open fold/call/raise/all-in="
            f"{greedy_sb_open_fold_rate:.3f}/{greedy_sb_open_call_rate:.3f}/"
            f"{greedy_sb_open_raise_rate:.3f}/{greedy_sb_open_allin_rate}",
        )
    elif (
        greedy_sb_open_fold_rate is None
        or greedy_sb_open_call_rate is None
        or greedy_sb_open_raise_rate is None
    ):
        add("greedy_sb_open", "PENDING", "greedy SB-open loss-report rates unavailable")
    else:
        add(
            "greedy_sb_open",
            "PASS",
            "SB open fold/call/raise/all-in="
            f"{greedy_sb_open_fold_rate:.3f}/{greedy_sb_open_call_rate:.3f}/"
            f"{greedy_sb_open_raise_rate:.3f}/{greedy_sb_open_allin_rate}",
        )

    if context_preflop_intervention_needed and ckpt_reached:
        overall = "CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED"
        recommendation = (
            "selector/loss evidence requires a context-conditioned preflop review; "
            "separate SB first-action tuning from BB facing-open tuning, and do not "
            "treat callguard as official strength"
        )
        dry_run_command = build_continue_dry_run_command(args, skip_gate_check=True)
    elif health_diag_overall == "FAIL_COLLAPSE_RISK":
        overall = "NOT_READY"
        recommendation = "do not cut over; rolling health diagnosis indicates collapse risk"
        dry_run_command = ""
    elif gate_overall == "PASS":
        dry_run_command = build_continue_dry_run_command(args, skip_gate_check=False)
        if internal_probe_verdict == "REGRESSION_RISK_INTERNAL" or health_diag_overall == "PREFLOP_ALLIN_SUSTAINED_WARN":
            overall = "STRICT_GATE_PASS_REVIEW_REQUIRED"
            recommendation = (
                "gate passed and dry-run is available, but internal/rolling health evidence requires review; "
                "do not execute cutover without explicit review, and prefer waiting for the next scheduled Slumbot evidence "
                "unless intentionally testing the preflop-prior intervention"
            )
        else:
            overall = "STRICT_GATE_PASS_READY"
            recommendation = "normal continuation dry-run is ready; execute only with explicit approval"
    elif only_health_warn and (
        preflop_warnings
        or preflop_probe_overall in {"WARN", "FAIL"}
        or health_diag_overall == "PREFLOP_ALLIN_SUSTAINED_WARN"
    ):
        overall = "PREFLOP_INTERVENTION_CANDIDATE"
        recommendation = (
            "target checkpoint is reached, and the remaining gate blocker is health/preflop WARN; "
            "review manually before any SkipGateCheck execution"
        )
        dry_run_command = build_continue_dry_run_command(args, skip_gate_check=True)
    elif gate_overall == "PENDING" or not ckpt_reached:
        overall = "PENDING_CHECKPOINT"
        recommendation = "wait for the target checkpoint and re-run this planner"
        dry_run_command = ""
    else:
        overall = "NOT_READY"
        recommendation = "do not cut over; blockers are broader than the targeted preflop intervention"
        dry_run_command = ""

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": overall,
        "recommendation": recommendation,
        "run_dir": str(run_dir),
        "target_iteration": args.target_iteration,
        "target_source": getattr(args, "target_source", "explicit"),
        "new_run_id": args.new_run_id,
        "new_run_dir": args.new_run_dir,
        "gate_overall": gate_overall,
        "gate_nonpass_checks": gate_nonpass,
        "checkpoint_iteration": ckpt_iter,
        "live_iteration": live_iter,
        "checkpoint_hands": gate_checkpoint.get("total_hands"),
        "health_overall": health.get("overall"),
        "health_warning_diagnosis": health_diag_overall,
        "health_warning_metrics": health_diag_metrics,
        "preflop_health_warnings": preflop_warnings,
        "preflop_probe_overall": preflop_probe_overall,
        "action_prior_trend_overall": action_trend_overall,
        "action_prior_trend_latest_iteration": action_trend_latest_iteration,
        "action_prior_trend_lag_iterations": trend_lag_iterations,
        "internal_probe_verdict": internal_probe_verdict,
        "internal_probe_latest_is_best_opponents": internal_latest_is_best,
        "internal_probe_opponent_count": internal_opponent_count,
        "internal_probe_mean_lower_bound_bb100": internal_mean_lower,
        "selector_pair": selector_pair,
        "selector_preflop_leak_confirmed": selector_preflop_leak_confirmed,
        "sb_open_weak": sb_open_weak,
        "context_preflop_intervention_needed": context_preflop_intervention_needed,
        "planned_action_priors": {
            "preflop_action_prior_coef": args.preflop_action_prior_coef,
            "preflop_action_prior_target": args.preflop_action_prior_target,
            "preflop_sb_open_action_prior_coef": args.preflop_sb_open_action_prior_coef,
            "preflop_sb_open_action_prior_target": args.preflop_sb_open_action_prior_target,
            "preflop_bb_vs_open_action_prior_coef": args.preflop_bb_vs_open_action_prior_coef,
            "preflop_bb_vs_open_action_prior_target": args.preflop_bb_vs_open_action_prior_target,
        },
        "dry_run_command": dry_run_command,
        "checks": checks,
        "safety": [
            "This planner is read-only and does not stop or start trainers.",
            "SkipGateCheck is only acceptable for a reviewed targeted intervention, never for a strength claim.",
            "No L5/L6 claim is allowed without 100k+ Slumbot hands and a positive CI lower bound.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# V5 Preflop Intervention Plan",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Run dir: `{summary['run_dir']}`",
        f"- Target iteration: `{summary['target_iteration']}`",
        f"- Target source: `{summary['target_source']}`",
        f"- Live iteration: `{summary['live_iteration']}`",
        f"- Checkpoint iteration / hands: `{summary['checkpoint_iteration']}` / `{summary['checkpoint_hands']}`",
        f"- Gate overall: `{summary['gate_overall']}`",
        f"- Health overall: `{summary['health_overall']}`",
        f"- Rolling health diagnosis: `{summary['health_warning_diagnosis']}`",
        f"- Preflop probe overall: `{summary['preflop_probe_overall']}`",
        f"- Action-prior trend overall: `{summary['action_prior_trend_overall']}`",
        f"- Action-prior trend latest iteration / lag: `{summary['action_prior_trend_latest_iteration']}` / `{summary['action_prior_trend_lag_iterations']}`",
        f"- Internal probe verdict: `{summary['internal_probe_verdict']}`",
        f"- Internal probe latest-best: `{summary['internal_probe_latest_is_best_opponents']}` / `{summary['internal_probe_opponent_count']}`",
        f"- Internal probe mean lower bb/100: `{summary['internal_probe_mean_lower_bound_bb100']}`",
        f"- Selector pair state: `{summary['selector_pair'].get('state')}`",
        f"- Selector pair source: `{summary['selector_pair'].get('source_status')}`",
        f"- Selector pair greedy / callguard bb/100: `{summary['selector_pair'].get('greedy_bb_per_100')}` / `{summary['selector_pair'].get('callguard_bb_per_100')}`",
        f"- Selector pair delta bb/100: `{summary['selector_pair'].get('delta_callguard_vs_greedy_bb_per_100')}`",
        f"- Greedy BB vs open call / raise: `{summary['selector_pair'].get('greedy_bb_vs_open_call_rate')}` / `{summary['selector_pair'].get('greedy_bb_vs_open_raise_rate')}`",
        f"- Callguard BB vs open call / raise: `{summary['selector_pair'].get('callguard_bb_vs_open_call_rate')}` / `{summary['selector_pair'].get('callguard_bb_vs_open_raise_rate')}`",
        f"- Greedy SB open fold / call / raise / all-in: `{summary['selector_pair'].get('greedy_sb_open_fold_rate')}` / `{summary['selector_pair'].get('greedy_sb_open_call_rate')}` / `{summary['selector_pair'].get('greedy_sb_open_raise_rate')}` / `{summary['selector_pair'].get('greedy_sb_open_allin_rate')}`",
        f"- Selector preflop leak confirmed: `{summary['selector_preflop_leak_confirmed']}`",
        f"- SB open weak: `{summary['sb_open_weak']}`",
        f"- Context preflop intervention needed: `{summary['context_preflop_intervention_needed']}`",
        f"- Planned global preflop prior: coef `{summary['planned_action_priors'].get('preflop_action_prior_coef')}`, target `{summary['planned_action_priors'].get('preflop_action_prior_target')}`",
        f"- Planned SB-open prior: coef `{summary['planned_action_priors'].get('preflop_sb_open_action_prior_coef')}`, target `{summary['planned_action_priors'].get('preflop_sb_open_action_prior_target')}`",
        f"- Planned BB-vs-open prior: coef `{summary['planned_action_priors'].get('preflop_bb_vs_open_action_prior_coef')}`, target `{summary['planned_action_priors'].get('preflop_bb_vs_open_action_prior_target')}`",
        "",
        "Gate non-pass checks:",
        "",
    ]
    for check in summary["gate_nonpass_checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    if not summary["gate_nonpass_checks"]:
        lines.append("- none")
    lines.extend(["", "Checks:", ""])
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.extend(["", "Dry-run command:", ""])
    if summary["dry_run_command"]:
        lines.extend(["```powershell", summary["dry_run_command"], "```", ""])
    else:
        lines.append("- not emitted")
        lines.append("")
    lines.extend(["Safety:", ""])
    for item in summary["safety"]:
        lines.append(f"- {item}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--target-iteration", type=int, default=4200)
    parser.add_argument("--auto-target", action="store_true")
    parser.add_argument("--expected-pool-snapshots", type=int, default=5)
    parser.add_argument("--repo", default="C:\\Users\\a8594\\CardPilot")
    parser.add_argument("--python", default="python")
    parser.add_argument("--workers", type=int, default=22)
    parser.add_argument("--next-gate-iteration", type=int, default=4300)
    parser.add_argument("--new-run-id", default="")
    parser.add_argument("--new-run-dir", default="")
    parser.add_argument("--postflop-action-prior-coef", type=float, default=0.02)
    parser.add_argument("--postflop-action-prior-target", default="0.15,0.30,0.52,0.03")
    parser.add_argument("--preflop-action-prior-coef", type=float, default=0.02)
    parser.add_argument("--preflop-action-prior-target", default="0.24,0.36,0.38,0.02")
    parser.add_argument("--preflop-sb-open-action-prior-coef", type=float, default=0.0)
    parser.add_argument("--preflop-sb-open-action-prior-target", default="0.15,0.20,0.63,0.02")
    parser.add_argument("--preflop-bb-vs-open-action-prior-coef", type=float, default=0.0)
    parser.add_argument("--preflop-bb-vs-open-action-prior-target", default="0.25,0.55,0.18,0.02")
    parser.add_argument("--recommended-preflop-sb-open-action-prior-coef", type=float, default=0.02)
    parser.add_argument("--recommended-preflop-bb-vs-open-action-prior-coef", type=float, default=0.02)
    parser.add_argument("--max-trend-iteration-lag", type=int, default=20)
    parser.add_argument("--selector-delta-warn-bb100", type=float, default=50.0)
    parser.add_argument("--selector-greedy-call-max", type=float, default=0.05)
    parser.add_argument("--selector-greedy-raise-min", type=float, default=0.25)
    parser.add_argument("--selector-callguard-call-min", type=float, default=0.25)
    parser.add_argument("--sb-open-fold-warn", type=float, default=0.30)
    parser.add_argument("--sb-open-call-warn", type=float, default=0.35)
    parser.add_argument("--sb-open-raise-warn", type=float, default=0.30)
    parser.add_argument("--report-path", default="reports\\v5_zero_l6_fixedenv_launch.md")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    args.target_iteration, args.target_source = resolve_target_iteration(
        run_dir,
        args.target_iteration,
        args.auto_target,
    )
    if args.next_gate_iteration <= args.target_iteration:
        args.next_gate_iteration = args.target_iteration + 100
    if not args.new_run_id:
        args.new_run_id = f"{run_dir.name}_after{args.target_iteration}_prectx_r1"
    if not args.new_run_dir:
        args.new_run_dir = str(run_dir.parent / args.new_run_id)

    summary = evaluate(args)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(Path(args.out_md), summary)

    print(f"overall={summary['overall']}")
    print(f"recommendation={summary['recommendation']}")
    ready_states = {
        "STRICT_GATE_PASS_READY",
        "STRICT_GATE_PASS_REVIEW_REQUIRED",
        "PREFLOP_INTERVENTION_CANDIDATE",
        "PREFLOP_INTERVENTION_REVIEW_REQUIRED",
        "CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED",
    }
    return 0 if summary["overall"] in ready_states else 2


if __name__ == "__main__":
    raise SystemExit(main())
