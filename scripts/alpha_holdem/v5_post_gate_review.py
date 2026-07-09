#!/usr/bin/env python
"""Build a read-only post-gate evidence review for V5 training.

This script intentionally does not stop, start, or mutate trainers. It collects
the gate, local probes, internal probe status, trend ledger, and L6 claim state
around a target checkpoint so the next intervention decision is evidence-based.
"""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - diagnostics should survive malformed artifacts.
        return {"_load_error": str(exc), "_path": str(path)}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pick(obj: dict[str, Any], *keys: str, default: Any = None) -> Any:
    cur: Any = obj
    for key in keys:
        if not isinstance(cur, dict) or key not in cur:
            return default
        cur = cur[key]
    return cur


def fmt(value: Any) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return "None" if value is None else str(value)


def join_names(names: list[str]) -> str:
    if not names:
        return "nothing"
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + f" and {names[-1]}"


def evidence_target_note(internal: dict[str, Any]) -> str:
    if internal.get("state") == "NOT_SCHEDULED":
        return " No scheduled internal probe for this target."
    return ""


def target_from_gate_name(path: Path) -> int | None:
    name = path.name
    prefix = "gate_"
    suffix = "_status.json"
    if not name.startswith(prefix) or not name.endswith(suffix):
        return None
    try:
        return int(name[len(prefix) : -len(suffix)])
    except ValueError:
        return None


def infer_target_iteration(run_dir: Path, requested: int | None) -> int | None:
    if requested:
        return requested
    l6 = load_json(run_dir / "v5_l6_status_brief.json")
    next_pending = pick(l6, "checkpoint", "next_pending_target")
    if isinstance(next_pending, int):
        return next_pending
    gates: list[int] = []
    for path in run_dir.glob("gate_*_status.json"):
        target = target_from_gate_name(path)
        if target is not None:
            gates.append(target)
    return max(gates) if gates else None


def summarize_gate(run_dir: Path, target_iteration: int | None) -> dict[str, Any]:
    if target_iteration is None:
        return {"overall": "UNKNOWN", "target_iteration": None, "path": None}
    gate_path = run_dir / f"gate_{target_iteration}_status.json"
    gate = load_json(gate_path)
    checkpoint = gate.get("checkpoint") if isinstance(gate.get("checkpoint"), dict) else {}
    live = gate.get("latest") or gate.get("live_log") or {}
    checks = gate.get("checks") if isinstance(gate.get("checks"), list) else []
    nonpass = [
        {
            "name": check.get("name"),
            "status": check.get("status"),
            "detail": check.get("detail"),
        }
        for check in checks
        if check.get("status") != "PASS"
    ]
    return {
        "overall": gate.get("overall", "MISSING" if gate.get("_missing") else "UNKNOWN"),
        "target_iteration": target_iteration,
        "path": str(gate_path),
        "checked_at": gate.get("checked_at"),
        "checkpoint_iteration": gate.get("checkpoint_iteration") or checkpoint.get("iteration"),
        "checkpoint_hands": gate.get("checkpoint_hands") or checkpoint.get("total_hands"),
        "live_iteration": gate.get("live_iteration") or live.get("iteration"),
        "live_hands": gate.get("live_hands") or live.get("hands"),
        "live_reached_target": gate.get("live_reached_target"),
        "checkpoint_reached_target": gate.get("checkpoint_reached_target"),
        "remaining_live_iterations": gate.get("remaining_live_iterations"),
        "remaining_checkpoint_iterations": gate.get("remaining_checkpoint_iterations"),
        "nonpass_checks": nonpass,
    }


