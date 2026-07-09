#!/usr/bin/env python3
"""Read-only checkpoint promotion decision for V5 L6 training.

This report answers whether the current target checkpoint can be promoted,
held for review, or simply waited on. It is stricter than a health dashboard:
local gates can allow continued training, but Slumbot/L5/L6 promotion claims
remain blocked until formal CI evidence exists.
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def gate_target_from(path: Path, gate: dict[str, Any]) -> int | None:
    target = gate.get("target_iteration")
    if isinstance(target, int):
        return target
    match = re.search(r"gate_(\d+)_status", path.stem)
    return int(match.group(1)) if match else None


def gate_records(run_dir: Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(run_dir.glob("gate_*_status.json")):
        gate = load_json(path)
        target = gate_target_from(path, gate)
        if target is None:
            continue
        records.append({"target": target, "path": path, "gate": gate})
    return sorted(records, key=lambda item: int(item["target"]))


def choose_target(run_dir: Path, requested: int | None) -> tuple[int | None, dict[str, Any] | None]:
    gates = gate_records(run_dir)
    if requested is not None:
        for item in gates:
            if item["target"] == requested:
                return requested, item
        return requested, None
    pending = [item for item in gates if item["gate"].get("overall") == "PENDING"]
    if pending:
        return int(pending[0]["target"]), pending[0]
    passed = [item for item in gates if item["gate"].get("overall") == "PASS"]
    if passed:
        return int(passed[-1]["target"]), passed[-1]
    return None, None


def build_decision(run_dir: Path, output_dir: Path, target_iteration: int | None = None) -> dict[str, Any]:
    target, gate_record = choose_target(run_dir, target_iteration)
    gate = gate_record["gate"] if gate_record else load_json(run_dir / f"gate_{target}_status.json") if target else {}
    health = load_json(run_dir / "health_status.json")
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    intervention_path, intervention = load_intervention_plan(run_dir)
    scorecard = load_json(run_dir / "v5_scorecard.json")
    claim_audit = load_json(run_dir / "v5_l6_claim_audit.json")
    speed = load_json(run_dir / "v5_l6_speed_decision.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    baseline = load_json(run_dir / "v5_baseline_gap.json")

    live_iteration = pick(gate, "latest", "iteration")
    live_hands = pick(gate, "latest", "hands")
    checkpoint_iteration = pick(gate, "checkpoint", "iteration")
    checkpoint_hands = pick(gate, "checkpoint", "total_hands")
    latest_internal = pick(scorecard, "internal_probes", "latest", default={}) or {}
    latest_slumbot = baseline.get("latest_slumbot") if isinstance(baseline.get("latest_slumbot"), dict) else {}

    checks: list[dict[str, str]] = []
    if target is None:
        add_check(checks, "target", "FAIL", "no gate target found")
    else:
        add_check(checks, "target", "PASS", f"target={target}")

    gate_overall = gate.get("overall")
    if gate_overall == "PASS":
        add_check(checks, "gate", "PASS", f"gate {target} PASS")
    elif gate_overall == "PENDING":
        add_check(checks, "gate", "WAIT", f"gate {target} pending; live={live_iteration}, checkpoint={checkpoint_iteration}")
    elif gate_overall:
        add_check(checks, "gate", "BLOCK", f"gate {target} is {gate_overall}")
    else:
        add_check(checks, "gate", "FAIL", f"gate {target} artifact missing")

    if checkpoint_iteration is not None and target is not None and int(checkpoint_iteration) >= int(target):
        add_check(checks, "checkpoint_reached", "PASS", f"checkpoint {checkpoint_iteration} >= target {target}")
    else:
        add_check(checks, "checkpoint_reached", "WAIT", f"checkpoint {checkpoint_iteration} < target {target}")

    health_overall = health.get("overall")
    health_diag_overall = health_diag.get("overall")
    if health_diag_overall == "FAIL_COLLAPSE_RISK":
        add_check(checks, "health", "BLOCK", "rolling health diagnosis indicates collapse risk")
    elif health_overall == "PASS" and health_diag_overall == "PASS":
        add_check(checks, "health", "PASS", "health and rolling diagnosis PASS")
    elif health_overall in {"PASS", "WARN"} and health_diag_overall in {"PASS", "WATCH", "HEALTH_WARN_TRANSIENT_OR_LOCAL", "PREFLOP_ALLIN_SUSTAINED_WARN"}:
        add_check(checks, "health", "WATCH", f"health={health_overall}, rolling={health_diag_overall}")
    else:
        add_check(checks, "health", "BLOCK", f"health={health_overall}, rolling={health_diag_overall}")

    preflop_overall = preflop_probe.get("overall")
    if preflop_overall == "PASS":
        add_check(checks, "preflop_probe", "PASS", "preflop probe PASS")
    elif preflop_overall:
        add_check(checks, "preflop_probe", "REVIEW", f"preflop probe={preflop_overall}")
    else:
        add_check(checks, "preflop_probe", "WAIT", "preflop probe missing or not refreshed")

    internal_target = latest_internal.get("checkpoint_iteration")
    internal_verdict = latest_internal.get("verdict")
    if target is not None and internal_target == target:
        if internal_verdict == "REGRESSION_RISK_INTERNAL":
            add_check(checks, "internal_eval", "REVIEW", f"target {target} internal verdict={internal_verdict}")
        elif internal_verdict:
            add_check(checks, "internal_eval", "PASS", f"target {target} internal verdict={internal_verdict}")
        else:
            add_check(checks, "internal_eval", "WAIT", f"target {target} internal verdict missing")
    else:
        add_check(checks, "internal_eval", "WAIT", f"latest internal target={internal_target}; waiting for {target}")

    blockers = claim_audit.get("blockers") if isinstance(claim_audit.get("blockers"), list) else []
    can_l5 = bool(pick(claim_audit, "summary", "can_claim_l5"))
    can_l6 = bool(pick(claim_audit, "summary", "can_claim_l6"))
    if can_l6:
        add_check(checks, "formal_claim", "PASS", "formal L6 claim available")
    elif can_l5:
        add_check(checks, "formal_claim", "PASS_L5_ONLY", "formal L5 claim available, L6 not proven")
    else:
        add_check(checks, "formal_claim", "BLOCK", f"claim audit blockers={len(blockers)}; Slumbot hands={latest_slumbot.get('hands')}")

    speed_decision = speed.get("decision")
    if speed_decision == "WAIT_FOR_GATE_BEFORE_SPEED_CHANGE":
        add_check(checks, "speed", "WAIT", f"speed decision={speed_decision}")
    elif speed_decision:
        add_check(checks, "speed", "WATCH", f"speed decision={speed_decision}")
    else:
        add_check(checks, "speed", "WAIT", "speed decision missing")

    statuses = {item["status"] for item in checks}
    if "FAIL" in statuses:
        overall = "ERROR_MISSING_EVIDENCE"
        recommendation = "Fix missing gate/evidence artifacts before making checkpoint decisions."
    elif "BLOCK" in statuses and any(item["name"] == "formal_claim" for item in checks if item["status"] == "BLOCK"):
        if "WAIT" in statuses:
            overall = "WAIT_FOR_CHECKPOINT_STRENGTH_BLOCKED"
            recommendation = f"Wait for checkpoint {target}; no promotion claim is allowed without formal Slumbot CI."
        elif "REVIEW" in statuses or "WATCH" in statuses:
            overall = "HOLD_REVIEW_STRENGTH_BLOCKED"
            recommendation = "Review local warnings/regression risk; formal promotion remains blocked by Slumbot CI."
        else:
            overall = "CONTINUE_TRAINING_STRENGTH_BLOCKED"
            recommendation = "Local evidence is acceptable, but continue training/evaluation because Slumbot L5/L6 is not proven."
    elif "BLOCK" in statuses:
        overall = "BLOCKED_LOCAL_GATE"
        recommendation = "Resolve local gate/health blockers before continuing or promoting."
    elif "WAIT" in statuses:
        overall = "WAIT_FOR_CHECKPOINT"
        recommendation = f"Wait for checkpoint {target} evidence to finish."
    elif "REVIEW" in statuses or "WATCH" in statuses:
        overall = "HOLD_FOR_REVIEW"
        recommendation = "Hold promotion and review local warnings before any restart or speed sweep."
    else:
        overall = "LOCAL_PROMOTION_READY"
        recommendation = "Local gates are ready; promotion still depends on formal Slumbot claim rules."

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "target_iteration": target,
        "overall": overall,
        "recommendation": recommendation,
        "checks": checks,
        "live": {"iteration": live_iteration, "hands": live_hands},
        "checkpoint": {"iteration": checkpoint_iteration, "hands": checkpoint_hands},
        "slumbot": {
            "hands": latest_slumbot.get("hands"),
            "bb_per_100": latest_slumbot.get("bb_per_100"),
            "ci_lower": latest_slumbot.get("lower_bound_bb_per_100"),
            "can_claim_l5": can_l5,
            "can_claim_l6": can_l6,
        },
        "next_external_eval": cadence.get("next_external_eval"),
        "source_artifacts": {
            "gate": str(gate_record["path"]) if gate_record else str(run_dir / f"gate_{target}_status.json") if target else None,
            "health": str(run_dir / "health_status.json"),
            "health_warning_diagnosis": str(run_dir / "v5_health_warning_diagnosis.json"),
            "preflop_probe": str(run_dir / "v5_preflop_probe_latest.json"),
            "intervention": str(intervention_path),
            "scorecard": str(run_dir / "v5_scorecard.json"),
            "claim_audit": str(run_dir / "v5_l6_claim_audit.json"),
            "speed_decision": str(run_dir / "v5_l6_speed_decision.json"),
        },
        "claim_rule": "Do not promote as V4/L5/L6 winner without 100k+ Slumbot hands, bb/100 > 0, and CI lower > 0; L6 also needs near +11.1 bb/100.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    live = summary["live"]
    checkpoint = summary["checkpoint"]
    slumbot = summary["slumbot"]
    lines = [
        "# V5 Checkpoint Promotion Decision",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Target iteration: `{summary['target_iteration']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        f"- Live/checkpoint iteration: `{live['iteration']}` / `{checkpoint['iteration']}`",
        f"- Live/checkpoint hands: `{live['hands']}` / `{checkpoint['hands']}`",
        "",
        "Checks:",
        "",
    ]
    for item in summary["checks"]:
        lines.append(f"- {item['status']}: `{item['name']}` - {item['detail']}")
    lines.extend(
        [
            "",
            "Slumbot claim state:",
            "",
            f"- Hands / bb100 / lower: `{slumbot['hands']}` / `{fmt(slumbot['bb_per_100'])}` / `{fmt(slumbot['ci_lower'])}`",
            f"- Can claim L5 / L6: `{slumbot['can_claim_l5']}` / `{slumbot['can_claim_l6']}`",
            "",
            "Claim rule:",
            "",
            f"- {summary['claim_rule']}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only V5 checkpoint promotion decision.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--target-iteration", type=int)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_decision(Path(args.run_dir), Path(args.output_dir), args.target_iteration)
    print(f"overall={summary['overall']}")
    print(f"recommendation={summary['recommendation']}")
    if args.out_json:
        write_json(Path(args.out_json), summary)
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
