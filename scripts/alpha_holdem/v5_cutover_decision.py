#!/usr/bin/env python3
"""Read-only V5 cutover decision report.

This aggregates gate, internal-probe, preflop, and Slumbot evidence into a
single conservative decision. It never starts or stops training.
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


def fmt(value: Any) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def decide(run_dir: Path) -> dict[str, Any]:
    l6 = load_json(run_dir / "v5_l6_status_brief.json")
    intervention_path, intervention = load_intervention_plan(run_dir)
    scorecard = load_json(run_dir / "v5_scorecard.json")
    baseline = load_json(run_dir / "v5_baseline_gap.json")
    trend = load_json(run_dir / "v5_trend_ledger.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")

    health = l6.get("health")
    quality = l6.get("quality_status")
    strength = l6.get("strength_answer")
    intervention_overall = intervention.get("overall")
    target_iteration = intervention.get("target_iteration")
    live_iteration = pick(l6, "live", "iteration") or intervention.get("live_iteration")
    checkpoint_iteration = (
        pick(l6, "checkpoint", "latest_pass_checkpoint_iteration")
        or pick(l6, "checkpoint", "checkpoint_iteration")
        or intervention.get("checkpoint_iteration")
    )
    latest_pass_target = pick(l6, "checkpoint", "latest_pass_target")
    if (
        isinstance(latest_pass_target, int)
        and isinstance(target_iteration, int)
        and latest_pass_target >= target_iteration
    ):
        gate_overall = "PASS"
    else:
        gate_overall = intervention.get("gate_overall") or pick(l6, "checkpoint", "gate_overall")
    preflop_probe = pick(l6, "preflop_probe", "overall") or intervention.get("preflop_probe_overall")
    internal_verdict = pick(l6, "next_evidence", "internal_probe_verdict") or intervention.get(
        "internal_probe_verdict"
    )
    latest_best = pick(l6, "next_evidence", "internal_probe_latest_is_best_opponents")
    if latest_best is None:
        latest_best = intervention.get("internal_probe_latest_is_best_opponents")
    opponent_count = pick(l6, "next_evidence", "internal_probe_opponent_count")
    if opponent_count is None:
        opponent_count = intervention.get("internal_probe_opponent_count")
    trend_overall = intervention.get("action_prior_trend_overall")
    trend_lag = intervention.get("action_prior_trend_lag_iterations")
    dry_run = str(intervention.get("dry_run_command") or "")
    health_diag_overall = health_diag.get("overall")
    health_diag_metrics = health_diag.get("metrics") if isinstance(health_diag.get("metrics"), dict) else {}

    formal_l5 = bool(pick(baseline, "claim_rules", "can_claim_l5"))
    formal_l6 = bool(pick(baseline, "claim_rules", "can_claim_l6"))
    slumbot_hands = pick(baseline, "latest_slumbot", "hands")
    slumbot_bb100 = pick(baseline, "latest_slumbot", "bb_per_100")
    slumbot_lower = pick(baseline, "latest_slumbot", "lower_bound_bb_per_100")

    checks: list[dict[str, Any]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if health == "PASS":
        health_status = "PASS"
    elif health == "WARN":
        health_status = "WARN"
    else:
        health_status = "BLOCK"
    add("health", health_status, f"health={health}")
    add("quality", "WARN" if quality and quality != "PASS" else "PASS", f"quality={quality}")
    if health_diag_overall == "FAIL_COLLAPSE_RISK":
        add("health_warning_diagnosis", "HOLD", "rolling diagnosis indicates collapse risk")
    elif health_diag_overall == "PREFLOP_ALLIN_SUSTAINED_WARN":
        add(
            "health_warning_diagnosis",
            "WARN",
            "rolling preflop all-in warning: "
            f"mean={fmt(health_diag_metrics.get('preflop_allin_mean'))}, "
            f"latest={fmt(health_diag_metrics.get('preflop_allin_latest'))}, "
            f"warn_frac={fmt(health_diag_metrics.get('preflop_allin_warn_fraction'))}",
        )
    elif health_diag_overall:
        add("health_warning_diagnosis", "PASS", f"diagnosis={health_diag_overall}")
    else:
        add("health_warning_diagnosis", "WARN", "rolling health diagnosis unavailable")
    add("strength_claim", "PASS" if formal_l5 or formal_l6 else "BLOCK", f"strength={strength}")

    if intervention_overall == "PENDING_CHECKPOINT":
        add(
            "intervention_readiness",
            "WAIT",
            f"target {target_iteration} not ready; live={live_iteration}, checkpoint={checkpoint_iteration}",
        )
    elif intervention_overall in {"STRICT_GATE_PASS_READY", "PREFLOP_INTERVENTION_CANDIDATE"}:
        add("intervention_readiness", "REVIEW", f"intervention={intervention_overall}")
    elif intervention_overall in {
        "STRICT_GATE_PASS_REVIEW_REQUIRED",
        "CONTEXT_PREFLOP_INTERVENTION_REVIEW_REQUIRED",
    }:
        add("intervention_readiness", "HOLD", "review required before any cutover")
    else:
        add("intervention_readiness", "BLOCK", f"intervention={intervention_overall}")

    add("gate", "PASS" if gate_overall == "PASS" else "WAIT", f"gate={gate_overall}")
    add("preflop_probe", "WARN" if preflop_probe in {"WARN", "FAIL"} else "PASS", f"preflop={preflop_probe}")
    add(
        "internal_probe",
        "HOLD" if internal_verdict == "REGRESSION_RISK_INTERNAL" else "PASS",
        f"verdict={internal_verdict}; latest_best={latest_best}/{opponent_count}",
    )
    add(
        "action_prior_trend",
        "PASS" if trend_overall == "PASS" and (trend_lag is None or int(trend_lag) <= 20) else "WARN",
        f"trend={trend_overall}; lag={trend_lag}",
    )
    add(
        "slumbot_formal",
        "PASS" if formal_l5 or formal_l6 else "BLOCK",
        f"hands={slumbot_hands}; bb100={fmt(slumbot_bb100)}; lower={fmt(slumbot_lower)}",
    )

    statuses = {str(item["status"]) for item in checks}
    if "WAIT" in statuses:
        decision = "WAIT_FOR_TARGET"
        recommendation = "Keep current trainer running; wait for the planned gate/probe target."
    elif "HOLD" in statuses or "BLOCK" in statuses:
        decision = "HOLD_NO_CUTOVER"
        recommendation = "Do not cut over; collect stronger internal or Slumbot evidence first."
    elif "WARN" in statuses:
        decision = "REVIEW_CUTOVER"
        recommendation = "Manual review required; dry-run exists but evidence is not clean."
    else:
        decision = "REVIEW_CUTOVER"
        recommendation = "All local checks are clean, but cutover still requires explicit approval."

    claim_note = (
        "This decision is about engineering cutover only. It cannot prove V4/L5/L6 strength; "
        "only Slumbot 100k+ with bb/100 > 0 and CI lower > 0 can prove L5."
    )

    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "run_dir": str(run_dir),
        "decision": decision,
        "recommendation": recommendation,
        "target_iteration": target_iteration,
        "live_iteration": live_iteration,
        "checkpoint_iteration": checkpoint_iteration,
        "health": health,
        "quality_status": quality,
        "health_warning_diagnosis": health_diag_overall,
        "health_warning_metrics": health_diag_metrics,
        "strength_answer": strength,
        "intervention_overall": intervention_overall,
        "intervention_source": str(intervention_path),
        "intervention": {
            "overall": intervention_overall,
            "target_iteration": target_iteration,
            "checkpoint_iteration": intervention.get("checkpoint_iteration"),
            "live_iteration": intervention.get("live_iteration"),
            "source_path": str(intervention_path),
            "recommendation": intervention.get("recommendation"),
            "context_preflop_intervention_needed": intervention.get("context_preflop_intervention_needed"),
            "sb_open_weak": intervention.get("sb_open_weak"),
            "selector_preflop_leak_confirmed": intervention.get("selector_preflop_leak_confirmed"),
            "planned_action_priors": intervention.get("planned_action_priors"),
            "dry_run_command_emitted": bool(dry_run),
        },
        "dry_run_command_emitted": bool(dry_run),
        "checks": checks,
        "slumbot": {
            "hands": slumbot_hands,
            "bb_per_100": slumbot_bb100,
            "ci_lower": slumbot_lower,
            "formal_l5": formal_l5,
            "formal_l6": formal_l6,
        },
        "next_evidence": {
            "next_internal_probe_target": pick(l6, "next_evidence", "next_internal_probe_target"),
            "next_external_eval_target_hands": pick(cadence, "next_external_eval", "target_hands"),
            "next_external_eval_state": pick(cadence, "next_external_eval", "state"),
            "next_external_eval_eta": pick(cadence, "next_external_eval", "eta_duration_live"),
            "trend_direction": pick(trend, "direction", "answer"),
            "latest_better": pick(scorecard, "is_latest_training_better", "answer"),
        },
        "claim_note": claim_note,
        "source_artifacts": {
            "l6_status": str(run_dir / "v5_l6_status_brief.json"),
            "intervention": str(intervention_path),
            "scorecard": str(run_dir / "v5_scorecard.json"),
            "baseline": str(run_dir / "v5_baseline_gap.json"),
            "cadence": str(run_dir / "v5_eval_cadence.json"),
        },
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# V5 Cutover Decision",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Decision: **{summary['decision']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Target / live / checkpoint iteration: `{summary['target_iteration']}` / `{summary['live_iteration']}` / `{summary['checkpoint_iteration']}`",
        f"- Health / quality: `{summary['health']}` / `{summary['quality_status']}`",
        f"- Rolling health diagnosis: `{summary['health_warning_diagnosis']}`",
        f"- Strength answer: `{summary['strength_answer']}`",
        f"- Intervention: `{summary['intervention_overall']}`",
        f"- Dry-run command emitted: `{summary['dry_run_command_emitted']}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.extend(
        [
            "",
            "Slumbot:",
            "",
            f"- Hands: `{summary['slumbot']['hands']}`",
            f"- bb/100: `{fmt(summary['slumbot']['bb_per_100'])}`",
            f"- CI lower: `{fmt(summary['slumbot']['ci_lower'])}`",
            f"- Formal L5 / L6: `{summary['slumbot']['formal_l5']}` / `{summary['slumbot']['formal_l6']}`",
            "",
            "Next Evidence:",
            "",
            f"- Next internal probe: `{summary['next_evidence']['next_internal_probe_target']}`",
            f"- Next external eval: `{summary['next_evidence']['next_external_eval_target_hands']}` hands, `{summary['next_evidence']['next_external_eval_state']}`, ETA `{summary['next_evidence']['next_external_eval_eta']}`",
            f"- Trend direction: `{summary['next_evidence']['trend_direction']}`",
            f"- Latest better: `{summary['next_evidence']['latest_better']}`",
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = decide(Path(args.run_dir))
    print(f"decision={summary['decision']}")
    print(f"target={summary['target_iteration']} live={summary['live_iteration']} ckpt={summary['checkpoint_iteration']}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(Path(args.out_md), summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