def summarize_internal_probe(run_dir: Path, target_iteration: int | None) -> dict[str, Any]:
    candidates: list[tuple[int, str, float, Path, dict[str, Any]]] = []
    scheduled_target = False
    for status_path in sorted(run_dir.glob("internal_strength_watch*_status.json")):
        status = load_json(status_path)
        targets = status.get("targets") if isinstance(status.get("targets"), list) else []
        completed = status.get("completed") if isinstance(status.get("completed"), list) else []
        covers_target = int(target_iteration in targets or target_iteration in completed) if target_iteration is not None else 0
        scheduled_target = scheduled_target or bool(covers_target)
        try:
            mtime = status_path.stat().st_mtime
        except OSError:
            mtime = 0.0
        candidates.append((covers_target, str(status.get("checked_at") or ""), mtime, status_path, status))
    if candidates:
        _, _, _, selected_path, selected = sorted(candidates, key=lambda item: (item[0], item[1], item[2]))[-1]
    else:
        selected_path, selected = None, {"_missing": True}
    completed = selected.get("completed") if isinstance(selected.get("completed"), list) else []
    target_completed = target_iteration in completed if target_iteration is not None else False
    latest_readiness = selected.get("latest_readiness") if isinstance(selected.get("latest_readiness"), dict) else {}

    l6 = load_json(run_dir / "v5_l6_status_brief.json")
    latest_iter = pick(l6, "score_progression", "latest_internal_probe_iteration")
    target_is_latest_l6 = target_iteration is not None and latest_iter == target_iteration
    target_probe = summarize_target_internal_probe(run_dir, target_iteration)
    if target_iteration is not None and not scheduled_target:
        state = "NOT_SCHEDULED"
    elif target_completed or target_is_latest_l6:
        state = "COMPLETED"
    else:
        state = latest_readiness.get("overall", "PENDING")
    return {
        "state": state,
        "scheduled": scheduled_target,
        "target_iteration": target_iteration,
        "watch_status": str(selected_path) if selected_path else None,
        "watch_checked_at": selected.get("checked_at"),
        "completed_targets": completed,
        "latest_readiness_target": latest_readiness.get("target_iteration"),
        "latest_readiness_overall": latest_readiness.get("overall"),
        "latest_l6_iteration": latest_iter,
        "latest_l6_hands": pick(l6, "score_progression", "latest_internal_probe_hands"),
        "latest_l6_verdict": pick(l6, "score_progression", "latest_internal_verdict"),
        "latest_l6_delta_mean_bb100": pick(l6, "score_progression", "latest_internal_delta_mean_bb100"),
        "latest_l6_delta_lower_bb100": pick(l6, "score_progression", "latest_internal_delta_lower_bb100"),
        "target_probe": target_probe,
    }


def summarize_target_internal_probe(run_dir: Path, target_iteration: int | None) -> dict[str, Any] | None:
    if target_iteration is None:
        return None
    paths = sorted(run_dir.glob(f"internal_strength_probe_iter{target_iteration}_*h.json"))
    if not paths:
        return None
    path = paths[-1]
    probe = load_json(path)
    results = probe.get("results") if isinstance(probe.get("results"), list) else []
    trends = probe.get("trends") if isinstance(probe.get("trends"), dict) else {}
    rows = []
    for result in results:
        if result.get("candidate_kind") != "checkpoint_latest":
            continue
        if result.get("candidate_iteration") != target_iteration:
            continue
        opponent = result.get("opponent")
        trend = trends.get(opponent) if isinstance(trends.get(opponent), dict) else {}
        rows.append(
            {
                "opponent": opponent,
                "bb100": result.get("bb100"),
                "ci95_bb100": result.get("ci95_bb100"),
                "hands": result.get("hands"),
                "wins": result.get("wins"),
                "losses": result.get("losses"),
                "draws": result.get("draws"),
                "latest_is_best": trend.get("latest_is_best"),
                "strictly_increasing": trend.get("strictly_increasing"),
            }
        )
    return {
        "path": str(path),
        "checked_at": probe.get("checked_at"),
        "checkpoint_iteration": pick(probe, "checkpoint", "iteration"),
        "checkpoint_hands": pick(probe, "checkpoint", "total_hands"),
        "hands_per_match": probe.get("hands_per_match"),
        "rows": rows,
    }


