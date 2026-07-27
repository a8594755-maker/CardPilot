#!/usr/bin/env python3
"""Audit V5 against the L6 AlphaHoldem-style goal.

This is a read-only requirements audit. It deliberately treats completion as
unproven unless current artifacts prove the specific requirement. Training
health, local probes, and Slumbot CI are separated so local progress cannot be
mistaken for an L5/L6 strength claim.
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
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"{path} root is not an object", "_path": str(path)}


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        import torch

        obj = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    return obj if isinstance(obj, dict) else {"_load_error": f"checkpoint is {type(obj).__name__}", "_path": str(path)}


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


def fmt_count(value: Any) -> str:
    """Format an optional integer count without crashing reporting-only audits."""
    if value is None:
        return "unknown"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError, OverflowError):
        return "unknown"


def check(status: str, key: str, requirement: str, evidence: str, action: str = "") -> dict[str, str]:
    return {
        "status": status,
        "key": key,
        "requirement": requirement,
        "evidence": evidence,
        "action": action,
    }


def model_roots(checkpoint: dict[str, Any]) -> set[str]:
    state = checkpoint.get("model") or checkpoint.get("model_state_dict") or {}
    if not isinstance(state, dict):
        return set()
    return {str(name).split(".")[0] for name in state.keys()}


def build_audit(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = load_json(run_dir / "run_manifest.json")
    progress = load_json(run_dir / "progress_status.json")
    health = load_json(run_dir / "health_status.json")
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    scorecard = load_json(run_dir / "v5_scorecard.json")
    baseline = load_json(run_dir / "v5_baseline_gap.json")
    cadence = load_json(run_dir / "v5_eval_cadence.json")
    speed = load_json(run_dir / "v5_l6_speed_decision.json")
    action_queue = load_json(run_dir / "v5_next_action_queue.json")
    checkpoint_path = Path(str(manifest.get("checkpoint") or run_dir / "latest.pt"))
    checkpoint = load_checkpoint(checkpoint_path)
    cfg = checkpoint.get("config") if isinstance(checkpoint.get("config"), dict) else {}
    goal = checkpoint.get("goal") if isinstance(checkpoint.get("goal"), dict) else manifest.get("goal") or {}
    roots = model_roots(checkpoint)

    live_hands = int(manifest.get("total_hands") or pick(progress, "latest", "hands") or checkpoint.get("total_hands") or 0)
    checkpoint_hands = int(checkpoint.get("total_hands") or 0)
    latest_slumbot = baseline.get("latest_slumbot") if isinstance(baseline.get("latest_slumbot"), dict) else {}
    claim_rules = baseline.get("claim_rules") if isinstance(baseline.get("claim_rules"), dict) else {}
    l6_gap = baseline.get("gap") if isinstance(baseline.get("gap"), dict) else baseline.get("l5_l6_gap") or {}
    internal_latest = pick(scorecard, "internal_probes", "latest", default={}) or {}

    items: list[dict[str, str]] = []
    paper_ref = pick(goal, "reference", "paper") or pick(manifest, "goal", "reference", "paper")
    items.append(
        check(
            "PASS" if paper_ref else "MISSING",
            "reference",
            "Reference Zhao et al. AlphaHoldem AAAI 2022 and +11.1 bb/100 target.",
            str(paper_ref or "reference metadata missing"),
        )
    )
    env_ok = checkpoint.get("env_version") == "v55" and checkpoint.get("starting_stack_bb") == 200.0
    items.append(
        check(
            "PASS" if env_ok else "FAIL",
            "environment",
            "200bb HUNL environment aligned with Slumbot benchmark stack depth.",
            f"env={checkpoint.get('env_version')}, stack={checkpoint.get('starting_stack_bb')}, actual_hand_accounting={checkpoint.get('actual_hand_accounting')}",
        )
    )
    lineage_ok = bool(checkpoint.get("fresh_from_zero_lineage"))
    items.append(
        check(
            "PASS" if lineage_ok else "FAIL",
            "from_zero_lineage",
            "V5 should be from-zero lineage even when resumed through continuation checkpoints.",
            f"fresh_from_zero_lineage={checkpoint.get('fresh_from_zero_lineage')}, root={checkpoint.get('lineage_root_run_id')}",
        )
    )
    arch_ok = {"card_cnn", "action_cnn", "extra_fc", "policy_head", "value_head"}.issubset(roots)
    items.append(
        check(
            "PASS" if arch_ok else "FAIL",
            "network_architecture",
            "Pseudo-Siamese card/action/extra branches with policy and value heads.",
            f"model roots={sorted(roots)}",
        )
    )
    action_ok = checkpoint.get("action_space_version") == "9slot_v5"
    items.append(
        check(
            "PASS" if action_ok else "FAIL",
            "action_space",
            "9-action discrete action space including fold/check-call/raises/all-in.",
            f"action_space_version={checkpoint.get('action_space_version')}",
        )
    )
    trinal_ok = "Trinal" in str(pick(goal, "method", "loss", default="")) and float(cfg.get("delta1") or 0.0) > 0.0
    items.append(
        check(
            "PASS" if trinal_ok else "FAIL",
            "trinal_clip_ppo",
            "Actor-critic PPO with Trinal-Clip policy/value constraints based on committed chips.",
            f"loss={pick(goal, 'method', 'loss')}, delta1={cfg.get('delta1')}, gamma={cfg.get('gamma')}",
        )
    )
    pool_ok = int(cfg.get("k_best") or 0) >= 5 and len(checkpoint.get("pool_active_metadata") or []) >= 5
    items.append(
        check(
            "PASS_WITH_DEVIATION" if pool_ok and checkpoint.get("pool_strategy") == "loss-kbest" else ("PASS" if pool_ok else "FAIL"),
            "k_best_pool",
            "K-best self-play opponent pool; deviations must be recorded and benchmarked.",
            f"k={cfg.get('k_best')}, strategy={checkpoint.get('pool_strategy')}, active_pool={len(checkpoint.get('pool_active_metadata') or [])}",
            "Keep treating loss-kbest as a proxy until Slumbot/internal evidence proves it is adequate.",
        )
    )
    health_ok = health.get("overall") == "PASS" and health_diag.get("overall") == "PASS"
    items.append(
        check(
            "PASS" if health_ok else "WATCH",
            "training_health",
            "Value loss, entropy, and action mix must not collapse.",
            f"health={health.get('overall')}, rolling={health_diag.get('overall')}, preflop_probe={preflop_probe.get('overall')}",
        )
    )
    hand_status = "IN_PROGRESS"
    if live_hands >= 2_700_000_000:
        hand_status = "PAPER_SCALE_REACHED"
    elif live_hands >= 1_000_000_000:
        hand_status = "MEANINGFUL_BASELINE_SCALE"
    items.append(
        check(
            hand_status,
            "training_scale",
            "Meaningful baseline around 1B hands; paper-scale target around 2.7B hands.",
            f"live_hands={live_hands:,}, checkpoint_hands={checkpoint_hands:,}, target_total={fmt_count(cfg.get('total_hands'))}",
            "Continue scheduled training; do not infer strength from hand count alone.",
        )
    )
    internal_verdict = internal_latest.get("verdict")
    items.append(
        check(
            "WATCH" if internal_verdict == "REGRESSION_RISK_INTERNAL" else ("PASS" if internal_verdict else "PENDING"),
            "internal_eval",
            "Internal eval should not show major regression before promotion.",
            f"latest_internal_target={internal_latest.get('checkpoint_iteration')}, verdict={internal_verdict}, mean_lower={internal_latest.get('mean_latest_lower_bound_bb100')}",
            "Wait for internal_probe_4400 before intervention decisions.",
        )
    )
    slumbot_hands = int(latest_slumbot.get("hands") or 0)
    slumbot_bb100 = latest_slumbot.get("bb_per_100")
    slumbot_lower = latest_slumbot.get("lower_bound_bb_per_100")
    formal_l5 = bool(claim_rules.get("can_claim_l5"))
    items.append(
        check(
            "PASS" if formal_l5 else "BLOCKED",
            "formal_l5_slumbot",
            "Primary target: 100k+ Slumbot hands, bb/100 > 0, 95% CI lower > 0.",
            f"hands={slumbot_hands}, bb100={fmt(slumbot_bb100)}, lower={fmt(slumbot_lower)}, can_claim_l5={formal_l5}",
            "Next Slumbot quick screen is diagnostic only; formal claim requires 100k+ positive CI.",
        )
    )
    formal_l6 = bool(claim_rules.get("can_claim_l6"))
    items.append(
        check(
            "PASS" if formal_l6 else "BLOCKED",
            "formal_l6_slumbot",
            "Stretch target: near AlphaHoldem paper claim +11.1 bb/100 vs Slumbot.",
            f"can_claim_l6={formal_l6}, gap_to_l6={fmt(l6_gap.get('to_l6_target_bb100') or l6_gap.get('gap_to_l6_target_bb100'))}",
            "Only formal Slumbot CI can close this requirement.",
        )
    )
    items.append(
        check(
            "WATCH",
            "generalization_not_overfit",
            "Model should remain a general 200bb HUNL agent, not only a Slumbot overfit.",
            f"preflop_probe={preflop_probe.get('overall')}, internal_verdict={internal_verdict}",
            "Keep local probes/internal pools, but require external Slumbot/formal evidence for claims.",
        )
    )
    items.append(
        check(
            "WATCH" if speed.get("decision") == "WAIT_FOR_GATE_BEFORE_SPEED_CHANGE" else "PASS",
            "throughput",
            "Throughput optimization is allowed, but only in a controlled evidence window.",
            f"decision={speed.get('decision')}, effective_hps={fmt(pick(speed, 'throughput', 'effective_hps_latest'))}, next_action={action_queue.get('overall')}",
            "Do not run sweeps while the active trainer owns the current evidence window.",
        )
    )

    blockers = [item for item in items if item["status"] in {"FAIL", "BLOCKED", "MISSING"}]
    watches = [item for item in items if item["status"] in {"WATCH", "PASS_WITH_DEVIATION", "IN_PROGRESS"}]
    if any(item["key"] == "formal_l6_slumbot" and item["status"] == "PASS" for item in items):
        overall = "L6_PROVEN"
    elif formal_l5:
        overall = "L5_PROVEN_NOT_L6"
    elif blockers:
        overall = "L6_NOT_PROVEN"
    else:
        overall = "ENGINEERING_READY_STRENGTH_UNPROVEN"

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "overall": overall,
        "items": items,
        "blockers": blockers,
        "watches": watches,
        "summary": {
            "live_hands": live_hands,
            "checkpoint_iteration": checkpoint.get("iteration"),
            "checkpoint_hands": checkpoint_hands,
            "health": health.get("overall"),
            "rolling_health": health_diag.get("overall"),
            "latest_slumbot_hands": slumbot_hands,
            "latest_slumbot_bb100": slumbot_bb100,
            "latest_slumbot_lower": slumbot_lower,
            "can_claim_l5": formal_l5,
            "can_claim_l6": formal_l6,
            "next_external_eval": pick(cadence, "next_external_eval", "target_hands"),
            "next_external_state": pick(cadence, "next_external_eval", "state"),
        },
        "claim_rule": "L5/L6 requires 100k+ Slumbot hands, bb/100 > 0, and CI lower > 0; L6 also needs near +11.1 bb/100.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    s = summary["summary"]
    lines = [
        "# V5 L6 Claim Audit",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Live/checkpoint hands: `{s['live_hands']}` / `{s['checkpoint_hands']}`",
        f"- Checkpoint iteration: `{s['checkpoint_iteration']}`",
        f"- Health / rolling health: `{s['health']}` / `{s['rolling_health']}`",
        f"- Latest Slumbot: hands `{s['latest_slumbot_hands']}`, bb/100 `{fmt(s['latest_slumbot_bb100'])}`, CI lower `{fmt(s['latest_slumbot_lower'])}`",
        f"- Can claim L5 / L6: `{s['can_claim_l5']}` / `{s['can_claim_l6']}`",
        "",
        "Audit Items:",
        "",
        "| status | key | evidence | next action |",
        "|---|---|---|---|",
    ]
    for item in summary["items"]:
        lines.append(
            f"| {item['status']} | `{item['key']}` | {item['evidence']} | {item.get('action') or ''} |"
        )
    lines.extend(["", "Blockers:", ""])
    for item in summary["blockers"]:
        lines.append(f"- `{item['key']}`: {item['requirement']} Evidence: {item['evidence']}")
    lines.extend(["", "Claim rule:", "", f"- {summary['claim_rule']}", ""])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit V5 against the L6 AlphaHoldem-style goal.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_audit(Path(args.run_dir), Path(args.output_dir))
    print(f"overall={summary['overall']}")
    print(f"blockers={len(summary['blockers'])}")
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
