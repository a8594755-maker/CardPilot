#!/usr/bin/env python3
"""Read-only L6 speed and ETA decision report.

This report separates two questions that are easy to mix up:
- are we using the current hardware efficiently enough to keep the L6 run moving;
- is it safe to change the trainer configuration now.

It never starts or stops a trainer. Any sweep/cutover remains a controlled
restart-window decision, not a live-run edit.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v5_run_dashboard import format_duration


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} root is not an object", "_path": str(path)}


def pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def finite_float(value: Any) -> float | None:
    try:
        result = float(value)
    except Exception:
        return None
    if result != result or result in {float("inf"), float("-inf")}:
        return None
    return result


def finite_int(value: Any) -> int | None:
    try:
        return int(value)
    except Exception:
        return None


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def parse_float_list(value: str) -> list[float]:
    result: list[float] = []
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        result.append(float(part))
    if not result:
        raise argparse.ArgumentTypeError("list must contain at least one float")
    return result


def eta_seconds(current_hands: int, target_hands: int, hps: float | None) -> float | None:
    if hps is None or hps <= 0:
        return None
    return max(0, target_hands - current_hands) / hps


def milestone_row(
    current_hands: int,
    checkpoint_hands: int,
    target_hands: int,
    label: str,
    measured_hps: float | None,
    target_hps_values: list[float],
) -> dict[str, Any]:
    measured_eta = eta_seconds(current_hands, target_hands, measured_hps)
    alternatives: list[dict[str, Any]] = []
    for hps in target_hps_values:
        alt_eta = eta_seconds(current_hands, target_hands, hps)
        saved = measured_eta - alt_eta if measured_eta is not None and alt_eta is not None else None
        alternatives.append(
            {
                "hps": hps,
                "eta_seconds": alt_eta,
                "eta_duration": format_duration(alt_eta),
                "time_saved_seconds": saved,
                "time_saved_duration": format_duration(saved),
            }
        )
    return {
        "label": label,
        "target_hands": target_hands,
        "remaining_live_hands": max(0, target_hands - current_hands),
        "remaining_checkpoint_hands": max(0, target_hands - checkpoint_hands),
        "measured_eta_seconds": measured_eta,
        "measured_eta_duration": format_duration(measured_eta),
        "target_hps_alternatives": alternatives,
    }


def status_from_checks(checks: list[dict[str, str]], name: str) -> str | None:
    for check in checks:
        if check.get("name") == name:
            return check.get("status")
    return None


def gate_target_from_path(path: Path) -> int | None:
    match = re.search(r"gate_(\d+)_status\.json$", path.name)
    if not match:
        return None
    return finite_int(match.group(1))


def current_gate_state(run_dir: Path) -> dict[str, Any]:
    statuses: list[dict[str, Any]] = []
    for path in run_dir.glob("gate_*_status.json"):
        target = gate_target_from_path(path)
        if target is None:
            continue
        obj = load_json(path)
        if obj.get("_missing") or obj.get("_load_error"):
            continue
        obj = dict(obj)
        obj["_path"] = str(path)
        obj["_target"] = finite_int(obj.get("target_iteration")) or target
        statuses.append(obj)

    if not statuses:
        return {"next_gate_target": None, "next_gate_overall": None, "source_path": None}

    passed = [
        item for item in statuses if item.get("overall") == "PASS" and isinstance(item.get("_target"), int)
    ]
    latest_pass_target = max((int(item["_target"]) for item in passed), default=None)
    pending = [
        item
        for item in statuses
        if item.get("overall") == "PENDING"
        and isinstance(item.get("_target"), int)
        and (latest_pass_target is None or int(item["_target"]) > latest_pass_target)
    ]
    if not pending:
        pending = [
            item
            for item in statuses
            if item.get("overall") == "PENDING" and isinstance(item.get("_target"), int)
        ]
    pending.sort(key=lambda item: int(item["_target"]))
    next_gate = pending[0] if pending else None
    return {
        "latest_pass_target": latest_pass_target,
        "next_gate_target": int(next_gate["_target"]) if next_gate else None,
        "next_gate_overall": next_gate.get("overall") if next_gate else None,
        "source_path": next_gate.get("_path") if next_gate else None,
        "next_gate_live_iteration": next_gate.get("live_iteration") if next_gate else None,
        "next_gate_checkpoint_iteration": next_gate.get("checkpoint_iteration") if next_gate else None,
        "next_gate_remaining_live_iterations": next_gate.get("remaining_live_iterations") if next_gate else None,
        "next_gate_remaining_checkpoint_iterations": next_gate.get("remaining_checkpoint_iterations") if next_gate else None,
    }


def classify(summary: dict[str, Any], args: argparse.Namespace) -> tuple[str, str]:
    health = summary["training"]["health"]
    health_diag = summary["training"]["health_warning_diagnosis"]
    throughput_overall = summary["throughput"]["overall"]
    effective_hps = finite_float(summary["throughput"]["effective_hps_latest"])
    latest_gate_overall = summary["evidence"]["next_gate_overall"]
    next_gate_target = summary["evidence"]["next_gate_target"]
    live_iteration = summary["training"]["live_iteration"]
    active_source = summary["sweep"]["active_source_trainer"]
    next_external_state = summary["evidence"]["next_external_eval_state"]

    if health_diag == "FAIL_COLLAPSE_RISK":
        return "DO_NOT_SWEEP_COLLAPSE_RISK", "Health diagnosis shows collapse risk; preserve evidence and intervene on policy health first."
    if next_external_state == "DUE":
        return "RUN_DUE_EVAL_FIRST", "A Slumbot cadence item is due; run that evidence before spending time on speed sweeps."
    if latest_gate_overall == "PENDING" and isinstance(next_gate_target, int):
        return (
            "WAIT_FOR_GATE_BEFORE_SPEED_CHANGE",
            f"Wait for gate {next_gate_target}; changing trainer configuration before the checkpoint would break this evidence window.",
        )
    if active_source is True:
        if throughput_overall == "WARN" and effective_hps is not None and effective_hps < float(args.target_effective_hps):
            return (
                "PREPARE_SWEEP_CONTROLLED_RESTART_ONLY",
                "Throughput is below target, but the source trainer is active; prepare sweep commands and execute only in a reviewed restart window.",
            )
        return "KEEP_CURRENT_RUN", "Trainer is active and throughput is acceptable enough for the current evidence window."
    if throughput_overall == "WARN":
        return "READY_TO_SWEEP_IF_EVIDENCE_CLEAN", "Trainer is not active and throughput is below target; a guarded sweep is reasonable if health/gates are clean."
    if health == "WARN":
        return "KEEP_CURRENT_RUN_HEALTH_WATCH", "Speed change is not the first priority while health is warning."
    return "KEEP_CURRENT_RUN", "No speed intervention is justified by current evidence."


def build_speed_decision(run_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    throughput = load_json(run_dir / "v5_throughput_audit.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    cadence_watch = load_json(run_dir / "v5_eval_cadence_watch_status.json")
    dashboard = load_json(run_dir / "v5_run_dashboard.json")
    next_action = load_json(run_dir / "v5_next_action_queue.json")
    health = load_json(run_dir / "health_status.json")
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")
    gates = current_gate_state(run_dir)
    sweep_plan = load_json(run_dir / "v5_throughput_sweep_plan.json")

    training_latest = pick(dashboard, "training", "latest", default={}) or {}
    current_hands = (
        finite_int(pick(dashboard, "training", "current_hands"))
        or finite_int(training_latest.get("hands"))
        or finite_int(cadence_watch.get("current_hands"))
        or finite_int(cadence.get("current_hands"))
        or 0
    )
    checkpoint_hands = (
        finite_int(cadence_watch.get("checkpoint_hands"))
        or finite_int(cadence.get("checkpoint_hands"))
        or finite_int(pick(dashboard, "checkpoint", "total_hands"))
        or 0
    )
    live_iteration = finite_int(training_latest.get("iteration"))
    checkpoint_iteration = (
        finite_int(cadence_watch.get("checkpoint_iteration"))
        or finite_int(cadence.get("checkpoint_iteration"))
        or finite_int(pick(dashboard, "checkpoint", "iteration"))
    )
    effective_latest = finite_float(pick(throughput, "latest_window", "effective_hps_mean"))
    effective_long = finite_float(pick(throughput, "long_window", "effective_hps_mean"))
    recent_hps = finite_float(cadence.get("recent_hands_per_second")) or finite_float(pick(dashboard, "training", "recent_hands_per_second"))
    measured_hps = effective_latest or effective_long or recent_hps

    next_external_target_hands = (
        finite_int(cadence_watch.get("next_target_hands"))
        or finite_int(pick(cadence, "next_external_eval", "target_hands"))
        or 150_000_000
    )
    next_external_key = (
        cadence_watch.get("next_eval_key")
        or cadence_watch.get("next_external_eval_key")
        or "next Slumbot screen"
    )
    target_hps_values = parse_float_list(args.target_hps)
    milestones = [
        milestone_row(current_hands, checkpoint_hands, next_external_target_hands, str(next_external_key), measured_hps, target_hps_values),
        milestone_row(current_hands, checkpoint_hands, 250_000_000, "promotion/formal eligibility", measured_hps, target_hps_values),
        milestone_row(current_hands, checkpoint_hands, 1_000_000_000, "meaningful baseline scale", measured_hps, target_hps_values),
        milestone_row(current_hands, checkpoint_hands, 2_700_000_000, "paper-scale hand count", measured_hps, target_hps_values),
    ]

    throughput_checks = pick(throughput, "classification", "checks", default=[])
    if not isinstance(throughput_checks, list):
        throughput_checks = []
    training = {
        "health": health.get("overall"),
        "health_warning_diagnosis": health_diag.get("overall"),
        "live_iteration": live_iteration,
        "checkpoint_iteration": checkpoint_iteration,
        "current_hands": current_hands,
        "checkpoint_hands": checkpoint_hands,
        "recent_hps": recent_hps,
    }
    report = {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "training": training,
        "throughput": {
            "overall": pick(throughput, "classification", "overall") or throughput.get("overall"),
            "effective_hps_latest": effective_latest,
            "effective_hps_long": effective_long,
            "reported_collect_hps_mean": pick(throughput, "latest_window", "reported_collect_hps_mean"),
            "fast_fraction": pick(throughput, "batch_buckets", "fast_fraction"),
            "fast_effective_hps_mean": pick(throughput, "batch_buckets", "fast_rows", "effective_hps_mean"),
            "slow_effective_hps_mean": pick(throughput, "batch_buckets", "slow_rows", "effective_hps_mean"),
            "gpu_utilization": pick(throughput, "gpu", "gpu_utilization_percent"),
            "ppo_share_mean": pick(throughput, "latest_window", "ppo_share_mean"),
            "effective_hps_check": status_from_checks(throughput_checks, "effective_hps"),
            "inference_batching_check": status_from_checks(throughput_checks, "inference_batching"),
        },
        "evidence": {
            "next_gate_target": gates.get("next_gate_target"),
            "next_gate_overall": gates.get("next_gate_overall"),
            "next_gate_source_path": gates.get("source_path"),
            "next_gate_live_iteration": gates.get("next_gate_live_iteration"),
            "next_gate_checkpoint_iteration": gates.get("next_gate_checkpoint_iteration"),
            "next_gate_remaining_live_iterations": gates.get("next_gate_remaining_live_iterations"),
            "next_gate_remaining_checkpoint_iterations": gates.get("next_gate_remaining_checkpoint_iterations"),
            "latest_gate_pass": gates.get("latest_pass_target"),
            "next_external_eval_target_hands": cadence_watch.get("next_target_hands")
            or pick(cadence, "next_external_eval", "target_hands"),
            "next_external_eval_state": cadence_watch.get("next_state")
            or pick(cadence, "next_external_eval", "state"),
            "next_external_eval_eta": cadence_watch.get("next_eta")
            or pick(cadence, "next_external_eval", "eta_duration_live"),
            "next_action_overall": next_action.get("overall"),
            "next_action_recommendation": next_action.get("recommendation"),
        },
        "sweep": {
            "active_source_trainer": sweep_plan.get("active_source_trainer"),
            "planned_variants": [
                {
                    "variant": item.get("variant"),
                    "workers": item.get("workers"),
                    "hands_per_iter": item.get("hands_per_iter"),
                    "run_dir": item.get("run_dir"),
                }
                for item in (sweep_plan.get("variants") or [])
                if isinstance(item, dict)
            ],
            "plan_overall": sweep_plan.get("overall"),
        },
        "milestones": milestones,
        "claim_note": "Speed evidence shortens training time only. It cannot prove V4/L5/L6 strength without formal Slumbot CI.",
    }
    decision, recommendation = classify(report, args)
    report["decision"] = decision
    report["recommendation"] = recommendation
    first_milestone = milestones[0] if milestones else {}
    first_milestone_alias = dict(first_milestone)
    if first_milestone_alias and "key" not in first_milestone_alias:
        first_milestone_alias["key"] = first_milestone_alias.get("label")
    milestone_by_target = {
        int(item.get("target_hands")): item
        for item in milestones
        if isinstance(item, dict) and finite_int(item.get("target_hands")) is not None
    }
    milestone_250m = milestone_by_target.get(250_000_000, {})
    milestone_1b = milestone_by_target.get(1_000_000_000, {})
    milestone_27b = milestone_by_target.get(2_700_000_000, {})
    report.update(
        {
            "health": training.get("health"),
            "live_iteration": training.get("live_iteration"),
            "checkpoint_iteration": training.get("checkpoint_iteration"),
            "current_hands": training.get("current_hands"),
            "checkpoint_hands": training.get("checkpoint_hands"),
            "throughput_overall": report["throughput"].get("overall"),
            "effective_hps_latest": report["throughput"].get("effective_hps_latest"),
            "effective_hps_long": report["throughput"].get("effective_hps_long"),
            "speed_effective_hps": report["throughput"].get("effective_hps_latest"),
            "speed_effective_hps_latest": report["throughput"].get("effective_hps_latest"),
            "speed_effective_hps_long": report["throughput"].get("effective_hps_long"),
            "next_gate_target": report["evidence"].get("next_gate_target"),
            "next_gate_overall": report["evidence"].get("next_gate_overall"),
            "next_gate_remaining_live_iterations": report["evidence"].get("next_gate_remaining_live_iterations"),
            "next_gate_remaining_checkpoint_iterations": report["evidence"].get("next_gate_remaining_checkpoint_iterations"),
            "first_slumbot_milestone": first_milestone_alias,
            "next_external_eval_key": first_milestone.get("label"),
            "next_external_eval_target_hands": first_milestone.get("target_hands"),
            "next_external_eval_remaining_checkpoint_hands": first_milestone.get("remaining_checkpoint_hands"),
            "next_external_eval_remaining_live_hands": first_milestone.get("remaining_live_hands"),
            "next_external_eval_eta_seconds": first_milestone.get("measured_eta_seconds"),
            "next_external_eval_eta": first_milestone.get("measured_eta_duration"),
            "next_eval_key": first_milestone.get("label"),
            "next_eval_state": report["evidence"].get("next_external_eval_state"),
            "next_target_hands": first_milestone.get("target_hands"),
            "remaining_checkpoint_hands": first_milestone.get("remaining_checkpoint_hands"),
            "remaining_live_hands": first_milestone.get("remaining_live_hands"),
            "next_eta": first_milestone.get("measured_eta_duration"),
            "first_milestone": first_milestone_alias,
            "remaining_to_first_slumbot_checkpoint_hands": first_milestone.get("remaining_checkpoint_hands"),
            "remaining_to_first_slumbot_live_hands": first_milestone.get("remaining_live_hands"),
            "eta_to_first_slumbot_seconds": first_milestone.get("measured_eta_seconds"),
            "eta_to_first_slumbot": first_milestone.get("measured_eta_duration"),
            "remaining_to_250m_checkpoint_hands": milestone_250m.get("remaining_checkpoint_hands"),
            "remaining_to_250m_live_hands": milestone_250m.get("remaining_live_hands"),
            "eta_to_250m_seconds": milestone_250m.get("measured_eta_seconds"),
            "eta_to_250m": milestone_250m.get("measured_eta_duration"),
            "remaining_to_1b_checkpoint_hands": milestone_1b.get("remaining_checkpoint_hands"),
            "remaining_to_1b_live_hands": milestone_1b.get("remaining_live_hands"),
            "eta_to_1b_seconds": milestone_1b.get("measured_eta_seconds"),
            "eta_to_1b": milestone_1b.get("measured_eta_duration"),
            "remaining_to_paper_scale_checkpoint_hands": milestone_27b.get("remaining_checkpoint_hands"),
            "remaining_to_paper_scale_live_hands": milestone_27b.get("remaining_live_hands"),
            "eta_to_paper_scale_seconds": milestone_27b.get("measured_eta_seconds"),
            "eta_to_paper_scale": milestone_27b.get("measured_eta_duration"),
        }
    )
    return report


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    throughput = summary["throughput"]
    training = summary["training"]
    evidence = summary["evidence"]
    sweep = summary["sweep"]
    lines = [
        "# V5 L6 Speed Decision",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Decision: **{summary['decision']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Health / rolling diagnosis: `{training['health']}` / `{training['health_warning_diagnosis']}`",
        f"- Live/checkpoint iteration: `{training['live_iteration']}` / `{training['checkpoint_iteration']}`",
        f"- Live/checkpoint hands: `{training['current_hands']}` / `{training['checkpoint_hands']}`",
        "",
        "Throughput:",
        "",
        f"- Overall: `{throughput['overall']}`; effective h/s latest/long `{fmt(throughput['effective_hps_latest'])}` / `{fmt(throughput['effective_hps_long'])}`",
        f"- Fast/slow effective h/s: `{fmt(throughput['fast_effective_hps_mean'])}` / `{fmt(throughput['slow_effective_hps_mean'])}`",
        f"- Fast fraction / GPU utilization / PPO share: `{fmt(throughput['fast_fraction'])}` / `{fmt(throughput['gpu_utilization'])}` / `{fmt(throughput['ppo_share_mean'])}`",
        f"- Checks: effective_hps `{throughput['effective_hps_check']}`, inference_batching `{throughput['inference_batching_check']}`",
        "",
        "Evidence window:",
        "",
        f"- Next gate: `{evidence['next_gate_target']}` / `{evidence['next_gate_overall']}`",
        f"- Next Slumbot screen: `{evidence['next_external_eval_target_hands']}` / `{evidence['next_external_eval_state']}`, ETA `{evidence['next_external_eval_eta']}`",
        f"- Next action: `{evidence['next_action_overall']}` - {evidence['next_action_recommendation']}",
        "",
        "Milestone ETA:",
        "",
        "| milestone | target hands | measured ETA | ETA @ target h/s |",
        "|---|---:|---:|---|",
    ]
    for item in summary.get("milestones") or []:
        alternatives = []
        for alt in item.get("target_hps_alternatives") or []:
            alternatives.append(
                f"{fmt(alt.get('hps'))}: {alt.get('eta_duration')} (save {alt.get('time_saved_duration')})"
            )
        lines.append(
            f"| {item.get('label')} | {int(item.get('target_hands') or 0):,} | {item.get('measured_eta_duration')} | {'; '.join(alternatives)} |"
        )
    lines.extend(
        [
            "",
            "Sweep readiness:",
            "",
            f"- Plan overall: `{sweep['plan_overall']}`",
            f"- Active source trainer: `{sweep['active_source_trainer']}`",
            f"- Planned variants: `{len(sweep['planned_variants'])}`",
            "",
            "Claim note:",
            "",
            f"- {summary['claim_note']}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a read-only V5 L6 speed decision report.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--target-hps", default="800,900")
    parser.add_argument("--target-effective-hps", type=float, default=800.0)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_speed_decision(Path(args.run_dir), args)
    print(f"decision={summary['decision']}")
    print(f"recommendation={summary['recommendation']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