def build_review(run_dir: Path, target_iteration: int | None = None) -> dict[str, Any]:
    target = infer_target_iteration(run_dir, target_iteration)
    gate = summarize_gate(run_dir, target)
    health = load_json(run_dir / "health_status.json")
    preflop = load_json(run_dir / "v5_preflop_probe_latest.json")
    checkpoint_delta = load_json(run_dir / "v5_checkpoint_delta.json")
    action_trend = load_json(run_dir / "v5_action_prior_trend.json")
    trend = load_json(run_dir / "v5_trend_ledger.json")
    l6 = load_json(run_dir / "v5_l6_status_brief.json")
    next_action = load_json(run_dir / "v5_next_action_queue.json")
    internal = summarize_internal_probe(run_dir, target)

    blockers: list[dict[str, str]] = []
    watches: list[dict[str, str]] = []
    gate_checkpoint_ready = (
        target is not None
        and isinstance(gate.get("checkpoint_iteration"), int)
        and int(gate.get("checkpoint_iteration") or 0) >= int(target)
    )
    gate_live_ready = (
        target is not None
        and isinstance(gate.get("live_iteration"), int)
        and int(gate.get("live_iteration") or 0) >= int(target)
    )
    gate_due = gate["overall"] != "PASS" and (gate_checkpoint_ready or gate_live_ready)
    internal_incomplete = internal["state"] not in {"COMPLETED", "NOT_SCHEDULED"}
    internal_due = internal_incomplete and gate_checkpoint_ready
    if gate["overall"] != "PASS":
        blockers.append(
            {
                "name": "gate",
                "detail": f"gate_{target} is {gate['overall']}; wait for checkpoint/live iteration readiness",
            }
        )
    if internal_incomplete:
        blockers.append(
            {
                "name": "internal_probe",
                "detail": f"internal probe {target} is {internal['state']}; wait for fixed-opponent comparison",
            }
        )
    if not pick(l6, "claims", "can_claim_l5", default=False):
        blockers.append(
            {
                "name": "formal_slumbot_claim",
                "detail": "L5/L6 still requires 100k+ Slumbot hands, bb/100 > 0, and CI lower > 0",
            }
        )
    if checkpoint_delta.get("overall") not in (None, "PASS", "LOCAL_GUARDRAILS_IMPROVED"):
        watches.append(
            {
                "name": "local_guardrails",
                "detail": f"checkpoint delta is {checkpoint_delta.get('overall')}: {checkpoint_delta.get('recommendation')}",
            }
        )
    if preflop.get("overall") not in (None, "PASS"):
        warnings = preflop.get("warnings") if isinstance(preflop.get("warnings"), list) else []
        watches.append(
            {
                "name": "preflop_probe",
                "detail": f"preflop probe is {preflop.get('overall')} with {len(warnings)} warnings",
            }
        )

    if gate_due or internal_due:
        overall = "DUE_EVIDENCE_REFRESH"
        due_items = []
        if gate_due:
            due_items.append(f"gate_{target}")
        if internal_due:
            due_items.append(f"internal_probe_{target}")
        recommendation = (
            f"Refresh/allow {join_names(due_items)}; no restart or strength claim."
            f"{evidence_target_note(internal)}"
        )
    elif gate["overall"] != "PASS" or internal_incomplete:
        overall = "PENDING_EVIDENCE"
        pending_items = []
        if gate["overall"] != "PASS":
            pending_items.append(f"gate_{target}")
        if internal_incomplete:
            pending_items.append(f"internal_probe_{target}")
        recommendation = (
            f"Wait for {join_names(pending_items)}; no restart or strength claim."
            f"{evidence_target_note(internal)}"
        )
    elif not pick(l6, "claims", "can_claim_l5", default=False):
        overall = "REVIEW_REQUIRED_NO_AUTO_RESTART"
        recommendation = (
            "Local gate/internal evidence is ready, but Slumbot proof is still missing; review leak shape before any "
            "controlled intervention."
        )
    else:
        overall = "FORMAL_STRENGTH_REVIEW_REQUIRED"
        recommendation = "Formal Slumbot claim evidence may be present; run the claim audit before promotion."

    return {
        "checked_at": now_iso(),
        "overall": overall,
        "recommendation": recommendation,
        "run_dir": str(run_dir),
        "target_iteration": target,
        "gate_overall": gate.get("overall"),
        "gate_live_iteration": gate.get("live_iteration"),
        "gate_live_hands": gate.get("live_hands"),
        "gate_checkpoint_iteration": gate.get("checkpoint_iteration"),
        "gate_checkpoint_hands": gate.get("checkpoint_hands"),
        "gate_live_reached_target": gate.get("live_reached_target"),
        "gate_checkpoint_reached_target": gate.get("checkpoint_reached_target"),
        "gate_remaining_live_iterations": gate.get("remaining_live_iterations"),
        "gate_remaining_checkpoint_iterations": gate.get("remaining_checkpoint_iterations"),
        "internal_probe_state": internal.get("state"),
        "internal_probe_scheduled": internal.get("scheduled"),
        "internal_probe_latest_l6_iteration": internal.get("latest_l6_iteration"),
        "strength_answer": l6.get("strength_answer"),
        "gate": gate,
        "readiness": {
            "gate_live_ready": gate_live_ready,
            "gate_checkpoint_ready": gate_checkpoint_ready,
            "gate_due": gate_due,
            "internal_due": internal_due,
        },
        "health": {
            "overall": health.get("overall"),
            "iteration": pick(health, "latest", "iteration"),
            "hands": pick(health, "latest", "hands"),
            "entropy": pick(health, "latest", "entropy"),
            "value_loss": pick(health, "latest", "value_loss"),
        },
        "preflop_probe": {
            "overall": preflop.get("overall"),
            "checked_at": preflop.get("checked_at"),
            "checkpoint_iteration": pick(preflop, "checkpoint", "iteration"),
            "checkpoint_hands": pick(preflop, "checkpoint", "total_hands"),
            "warning_count": len(preflop.get("warnings") or []),
        },
        "checkpoint_delta": {
            "overall": checkpoint_delta.get("overall"),
            "recommendation": checkpoint_delta.get("recommendation"),
            "latest_probe_iteration": pick(checkpoint_delta, "latest_probe", "checkpoint_iteration"),
            "latest_probe_warning_count": pick(checkpoint_delta, "latest_probe", "warning_count"),
            "warning_delta": pick(checkpoint_delta, "probe_delta", "warning_count"),
        },
        "action_prior_trend": {
            "overall": action_trend.get("overall"),
            "latest_iteration": pick(action_trend, "candidate", "latest_iteration"),
            "preflop_call_delta": pick(action_trend, "comparison", "preflop_call_delta"),
            "preflop_allin_delta": pick(action_trend, "comparison", "preflop_allin_delta"),
            "postflop_raise_allin_delta": pick(action_trend, "comparison", "postflop_raise_allin_delta"),
        },
        "internal_probe": internal,
        "slumbot_trend": {
            "overall": trend.get("overall"),
            "latest_official_hands": pick(trend, "latest_official", "hands"),
            "latest_official_bb100": pick(trend, "latest_official", "bb_per_100"),
            "latest_official_ci_lower": pick(trend, "latest_official", "lower_bound_bb_per_100"),
            "claim_latest_is_better": pick(trend, "decision", "claim_latest_is_better"),
            "promote_strength_claim": pick(trend, "decision", "promote_strength_claim"),
        },
        "claim_state": {
            "strength_answer": l6.get("strength_answer"),
            "can_claim_stronger_than_v4": pick(l6, "claims", "can_claim_stronger_than_v4"),
            "can_claim_l5": pick(l6, "claims", "can_claim_l5"),
            "can_claim_l6": pick(l6, "claims", "can_claim_l6"),
            "claim_rule": pick(l6, "claims", "claim_rule"),
        },
        "next_action": {
            "overall": next_action.get("overall"),
            "recommendation": next_action.get("recommendation"),
        },
        "blockers": blockers,
        "watches": watches,
        "source_artifacts": {
            "gate": gate.get("path"),
            "health": str(run_dir / "health_status.json"),
            "preflop_probe": str(run_dir / "v5_preflop_probe_latest.json"),
            "checkpoint_delta": str(run_dir / "v5_checkpoint_delta.json"),
            "action_prior_trend": str(run_dir / "v5_action_prior_trend.json"),
            "trend_ledger": str(run_dir / "v5_trend_ledger.json"),
            "l6_status_brief": str(run_dir / "v5_l6_status_brief.json"),
            "next_action_queue": str(run_dir / "v5_next_action_queue.json"),
            "internal_strength_watch": internal.get("watch_status"),
        },
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    gate = summary["gate"]
    health = summary["health"]
    preflop = summary["preflop_probe"]
    delta = summary["checkpoint_delta"]
    internal = summary["internal_probe"]
    target_probe = internal.get("target_probe") or {}
    target_rows = target_probe.get("rows") if isinstance(target_probe.get("rows"), list) else []
    trend = summary["slumbot_trend"]
    claims = summary["claim_state"]
    lines = [
        "# V5 Post-Gate Review",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Target iteration: `{summary['target_iteration']}`",
        "",
        "Gate and training:",
        "",
        f"- Gate: `{gate['overall']}`; checkpoint iter/hands `{gate.get('checkpoint_iteration')}` / `{gate.get('checkpoint_hands')}`",
        f"- Live iter/hands: `{gate.get('live_iteration')}` / `{gate.get('live_hands')}`",
        f"- Health: `{health['overall']}`; latest iter/hands `{health['iteration']}` / `{health['hands']}`; entropy `{fmt(health['entropy'])}`; value loss `{fmt(health['value_loss'])}`",
        "",
        "Local evidence:",
        "",
        f"- Preflop probe: `{preflop['overall']}` at checkpoint `{preflop['checkpoint_iteration']}` / `{preflop['checkpoint_hands']}`; warnings `{preflop['warning_count']}`",
        f"- Checkpoint delta: `{delta['overall']}`; latest probe iter `{delta['latest_probe_iteration']}`; warning delta `{fmt(delta['warning_delta'])}`",
        f"- Internal probe: `{internal['state']}`; scheduled `{internal.get('scheduled')}`; latest L6 iter `{internal['latest_l6_iteration']}`; verdict `{internal['latest_l6_verdict']}`; delta mean/lower `{fmt(internal['latest_l6_delta_mean_bb100'])}` / `{fmt(internal['latest_l6_delta_lower_bb100'])}`",
    ]
    if target_rows:
        formatted = []
        for row in target_rows:
            formatted.append(
                f"{row.get('opponent')} {fmt(row.get('bb100'))} +/-{fmt(row.get('ci95_bb100'))} bb/100"
            )
        lines.append(f"- Internal target rows: {'; '.join(formatted)}")
        lines.append(f"- Internal target artifact: `{target_probe.get('path')}`")
    lines.extend(
        [
            "",
            "Slumbot and claims:",
            "",
            f"- Trend: `{trend['overall']}`",
            f"- Latest official Slumbot hands / bb100 / CI lower: `{trend['latest_official_hands']}` / `{fmt(trend['latest_official_bb100'])}` / `{fmt(trend['latest_official_ci_lower'])}`",
            f"- Claim latest/promote strength: `{trend['claim_latest_is_better']}` / `{trend['promote_strength_claim']}`",
            f"- Strength answer: `{claims['strength_answer']}`",
            f"- Can claim V4/L5/L6: `{claims['can_claim_stronger_than_v4']}` / `{claims['can_claim_l5']}` / `{claims['can_claim_l6']}`",
            "",
            "Blockers:",
            "",
        ]
    )
    if summary["blockers"]:
        for blocker in summary["blockers"]:
            lines.append(f"- `{blocker['name']}` - {blocker['detail']}")
    else:
        lines.append("- none")
    lines.extend(["", "Watches:", ""])
    if summary["watches"]:
        for watch in summary["watches"]:
            lines.append(f"- `{watch['name']}` - {watch['detail']}")
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "Claim rule:",
            "",
            f"- {claims['claim_rule']}",
            "",
            "Source artifacts:",
            "",
        ]
    )
    for name, source in summary["source_artifacts"].items():
        lines.append(f"- `{name}`: `{source}`")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only post-gate V5 evidence review.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--target-iteration", type=int)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    summary = build_review(run_dir, args.target_iteration)
    target = summary["target_iteration"] or "unknown"
    out_json = Path(args.out_json) if args.out_json else run_dir / f"v5_post_gate_review_{target}.json"
    out_md = Path(args.out_md) if args.out_md else run_dir / f"v5_post_gate_review_{target}.md"
    write_json(out_json, summary)
    write_markdown(summary, out_md)
    print(f"overall={summary['overall']}")
    print(f"target_iteration={summary['target_iteration']}")
    print(f"recommendation={summary['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
