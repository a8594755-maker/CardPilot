#!/usr/bin/env python3
"""Evaluate V5 Slumbot benchmark artifacts against promotion gates.

This script does not call the Slumbot API. It consumes:

- a V5 checkpoint
- an optional run_dir containing health_status.json
- a CI JSON produced by slumbot_ci_from_hands.py

It then emits a single audit JSON/Markdown summary for 20k promotion, formal
L5, and L6 claims.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc)}


def load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True}
    try:
        obj = torch.load(path, map_location="cpu", weights_only=False)
    except Exception as exc:
        return {"_load_error": str(exc)}
    if not isinstance(obj, dict):
        return {"_load_error": f"checkpoint is {type(obj).__name__}, not dict"}
    return obj


def fresh_from_zero_lineage(checkpoint: dict[str, Any]) -> bool:
    if "fresh_from_zero_lineage" in checkpoint:
        return bool(checkpoint.get("fresh_from_zero_lineage"))
    return checkpoint.get("version") == "v5.zero" and checkpoint.get("resume") is None


def approx_equal(value: Any, expected: float, tolerance: float = 1e-6) -> bool:
    try:
        return abs(float(value) - expected) <= tolerance
    except Exception:
        return False


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def validate_terminal_endpoint_health(
    *,
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
    run_dir: Path,
    endpoint_status_path: Path,
    protocol_status_path: Path,
) -> tuple[bool, str, dict[str, Any]]:
    """Bind a frozen benchmark copy to a finished endpoint without live health."""
    endpoint = load_json(endpoint_status_path)
    protocol = load_json(protocol_status_path)
    manifest = load_json(run_dir / "run_manifest.json")
    errors: list[str] = []
    if endpoint.get("_missing") or endpoint.get("_load_error"):
        errors.append("endpoint status missing or unreadable")
    if protocol.get("_missing") or protocol.get("_load_error"):
        errors.append("protocol status missing or unreadable")
    if manifest.get("_missing") or manifest.get("_load_error"):
        errors.append("run manifest missing or unreadable")
    if manifest.get("status") != "finished":
        errors.append(f"manifest status {manifest.get('status')!r} is not finished")
    if endpoint.get("overall") != "PASS" or endpoint.get("state") != "ARM_ENDPOINT_FROZEN":
        errors.append("endpoint is not ARM_ENDPOINT_FROZEN/PASS")
    if protocol.get("overall") != "PASS" or protocol.get("state") != "ARM_FINISHED_GUARDS_PASS":
        errors.append("protocol is not ARM_FINISHED_GUARDS_PASS/PASS")

    endpoint_checkpoint = Path(str(endpoint.get("checkpoint_path") or ""))
    endpoint_sha = ""
    if not endpoint_checkpoint.is_file():
        errors.append("endpoint checkpoint path missing")
    else:
        endpoint_sha = sha256_file(endpoint_checkpoint)
    candidate_sha = sha256_file(checkpoint_path) if checkpoint_path.is_file() else ""
    if endpoint.get("checkpoint_sha256") != endpoint_sha:
        errors.append("endpoint checkpoint SHA256 mismatch")
    if not candidate_sha or candidate_sha != endpoint_sha:
        errors.append("frozen benchmark checkpoint SHA256 mismatch")

    expected_iter = int(checkpoint.get("iteration") or 0)
    expected_hands = int(checkpoint.get("total_hands") or 0)
    if int(endpoint.get("iteration") or 0) != expected_iter:
        errors.append("endpoint iteration mismatch")
    if int(endpoint.get("hands") or 0) != expected_hands:
        errors.append("endpoint hands mismatch")
    if int(manifest.get("iteration") or 0) != expected_iter:
        errors.append("manifest iteration mismatch")
    if int(manifest.get("total_hands") or 0) != expected_hands:
        errors.append("manifest hands mismatch")
    if endpoint.get("run_id") != checkpoint.get("run_id"):
        errors.append("endpoint run_id mismatch")
    if manifest.get("run_id") != checkpoint.get("run_id"):
        errors.append("manifest run_id mismatch")
    if protocol.get("arm") != endpoint.get("arm"):
        errors.append("endpoint/protocol arm mismatch")

    payload = {
        "endpoint_status_path": str(endpoint_status_path),
        "protocol_status_path": str(protocol_status_path),
        "endpoint_checkpoint_path": str(endpoint_checkpoint),
        "endpoint_checkpoint_sha256": endpoint_sha,
        "benchmark_checkpoint_sha256": candidate_sha,
        "manifest_status": manifest.get("status"),
        "endpoint_state": endpoint.get("state"),
        "protocol_state": protocol.get("state"),
        "iteration": expected_iter,
        "training_hands": expected_hands,
        "errors": errors,
    }
    detail = "terminal endpoint/protocol identity PASS" if not errors else "; ".join(errors)
    return not errors, detail, payload


def float_rate(value: Any) -> float:
    try:
        return float(value or 0.0)
    except Exception:
        return 0.0


def postflop_aggression(section: dict[str, Any] | None) -> dict[str, Any]:
    streets = (section or {}).get("streets") or {}
    per_street: dict[str, float] = {}
    counts: dict[str, int] = {}
    for street in ("flop", "turn", "river"):
        entry = streets.get(street) or {}
        rates = entry.get("rates") or {}
        count = int(entry.get("count") or 0)
        if count <= 0 and not rates:
            continue
        per_street[street] = float_rate(rates.get("raise")) + float_rate(rates.get("allin"))
        counts[street] = count
    max_street = max(per_street, key=per_street.get) if per_street else None
    return {
        "max": per_street[max_street] if max_street else None,
        "max_street": max_street,
        "per_street": per_street,
        "counts": counts,
    }


def evaluate_aggression_metric(
    label: str,
    metric: dict[str, Any],
    warn_threshold: float,
    fail_threshold: float,
) -> tuple[str, str]:
    max_value = metric.get("max")
    if max_value is None:
        return "WARN", f"{label} postflop aggression unavailable"
    detail = (
        f"{label} max postflop raise+all-in={float(max_value):.3f} "
        f"on {metric.get('max_street')}; warn>{warn_threshold:.3f}, fail>{fail_threshold:.3f}"
    )
    if float(max_value) > fail_threshold:
        return "FAIL", detail
    if float(max_value) > warn_threshold:
        return "WARN", detail
    return "PASS", detail


def evaluate_selector_replay(
    selector_replay_path: Path | None,
    *,
    played_warn: float,
    played_fail: float,
    greedy_warn: float,
    greedy_fail: float,
    mass_warn: float,
    mass_fail: float,
) -> dict[str, Any]:
    if selector_replay_path is None:
        return {
            "status": "WARN",
            "path": None,
            "clean": False,
            "checks": [
                {
                    "name": "selector_replay_provided",
                    "status": "WARN",
                    "detail": "selector replay JSON not provided; postflop selector behavior not verified",
                }
            ],
            "metrics": {},
        }

    replay = load_json(selector_replay_path)
    if replay.get("_missing"):
        return {
            "status": "FAIL",
            "path": str(selector_replay_path),
            "clean": False,
            "checks": [
                {
                    "name": "selector_replay_load",
                    "status": "FAIL",
                    "detail": f"missing: {selector_replay_path}",
                }
            ],
            "metrics": {},
        }
    if replay.get("_load_error"):
        return {
            "status": "FAIL",
            "path": str(selector_replay_path),
            "clean": False,
            "checks": [
                {
                    "name": "selector_replay_load",
                    "status": "FAIL",
                    "detail": str(replay["_load_error"]),
                }
            ],
            "metrics": {},
        }

    metrics = {
        "played": postflop_aggression(replay.get("actual") or {}),
        "greedy": postflop_aggression(((replay.get("policies") or {}).get("greedy") or {})),
        "raw_probability_mass": postflop_aggression(((replay.get("probability_mass") or {}).get("raw") or {})),
    }
    checks: list[dict[str, str]] = [
        {"name": "selector_replay_load", "status": "PASS", "detail": f"loaded {selector_replay_path}"}
    ]
    for name, warn, fail in (
        ("played", played_warn, played_fail),
        ("greedy", greedy_warn, greedy_fail),
        ("raw_probability_mass", mass_warn, mass_fail),
    ):
        metric = metrics[name]
        status, detail = evaluate_aggression_metric(name, metric, warn, fail)
        if name == "raw_probability_mass" and metric.get("max") is None:
            status = "WARN"
            detail = "raw probability mass unavailable; rerun selector replay with probability-mass support for stronger audit"
        checks.append({"name": f"selector_replay_{name}_postflop_aggression", "status": status, "detail": detail})

    if any(check["status"] == "FAIL" for check in checks):
        status = "FAIL"
    elif any(check["status"] == "WARN" for check in checks):
        status = "WARN"
    else:
        status = "PASS"
    return {
        "status": status,
        "path": str(selector_replay_path),
        "clean": status == "PASS",
        "checks": checks,
        "metrics": metrics,
    }


def evaluate(
    checkpoint_path: Path,
    ci_json_path: Path,
    run_dir: Path | None,
    min_promotion_hands: int,
    expected_stack_bb: float,
    selector_replay_path: Path | None = None,
    selector_postflop_played_warn: float = 0.75,
    selector_postflop_played_fail: float = 0.85,
    selector_postflop_greedy_warn: float = 0.75,
    selector_postflop_greedy_fail: float = 0.85,
    selector_postflop_mass_warn: float = 0.75,
    selector_postflop_mass_fail: float = 0.85,
    terminal_endpoint_status_path: Path | None = None,
    terminal_protocol_status_path: Path | None = None,
) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    checkpoint = load_checkpoint(checkpoint_path)
    ci = load_json(ci_json_path)
    health = load_json(run_dir / "health_status.json") if run_dir else {}
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json") if run_dir else {}

    checks: list[dict[str, str]] = []

    checkpoint_ready = not checkpoint.get("_missing") and not checkpoint.get("_load_error")
    ci_ready = not ci.get("_missing") and not ci.get("_load_error")

    if checkpoint.get("_missing"):
        add_check(checks, "checkpoint_load", "FAIL", f"missing: {checkpoint_path}")
    elif checkpoint.get("_load_error"):
        add_check(checks, "checkpoint_load", "FAIL", str(checkpoint["_load_error"]))
    else:
        add_check(checks, "checkpoint_load", "PASS", f"loaded {checkpoint_path}")

    expected_metadata = {
        "version": "v5.zero",
        "env_version": "v55",
        "obs_version": "v55",
        "action_space_version": "9slot_v5",
    }
    for key, expected in expected_metadata.items():
        actual = checkpoint.get(key)
        if not checkpoint_ready:
            add_check(checks, key, "FAIL", "checkpoint unavailable")
        elif actual == expected:
            add_check(checks, key, "PASS", f"{key}={actual}")
        else:
            add_check(checks, key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if not checkpoint_ready:
        add_check(checks, "starting_stack_bb", "FAIL", "checkpoint unavailable")
    elif approx_equal(checkpoint.get("starting_stack_bb"), expected_stack_bb):
        add_check(checks, "starting_stack_bb", "PASS", f"starting_stack_bb={checkpoint.get('starting_stack_bb')}")
    else:
        add_check(
            checks,
            "starting_stack_bb",
            "FAIL",
            f"starting_stack_bb={checkpoint.get('starting_stack_bb')!r}, expected {expected_stack_bb}",
        )

    if not checkpoint_ready:
        add_check(checks, "actual_hand_accounting", "FAIL", "checkpoint unavailable")
    elif checkpoint.get("actual_hand_accounting") is True:
        add_check(checks, "actual_hand_accounting", "PASS", "actual_hand_accounting=True")
    else:
        add_check(
            checks,
            "actual_hand_accounting",
            "FAIL",
            f"actual_hand_accounting={checkpoint.get('actual_hand_accounting')!r}, expected True",
        )

    if not checkpoint_ready:
        add_check(checks, "fresh_from_zero_lineage", "FAIL", "checkpoint unavailable")
    elif fresh_from_zero_lineage(checkpoint):
        add_check(checks, "fresh_from_zero_lineage", "PASS", "fresh_from_zero_lineage=True")
    else:
        add_check(
            checks,
            "fresh_from_zero_lineage",
            "FAIL",
            f"fresh_from_zero_lineage={checkpoint.get('fresh_from_zero_lineage')!r}; resume={checkpoint.get('resume')!r}",
        )

    health_overall = health.get("overall")
    terminal_evidence: dict[str, Any] | None = None
    terminal_paths_supplied = bool(terminal_endpoint_status_path or terminal_protocol_status_path)
    if terminal_paths_supplied:
        if not run_dir or not terminal_endpoint_status_path or not terminal_protocol_status_path or not checkpoint_ready:
            add_check(
                checks,
                "terminal_endpoint_health",
                "FAIL",
                "run_dir, readable checkpoint and both terminal status paths are required",
            )
        else:
            terminal_ok, terminal_detail, terminal_evidence = validate_terminal_endpoint_health(
                checkpoint_path=checkpoint_path,
                checkpoint=checkpoint,
                run_dir=run_dir,
                endpoint_status_path=terminal_endpoint_status_path,
                protocol_status_path=terminal_protocol_status_path,
            )
            add_check(checks, "terminal_endpoint_health", "PASS" if terminal_ok else "FAIL", terminal_detail)
            if terminal_ok:
                health_overall = "TERMINAL_ENDPOINT_PASS"
    elif not run_dir:
        add_check(checks, "health_status", "WARN", "no run_dir provided; health not verified")
    elif health.get("_missing"):
        add_check(checks, "health_status", "FAIL", f"missing health_status.json in {run_dir}")
    elif health.get("_load_error"):
        add_check(checks, "health_status", "FAIL", str(health["_load_error"]))
    elif health_overall in {"PASS", "WARN"}:
        add_check(checks, "health_status", "PASS" if health_overall == "PASS" else "WARN", f"health overall {health_overall}")
    else:
        add_check(checks, "health_status", "FAIL", f"health overall {health_overall!r}")

    preflop_overall = preflop_probe.get("overall")
    if not run_dir:
        add_check(checks, "preflop_guardrail", "WARN", "no run_dir provided; preflop probe not verified")
    elif preflop_probe.get("_missing"):
        add_check(checks, "preflop_guardrail", "WARN", f"missing v5_preflop_probe_latest.json in {run_dir}")
    elif preflop_probe.get("_load_error"):
        add_check(checks, "preflop_guardrail", "WARN", str(preflop_probe["_load_error"]))
    elif preflop_overall == "PASS":
        add_check(checks, "preflop_guardrail", "PASS", "preflop probe PASS")
    elif preflop_overall in {"WARN", "FAIL"}:
        add_check(checks, "preflop_guardrail", "WARN", f"preflop probe {preflop_overall}")
    else:
        add_check(checks, "preflop_guardrail", "WARN", f"preflop probe status {preflop_overall!r}")

    selector_replay = evaluate_selector_replay(
        selector_replay_path,
        played_warn=selector_postflop_played_warn,
        played_fail=selector_postflop_played_fail,
        greedy_warn=selector_postflop_greedy_warn,
        greedy_fail=selector_postflop_greedy_fail,
        mass_warn=selector_postflop_mass_warn,
        mass_fail=selector_postflop_mass_fail,
    )
    checks.extend(selector_replay["checks"])

    if ci.get("_missing"):
        add_check(checks, "ci_json", "FAIL", f"missing: {ci_json_path}")
    elif ci.get("_load_error"):
        add_check(checks, "ci_json", "FAIL", str(ci["_load_error"]))
    else:
        add_check(checks, "ci_json", "PASS", f"loaded {ci_json_path}")

    input_files = ci.get("input_files") if ci_ready else None
    if isinstance(input_files, list) and input_files:
        missing = [str(path) for path in input_files if not Path(path).exists()]
        if missing:
            add_check(checks, "hand_artifacts", "FAIL", f"missing input files: {missing}")
        else:
            add_check(checks, "hand_artifacts", "PASS", f"{len(input_files)} hand artifact files exist")
    elif ci_ready:
        add_check(checks, "hand_artifacts", "FAIL", "ci_json has no input_files list")
    else:
        add_check(checks, "hand_artifacts", "FAIL", "ci_json unavailable")

    hands = int(ci.get("hands") or 0) if ci_ready else 0
    bb100 = float(ci.get("bb_per_100") or 0.0) if ci_ready else 0.0
    lower = float(ci.get("lower_bound_bb_per_100") or 0.0) if ci_ready else 0.0
    milestone_level = str(ci.get("milestone_level") or "unknown") if ci_ready else "unknown"
    l5_formal = bool(ci.get("l5_formal_win")) if ci_ready else False
    l6 = bool(ci.get("l6_near_paper_target")) if ci_ready else False
    baseline_improved = bool(ci.get("baseline_point_estimate_improved")) if ci_ready else False
    baseline_lcb_above = bool(ci.get("baseline_ci_lower_above_baseline")) if ci_ready else False

    if hands >= min_promotion_hands:
        add_check(checks, "promotion_hands", "PASS", f"hands={hands} >= {min_promotion_hands}")
    else:
        add_check(checks, "promotion_hands", "FAIL", f"hands={hands} < {min_promotion_hands}")

    hard_fail = any(c["status"] == "FAIL" for c in checks)
    metadata_health_artifacts_ok = not hard_fail
    preflop_guardrail_clean = preflop_overall == "PASS"
    selector_replay_clean = bool(selector_replay.get("clean"))
    promotion_20k_candidate = (
        metadata_health_artifacts_ok
        and preflop_guardrail_clean
        and selector_replay_clean
        and hands >= min_promotion_hands
        and baseline_improved
    )
    promotion_20k_strong = promotion_20k_candidate and baseline_lcb_above
    formal_l5_claim = metadata_health_artifacts_ok and preflop_guardrail_clean and selector_replay_clean and l5_formal
    formal_l6_claim = metadata_health_artifacts_ok and preflop_guardrail_clean and selector_replay_clean and l6

    result = {
        "checked_at": now.isoformat(),
        "checkpoint_path": str(checkpoint_path),
        "ci_json_path": str(ci_json_path),
        "run_dir": str(run_dir) if run_dir else None,
        "checks": checks,
        "checkpoint": {
            "version": checkpoint.get("version"),
            "run_id": checkpoint.get("run_id"),
            "iteration": checkpoint.get("iteration"),
            "total_hands": checkpoint.get("total_hands"),
            "env_version": checkpoint.get("env_version"),
            "obs_version": checkpoint.get("obs_version"),
            "action_space_version": checkpoint.get("action_space_version"),
            "starting_stack_bb": checkpoint.get("starting_stack_bb"),
            "actual_hand_accounting": checkpoint.get("actual_hand_accounting"),
            "fresh_from_zero_lineage": fresh_from_zero_lineage(checkpoint) if checkpoint_ready else None,
        },
        "health_overall": health_overall,
        "terminal_endpoint_evidence": terminal_evidence,
        "preflop_guardrail": {
            "overall": preflop_overall,
            "path": str(run_dir / "v5_preflop_probe_latest.json") if run_dir else None,
            "clean": preflop_guardrail_clean,
            "warnings": preflop_probe.get("warnings") if isinstance(preflop_probe, dict) else None,
        },
        "selector_replay": selector_replay,
        "slumbot": {
            "hands": hands,
            "bb_per_100": bb100,
            "lower_bound_bb_per_100": lower,
            "upper_bound_bb_per_100": ci.get("upper_bound_bb_per_100") if ci_ready else None,
            "milestone_level": milestone_level,
            "milestone_meaning": ci.get("milestone_meaning") if ci_ready else None,
            "l5_blockers": ci.get("l5_blockers") if ci_ready else None,
            "baseline_delta_bb_per_100": ci.get("baseline_delta_bb_per_100") if ci_ready else None,
        },
        "decisions": {
            "promotion_20k_candidate": promotion_20k_candidate,
            "promotion_20k_strong": promotion_20k_strong,
            "formal_l5_claim": formal_l5_claim,
            "formal_l6_claim": formal_l6_claim,
            "preflop_guardrail_clean": preflop_guardrail_clean,
            "selector_replay_clean": selector_replay_clean,
        },
        "overall": "FAIL" if hard_fail else "PASS",
    }
    return result


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    sl = summary["slumbot"]
    decisions = summary["decisions"]
    preflop = summary.get("preflop_guardrail") or {}
    selector = summary.get("selector_replay") or {}
    selector_metrics = selector.get("metrics") or {}
    lines = [
        "# V5 Slumbot Promotion Gate",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall metadata/artifact status: **{summary['overall']}**",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- CI JSON: `{summary['ci_json_path']}`",
        f"- Run dir: `{summary.get('run_dir')}`",
        "",
        "Slumbot result:",
        "",
        f"- Hands: `{sl['hands']:,}`",
        f"- bb/100: `{sl['bb_per_100']:+.2f}`",
        f"- 95% CI lower: `{sl['lower_bound_bb_per_100']:+.2f}`",
        f"- Milestone: `{sl['milestone_level']}` - {sl.get('milestone_meaning')}",
        f"- L5 blockers: `{sl.get('l5_blockers')}`",
        "",
        "Preflop guardrail:",
        "",
        f"- Overall: `{preflop.get('overall')}`",
        f"- Clean for promotion: `{preflop.get('clean')}`",
        f"- Probe JSON: `{preflop.get('path')}`",
        "",
        "Selector replay guardrail:",
        "",
        f"- Overall: `{selector.get('status')}`",
        f"- Clean for promotion: `{selector.get('clean')}`",
        f"- Replay JSON: `{selector.get('path')}`",
    ]
    for name in ("played", "greedy", "raw_probability_mass"):
        metric = selector_metrics.get(name) or {}
        if metric.get("max") is None:
            lines.append(f"- {name} max postflop raise+all-in: `unavailable`")
        else:
            lines.append(
                f"- {name} max postflop raise+all-in: `{float(metric['max']):.3f}` "
                f"on `{metric.get('max_street')}`"
            )
    lines += [
        "",
        "Decisions:",
        "",
    ]
    for key, value in decisions.items():
        lines.append(f"- `{key}`: `{value}`")
    lines += ["", "Checks:", ""]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", required=True)
    parser.add_argument("--ci-json", required=True)
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    parser.add_argument("--min-promotion-hands", type=int, default=20_000)
    parser.add_argument("--expected-stack-bb", type=float, default=200.0)
    parser.add_argument("--selector-replay-json", default="")
    parser.add_argument("--selector-postflop-played-warn", type=float, default=0.75)
    parser.add_argument("--selector-postflop-played-fail", type=float, default=0.85)
    parser.add_argument("--selector-postflop-greedy-warn", type=float, default=0.75)
    parser.add_argument("--selector-postflop-greedy-fail", type=float, default=0.85)
    parser.add_argument("--selector-postflop-mass-warn", type=float, default=0.75)
    parser.add_argument("--selector-postflop-mass-fail", type=float, default=0.85)
    parser.add_argument("--terminal-endpoint-status-json", default="")
    parser.add_argument("--terminal-protocol-status-json", default="")
    args = parser.parse_args()

    summary = evaluate(
        checkpoint_path=Path(args.checkpoint),
        ci_json_path=Path(args.ci_json),
        run_dir=Path(args.run_dir) if args.run_dir else None,
        min_promotion_hands=args.min_promotion_hands,
        expected_stack_bb=args.expected_stack_bb,
        selector_replay_path=Path(args.selector_replay_json) if args.selector_replay_json else None,
        selector_postflop_played_warn=args.selector_postflop_played_warn,
        selector_postflop_played_fail=args.selector_postflop_played_fail,
        selector_postflop_greedy_warn=args.selector_postflop_greedy_warn,
        selector_postflop_greedy_fail=args.selector_postflop_greedy_fail,
        selector_postflop_mass_warn=args.selector_postflop_mass_warn,
        selector_postflop_mass_fail=args.selector_postflop_mass_fail,
        terminal_endpoint_status_path=Path(args.terminal_endpoint_status_json) if args.terminal_endpoint_status_json else None,
        terminal_protocol_status_path=Path(args.terminal_protocol_status_json) if args.terminal_protocol_status_json else None,
    )

    print(f"overall={summary['overall']}")
    print(f"milestone_level={summary['slumbot']['milestone_level']}")
    print(f"promotion_20k_candidate={summary['decisions']['promotion_20k_candidate']}")
    print(f"promotion_20k_strong={summary['decisions']['promotion_20k_strong']}")
    print(f"formal_l5_claim={summary['decisions']['formal_l5_claim']}")
    print(f"formal_l6_claim={summary['decisions']['formal_l6_claim']}")
    print(f"selector_replay_clean={summary['decisions']['selector_replay_clean']}")

    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
        print(f"wrote={out_json}")
    if args.out_md:
        out_md = Path(args.out_md)
        out_md.parent.mkdir(parents=True, exist_ok=True)
        write_markdown(out_md, summary)
        print(f"wrote={out_md}")
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
