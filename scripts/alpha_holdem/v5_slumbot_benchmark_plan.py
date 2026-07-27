#!/usr/bin/env python3
"""Plan gated V5 Slumbot benchmarks without calling Slumbot.

This script is intentionally read-only with respect to Slumbot: it checks the
candidate checkpoint/run metadata and emits the exact benchmark command only
when the checkpoint is eligible for the requested benchmark stage.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


STAGES: dict[str, dict[str, Any]] = {
    "quick5k": {
        "hands_per_session": 1250,
        "sessions": 4,
        "min_training_hands": 50_000_000,
        "purpose": "API/loader smoke only; not a promotion or win claim.",
    },
    "promotion20k": {
        "hands_per_session": 1700,
        "sessions": 12,
        "min_training_hands": 250_000_000,
        "purpose": "20k promotion screen; cannot prove L5/L6 by itself.",
    },
    "formal100k": {
        "hands_per_session": 5000,
        "sessions": 20,
        "min_training_hands": 250_000_000,
        "purpose": "Formal L5/L6-eligible Slumbot benchmark if CI gates pass.",
    },
}

EXPECTED_METADATA: dict[str, Any] = {
    "version": "v5.zero",
    "env_version": "v55",
    "obs_version": "v55",
    "action_space_version": "9slot_v5",
}


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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_terminal_endpoint_evidence(
    *,
    checkpoint_path: Path,
    checkpoint: dict[str, Any],
    manifest: dict[str, Any],
    endpoint_status_path: Path,
    protocol_status_path: Path,
) -> tuple[bool, str, dict[str, Any]]:
    """Fail closed on a stopped run unless exact endpoint/protocol evidence passes."""
    endpoint = load_json(endpoint_status_path)
    protocol = load_json(protocol_status_path)
    errors: list[str] = []
    if endpoint.get("_missing") or endpoint.get("_load_error"):
        errors.append("endpoint status missing or unreadable")
    if protocol.get("_missing") or protocol.get("_load_error"):
        errors.append("protocol status missing or unreadable")
    if manifest.get("status") != "finished":
        errors.append(f"manifest status {manifest.get('status')!r} is not finished")
    if endpoint.get("overall") != "PASS" or endpoint.get("state") != "ARM_ENDPOINT_FROZEN":
        errors.append("endpoint is not ARM_ENDPOINT_FROZEN/PASS")
    if protocol.get("overall") != "PASS" or protocol.get("state") != "ARM_FINISHED_GUARDS_PASS":
        errors.append("protocol is not ARM_FINISHED_GUARDS_PASS/PASS")
    try:
        if Path(str(endpoint.get("checkpoint_path", ""))).resolve() != checkpoint_path.resolve():
            errors.append("endpoint checkpoint path mismatch")
    except (OSError, RuntimeError):
        errors.append("endpoint checkpoint path invalid")
    actual_sha = sha256_file(checkpoint_path) if checkpoint_path.is_file() else ""
    if endpoint.get("checkpoint_sha256") != actual_sha:
        errors.append("endpoint checkpoint SHA256 mismatch")
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
    if protocol.get("arm") != endpoint.get("arm"):
        errors.append("endpoint/protocol arm mismatch")
    payload = {
        "endpoint_status_path": str(endpoint_status_path),
        "protocol_status_path": str(protocol_status_path),
        "checkpoint_sha256": actual_sha,
        "iteration": expected_iter,
        "training_hands": expected_hands,
        "manifest_status": manifest.get("status"),
        "endpoint_state": endpoint.get("state"),
        "protocol_state": protocol.get("state"),
        "errors": errors,
    }
    return not errors, "terminal endpoint/protocol identity PASS" if not errors else "; ".join(errors), payload


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


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except Exception:
        return None


def ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def sanitize_tag(value: str) -> str:
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_.-")
    return tag or "v5_slumbot"


def build_default_tag(stage: str, run_id: str, iteration: Any, total_hands: int) -> str:
    hand_m = total_hands // 1_000_000
    parts = ["v5", run_id or "unknown_run"]
    if iteration is not None:
        parts.append(f"iter{iteration}")
    if total_hands > 0:
        parts.append(f"{hand_m}M")
    parts.append(stage)
    return sanitize_tag("_".join(str(p) for p in parts))


def benchmark_command(
    checkpoint_path: Path,
    tag: str,
    hands_per_session: int,
    sessions: int,
    output_dir: Path,
    run_dir: Path,
    *,
    policy_mode: str = "greedy",
    temperature: float = 1.0,
    guarded_allin_max_spr: float = 2.0,
    guarded_allin_min_prob: float = 0.65,
    callguard_min_prob: float = 0.20,
    callguard_ratio: float = 0.65,
    callguard_include_open: bool = False,
) -> str:
    lines = [
        ".\\scripts\\alpha_holdem\\bench_v55_slumbot.ps1 `",
        f"  -ModelPath {ps_quote(str(checkpoint_path))} `",
        f"  -Tag {ps_quote(tag)} `",
        f"  -HandsPerSession {hands_per_session} `",
        f"  -Sessions {sessions} `",
        f"  -OutputDir {ps_quote(str(output_dir))} `",
        f"  -RunDir {ps_quote(str(run_dir))} `",
        f"  -PolicyMode {ps_quote(policy_mode)} `",
        f"  -Temperature {temperature:g} `",
        f"  -GuardedAllinMaxSpr {guarded_allin_max_spr:g} `",
        f"  -GuardedAllinMinProb {guarded_allin_min_prob:g} `",
        f"  -CallguardMinProb {callguard_min_prob:g} `",
        f"  -CallguardRatio {callguard_ratio:g}",
    ]
    if callguard_include_open:
        lines[-1] += " `"
        lines.append("  -CallguardIncludeOpen")
    return "\n".join(lines)


def benchmark_policy_summary(args: argparse.Namespace) -> dict[str, Any]:
    return {
        "policy_mode": getattr(args, "policy_mode", "greedy"),
        "temperature": float(getattr(args, "temperature", 1.0)),
        "guarded_allin_max_spr": float(getattr(args, "guarded_allin_max_spr", 2.0)),
        "guarded_allin_min_prob": float(getattr(args, "guarded_allin_min_prob", 0.65)),
        "callguard_min_prob": float(getattr(args, "callguard_min_prob", 0.20)),
        "callguard_ratio": float(getattr(args, "callguard_ratio", 0.65)),
        "callguard_include_open": bool(getattr(args, "callguard_include_open", False)),
    }


def output_artifacts(output_dir: Path, tag: str) -> dict[str, Any]:
    pattern = str(output_dir / f"bench_v55_{tag}_part*")
    return {
        "session_glob": pattern,
        "hands_glob": str(output_dir / f"bench_v55_{tag}_part*_hands.jsonl"),
        "dump_glob": str(output_dir / f"bench_v55_{tag}_part*_dump.jsonl"),
        "summary_txt": str(output_dir / f"bench_v55_{tag}_summary.txt"),
        "ci_json": str(output_dir / f"bench_v55_{tag}_ci_summary.json"),
        "promotion_json": str(output_dir / f"bench_v55_{tag}_promotion_gate.json"),
        "promotion_md": str(output_dir / f"bench_v55_{tag}_promotion_gate.md"),
        "dump_analysis": str(output_dir / f"bench_v55_{tag}_dump_analysis.txt"),
        "loss_report_json": str(output_dir / f"bench_v55_{tag}_loss_report.json"),
        "loss_report_md": str(output_dir / f"bench_v55_{tag}_loss_report.md"),
        "artifact_audit_json": str(output_dir / f"bench_v55_{tag}_artifact_audit.json"),
        "artifact_audit_md": str(output_dir / f"bench_v55_{tag}_artifact_audit.md"),
        "hand_review_json": str(output_dir / f"bench_v55_{tag}_hand_review.json"),
        "hand_review_md": str(output_dir / f"bench_v55_{tag}_hand_review.md"),
        "selector_replay_json": str(output_dir / f"bench_v55_{tag}_selector_replay.json"),
        "selector_replay_md": str(output_dir / f"bench_v55_{tag}_selector_replay.md"),
    }


def existing_outputs(output_dir: Path, tag: str) -> list[str]:
    patterns = [
        str(output_dir / f"bench_v55_{tag}_part*"),
        str(output_dir / f"bench_v55_{tag}_summary.txt"),
        str(output_dir / f"bench_v55_{tag}_ci_summary.*"),
        str(output_dir / f"bench_v55_{tag}_promotion_gate.*"),
        str(output_dir / f"bench_v55_{tag}_dump_analysis.txt"),
        str(output_dir / f"bench_v55_{tag}_loss_report.*"),
        str(output_dir / f"bench_v55_{tag}_artifact_audit.*"),
        str(output_dir / f"bench_v55_{tag}_hand_review.*"),
        str(output_dir / f"bench_v55_{tag}_selector_replay.*"),
    ]
    found: list[str] = []
    for pattern in patterns:
        found.extend(glob.glob(pattern))
    return sorted(set(found))


def promotion_gate_paths(output_dir: Path, run_id: str, explicit_path: str = "") -> list[Path]:
    if explicit_path:
        return [Path(explicit_path)]
    patterns = [
        str(output_dir / f"bench_v55_*{run_id}*promotion20k*_promotion_gate.json"),
        str(output_dir / f"bench_v55_*{run_id}*promotion*_promotion_gate.json"),
    ]
    found: list[Path] = []
    for pattern in patterns:
        found.extend(Path(path) for path in glob.glob(pattern))
    return sorted(set(found), key=lambda path: path.stat().st_mtime if path.exists() else 0.0, reverse=True)


def evaluate_promotion20k_prerequisite(
    args: argparse.Namespace,
    output_dir: Path,
    run_id: str,
    checkpoint: dict[str, Any],
) -> dict[str, Any] | None:
    """Return the formal100k promotion prerequisite decision.

    Formal 100k is expensive and is the only L5/L6-eligible stage. By default
    it must follow a strong 20k promotion gate for the same run, matching the
    project promotion rules.
    """
    if args.stage != "formal100k":
        return None
    if args.no_require_promotion20k:
        return {
            "required": False,
            "status": "WARN",
            "detail": "promotion20k prerequisite disabled by --no-require-promotion20k",
            "path": None,
            "promotion_gate": None,
        }

    paths = promotion_gate_paths(output_dir, run_id, args.promotion_gate_json)
    if not paths:
        return {
            "required": True,
            "status": "FAIL",
            "detail": "no promotion20k promotion_gate.json found for this run",
            "path": None,
            "promotion_gate": None,
        }

    inspected: list[dict[str, Any]] = []
    for path in paths:
        data = load_json(path)
        if data.get("_missing"):
            inspected.append({"path": str(path), "status": "FAIL", "detail": "missing"})
            continue
        if data.get("_load_error"):
            inspected.append({"path": str(path), "status": "FAIL", "detail": data.get("_load_error")})
            continue
        decisions = data.get("decisions") or {}
        slumbot = data.get("slumbot") or {}
        gate_checkpoint = data.get("checkpoint") or {}
        strong = bool(decisions.get("promotion_20k_strong"))
        candidate = bool(decisions.get("promotion_20k_candidate"))
        identity_matches = all(
            gate_checkpoint.get(key) == checkpoint.get(key)
            for key in ("run_id", "iteration", "total_hands")
        )
        inspected.append(
            {
                "path": str(path),
                "status": "PASS" if strong and identity_matches else "FAIL",
                "promotion_20k_strong": strong,
                "promotion_20k_candidate": candidate,
                "checkpoint_identity_matches": identity_matches,
                "checkpoint": {
                    "run_id": gate_checkpoint.get("run_id"),
                    "iteration": gate_checkpoint.get("iteration"),
                    "total_hands": gate_checkpoint.get("total_hands"),
                },
                "hands": slumbot.get("hands"),
                "bb_per_100": slumbot.get("bb_per_100"),
                "lower_bound_bb_per_100": slumbot.get("lower_bound_bb_per_100"),
                "milestone_level": slumbot.get("milestone_level"),
            }
        )
        if strong and identity_matches:
            return {
                "required": True,
                "status": "PASS",
                "detail": f"promotion20k strong gate passed: {path}",
                "path": str(path),
                "promotion_gate": inspected[-1],
                "inspected_tail": inspected[:5],
            }

    return {
        "required": True,
        "status": "FAIL",
        "detail": (
            "promotion20k gate exists but no promotion_20k_strong=True result "
            "for the exact formal checkpoint identity was found"
        ),
        "path": str(paths[0]) if paths else None,
        "promotion_gate": inspected[0] if inspected else None,
        "inspected_tail": inspected[:5],
    }


def evaluate_quality_gate(
    args: argparse.Namespace,
    run_dir: Path,
    checkpoint: dict[str, Any],
    checkpoint_ready: bool,
) -> dict[str, Any]:
    """Decide whether the current checkpoint is eligible for expensive Slumbot stages.

    The 20k/100k stages should not launch purely because training-hands crossed a
    threshold. They are expensive evidence gates, so the candidate must also
    have a fresh preflop guardrail result that is not warning/failing.
    """
    required = args.stage in {"promotion20k", "formal100k"} and not args.no_require_quality_gate
    if args.no_require_quality_gate:
        return {
            "required": False,
            "status": "WARN",
            "detail": "quality gate disabled by --no-require-quality-gate",
            "scorecard_path": str(run_dir / "v5_scorecard.json"),
            "quality_status": None,
            "preflop_overall": None,
            "preflop_checkpoint_hands": None,
            "checkpoint_hands": checkpoint.get("total_hands") if checkpoint_ready else None,
            "latest_diagnostic": None,
        }

    scorecard_path = run_dir / "v5_scorecard.json"
    scorecard = load_json(scorecard_path)
    if scorecard.get("_missing") or scorecard.get("_load_error"):
        return {
            "required": required,
            "status": "FAIL" if required else "WARN",
            "detail": f"scorecard unavailable: {scorecard.get('_load_error') or 'missing'}",
            "scorecard_path": str(scorecard_path),
            "quality_status": None,
            "preflop_overall": None,
            "preflop_checkpoint_hands": None,
            "checkpoint_hands": checkpoint.get("total_hands") if checkpoint_ready else None,
            "latest_diagnostic": None,
        }

    quality_status = scorecard.get("quality_status")
    preflop = scorecard.get("preflop_probe") or {}
    preflop_overall = preflop.get("overall")
    preflop_checkpoint = preflop.get("checkpoint") or {}
    preflop_hands = preflop_checkpoint.get("total_hands")
    checkpoint_hands = checkpoint.get("total_hands") if checkpoint_ready else None
    slumbot = scorecard.get("slumbot_ci") or {}
    latest_diagnostic = slumbot.get("latest_diagnostic")

    problems: list[str] = []
    if preflop_overall in {"WARN", "FAIL"}:
        problems.append(f"preflop guardrail is {preflop_overall}")
    if checkpoint_hands is not None and preflop_hands is not None and int(preflop_hands) != int(checkpoint_hands):
        problems.append(f"preflop probe is stale: probe hands {preflop_hands:,} != checkpoint hands {checkpoint_hands:,}")

    if problems:
        status = "FAIL" if required else "PASS"
        detail = "; ".join(problems) if required else "optional quality warning for smoke benchmark: " + "; ".join(problems)
    else:
        status = "PASS"
        detail = f"quality_status={quality_status}; preflop={preflop_overall}"

    return {
        "required": required,
        "status": status,
        "detail": detail,
        "scorecard_path": str(scorecard_path),
        "quality_status": quality_status,
        "preflop_overall": preflop_overall,
        "preflop_checkpoint_hands": preflop_hands,
        "checkpoint_hands": checkpoint_hands,
        "latest_diagnostic": latest_diagnostic,
    }


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    stage = STAGES[args.stage]
    run_dir = Path(args.run_dir)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else run_dir / "latest.pt"
    output_dir = Path(args.output_dir)
    manifest = load_json(run_dir / "run_manifest.json")
    health = load_json(run_dir / "health_status.json")
    checkpoint = load_checkpoint(checkpoint_path)
    checkpoint_ready = not checkpoint.get("_missing") and not checkpoint.get("_load_error")
    terminal_evidence: dict[str, Any] | None = None

    checks: list[dict[str, str]] = []
    sentinel_path = Path(getattr(args, "active_window_sentinel", "reports/v5_active_window.json"))
    sentinel = load_json(sentinel_path)
    active_window_block = bool(
        not sentinel.get("_missing")
        and not sentinel.get("_load_error")
        and sentinel.get("active") is True
        and sentinel.get("terminal") is not True
    )
    if active_window_block:
        add_check(
            checks,
            "active_window_sentinel",
            "FAIL",
            f"active window {sentinel.get('design_id')!r}/{sentinel.get('state')!r}; Slumbot planning and command emission are forbidden",
        )
    elif sentinel.get("_load_error"):
        add_check(checks, "active_window_sentinel", "FAIL", "active-window sentinel is unreadable")
    else:
        add_check(checks, "active_window_sentinel", "PASS", "no nonterminal active-window block")
    if run_dir.exists():
        add_check(checks, "run_dir", "PASS", f"exists: {run_dir}")
    else:
        add_check(checks, "run_dir", "FAIL", f"missing: {run_dir}")

    if checkpoint.get("_missing"):
        add_check(checks, "checkpoint_load", "FAIL", f"missing: {checkpoint_path}")
    elif checkpoint.get("_load_error"):
        add_check(checks, "checkpoint_load", "FAIL", str(checkpoint["_load_error"]))
    else:
        add_check(checks, "checkpoint_load", "PASS", f"loaded {checkpoint_path}")

    for key, expected in EXPECTED_METADATA.items():
        actual = checkpoint.get(key)
        if not checkpoint_ready:
            add_check(checks, key, "FAIL", "checkpoint unavailable")
        elif actual == expected:
            add_check(checks, key, "PASS", f"{key}={actual}")
        else:
            add_check(checks, key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if not checkpoint_ready:
        add_check(checks, "starting_stack_bb", "FAIL", "checkpoint unavailable")
        add_check(checks, "actual_hand_accounting", "FAIL", "checkpoint unavailable")
        add_check(checks, "fresh_from_zero_lineage", "FAIL", "checkpoint unavailable")
    else:
        stack = checkpoint.get("starting_stack_bb")
        if approx_equal(stack, 200.0):
            add_check(checks, "starting_stack_bb", "PASS", f"starting_stack_bb={stack}")
        else:
            add_check(checks, "starting_stack_bb", "FAIL", f"starting_stack_bb={stack!r}, expected 200.0")

        if checkpoint.get("actual_hand_accounting") is True:
            add_check(checks, "actual_hand_accounting", "PASS", "actual_hand_accounting=True")
        else:
            add_check(
                checks,
                "actual_hand_accounting",
                "FAIL",
                f"actual_hand_accounting={checkpoint.get('actual_hand_accounting')!r}, expected True",
            )

        if fresh_from_zero_lineage(checkpoint):
            add_check(checks, "fresh_from_zero_lineage", "PASS", "fresh_from_zero_lineage=True")
        else:
            add_check(
                checks,
                "fresh_from_zero_lineage",
                "FAIL",
                f"fresh_from_zero_lineage={checkpoint.get('fresh_from_zero_lineage')!r}; resume={checkpoint.get('resume')!r}",
            )

    health_overall = health.get("overall")
    terminal_endpoint_status_json = getattr(args, "terminal_endpoint_status_json", "")
    terminal_protocol_status_json = getattr(args, "terminal_protocol_status_json", "")
    terminal_paths_supplied = bool(terminal_endpoint_status_json or terminal_protocol_status_json)
    if terminal_paths_supplied:
        if not terminal_endpoint_status_json or not terminal_protocol_status_json or not checkpoint_ready:
            add_check(checks, "terminal_endpoint_health", "FAIL", "both terminal status paths and a readable checkpoint are required")
        else:
            terminal_ok, terminal_detail, terminal_evidence = validate_terminal_endpoint_evidence(
                checkpoint_path=checkpoint_path,
                checkpoint=checkpoint,
                manifest=manifest,
                endpoint_status_path=Path(terminal_endpoint_status_json),
                protocol_status_path=Path(terminal_protocol_status_json),
            )
            add_check(checks, "terminal_endpoint_health", "PASS" if terminal_ok else "FAIL", terminal_detail)
    else:
        if health.get("_missing"):
            add_check(checks, "health_status", "FAIL", f"missing: {run_dir / 'health_status.json'}")
        elif health.get("_load_error"):
            add_check(checks, "health_status", "FAIL", str(health["_load_error"]))
        elif health_overall in {"PASS", "WARN"}:
            add_check(checks, "health_status", "PASS" if health_overall == "PASS" else "WARN", f"health overall {health_overall}")
        else:
            add_check(checks, "health_status", "FAIL", f"health overall {health_overall!r}")

        if not args.no_health_age_check and not health.get("_missing") and not health.get("_load_error"):
            checked_at = parse_time(health.get("checked_at"))
            if checked_at is None:
                add_check(checks, "health_age", "WARN", "health checked_at missing or invalid")
            else:
                age_seconds = (now - checked_at.astimezone(timezone.utc)).total_seconds()
                if age_seconds <= args.max_health_age_seconds:
                    add_check(checks, "health_age", "PASS", f"health age {age_seconds:.0f}s <= {args.max_health_age_seconds}s")
                else:
                    add_check(checks, "health_age", "FAIL", f"health age {age_seconds:.0f}s > {args.max_health_age_seconds}s")

    checkpoint_hands = int(checkpoint.get("total_hands") or 0) if checkpoint_ready else 0
    manifest_hands = int(manifest.get("total_hands") or 0) if not manifest.get("_missing") and not manifest.get("_load_error") else 0
    total_hands = checkpoint_hands or manifest_hands
    min_training_hands = args.min_training_hands if args.min_training_hands is not None else int(stage["min_training_hands"])
    if checkpoint_hands >= min_training_hands:
        add_check(checks, "training_hands", "PASS", f"checkpoint hands {checkpoint_hands:,} >= {min_training_hands:,}")
    elif args.allow_early and checkpoint_hands > 0:
        add_check(
            checks,
            "training_hands",
            "WARN",
            f"checkpoint hands {checkpoint_hands:,} < {min_training_hands:,}; early benchmark override enabled",
        )
    else:
        add_check(checks, "training_hands", "FAIL", f"checkpoint hands {checkpoint_hands:,} < {min_training_hands:,}")

    hands_per_session = args.hands_per_session or int(stage["hands_per_session"])
    sessions = args.sessions or int(stage["sessions"])
    planned_hands = hands_per_session * sessions
    if args.stage == "formal100k" and planned_hands < 100_000:
        add_check(checks, "planned_hands", "FAIL", f"planned hands {planned_hands:,} < formal gate 100,000")
    elif args.stage == "promotion20k" and planned_hands < 20_000:
        add_check(checks, "planned_hands", "FAIL", f"planned hands {planned_hands:,} < promotion gate 20,000")
    else:
        add_check(checks, "planned_hands", "PASS", f"planned hands {planned_hands:,}")

    run_id = str(checkpoint.get("run_id") or manifest.get("run_id") or run_dir.name)
    iteration = checkpoint.get("iteration") if checkpoint_ready else manifest.get("iteration")
    promotion20k_prerequisite = evaluate_promotion20k_prerequisite(args, output_dir, run_id, checkpoint)
    if promotion20k_prerequisite is not None:
        add_check(
            checks,
            "promotion20k_prerequisite",
            str(promotion20k_prerequisite["status"]),
            str(promotion20k_prerequisite["detail"]),
        )

    quality_gate = evaluate_quality_gate(args, run_dir, checkpoint, checkpoint_ready)
    if args.stage == "formal100k" and promotion20k_prerequisite and promotion20k_prerequisite.get("status") == "PASS":
        gate_data = load_json(Path(str(promotion20k_prerequisite.get("path") or "")))
        gate_decisions = gate_data.get("decisions") or {}
        gate_quality_clean = bool(gate_decisions.get("preflop_guardrail_clean"))
        if gate_quality_clean:
            quality_gate = {
                "required": True,
                "status": "PASS",
                "detail": "exact-checkpoint strong promotion20k gate recorded a clean preflop guardrail",
                "source": "promotion20k_prerequisite",
                "promotion_gate_path": promotion20k_prerequisite.get("path"),
            }
    add_check(checks, "quality_gate", str(quality_gate["status"]), str(quality_gate["detail"]))

    tag = sanitize_tag(args.tag) if args.tag else build_default_tag(args.stage, run_id, iteration, total_hands)
    collisions = existing_outputs(output_dir, tag)
    if collisions and args.allow_existing_output:
        add_check(checks, "output_collision", "WARN", f"{len(collisions)} existing output files matched tag; overwrite risk accepted")
    elif collisions:
        add_check(checks, "output_collision", "FAIL", f"{len(collisions)} existing output files matched tag; choose another tag")
    else:
        add_check(checks, "output_collision", "PASS", f"no existing outputs for tag {tag}")

    hard_fail = any(check["status"] == "FAIL" for check in checks)
    warn = any(check["status"] == "WARN" for check in checks)
    if hard_fail:
        overall = "BLOCKED"
    elif warn:
        overall = "READY_WITH_WARNINGS"
    else:
        overall = "READY"

    policy = benchmark_policy_summary(args)
    command = "" if active_window_block else benchmark_command(
        checkpoint_path=checkpoint_path,
        tag=tag,
        hands_per_session=hands_per_session,
        sessions=sessions,
        output_dir=output_dir,
        run_dir=run_dir,
        policy_mode=policy["policy_mode"],
        temperature=policy["temperature"],
        guarded_allin_max_spr=policy["guarded_allin_max_spr"],
        guarded_allin_min_prob=policy["guarded_allin_min_prob"],
        callguard_min_prob=policy["callguard_min_prob"],
        callguard_ratio=policy["callguard_ratio"],
        callguard_include_open=policy["callguard_include_open"],
    )

    return {
        "checked_at": now.isoformat(),
        "overall": overall,
        "stage": args.stage,
        "stage_purpose": stage["purpose"],
        "run_dir": str(run_dir),
        "checkpoint_path": str(checkpoint_path),
        "output_dir": str(output_dir),
        "tag": tag,
        "hands_per_session": hands_per_session,
        "sessions": sessions,
        "planned_hands": planned_hands,
        "policy": policy,
        "min_training_hands": min_training_hands,
        "checks": checks,
        "checkpoint": {
            "run_id": checkpoint.get("run_id") if checkpoint_ready else None,
            "iteration": checkpoint.get("iteration") if checkpoint_ready else None,
            "total_hands": checkpoint_hands if checkpoint_ready else None,
            "version": checkpoint.get("version") if checkpoint_ready else None,
            "env_version": checkpoint.get("env_version") if checkpoint_ready else None,
            "obs_version": checkpoint.get("obs_version") if checkpoint_ready else None,
            "action_space_version": checkpoint.get("action_space_version") if checkpoint_ready else None,
            "starting_stack_bb": checkpoint.get("starting_stack_bb") if checkpoint_ready else None,
            "actual_hand_accounting": checkpoint.get("actual_hand_accounting") if checkpoint_ready else None,
            "fresh_from_zero_lineage": fresh_from_zero_lineage(checkpoint) if checkpoint_ready else None,
        },
        "health_overall": health_overall,
        "terminal_endpoint_evidence": terminal_evidence,
        "active_window_sentinel": {
            "path": str(sentinel_path),
            "active_block": active_window_block,
            "design_id": sentinel.get("design_id"),
            "state": sentinel.get("state"),
        },
        "manifest_total_hands": manifest_hands,
        "quality_gate": quality_gate,
        "promotion20k_prerequisite": promotion20k_prerequisite,
        "command": command,
        "artifacts": output_artifacts(output_dir, tag),
        "notes": [
            "This planner does not call Slumbot or run the benchmark.",
            "20k promotion benchmarks cannot prove L5/L6.",
            "L5/L6 claims still require the promotion gate over saved per-hand artifacts.",
        ],
    }


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    lines = [
        "# V5 Slumbot Benchmark Plan",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Stage: `{summary['stage']}`",
        f"- Purpose: {summary['stage_purpose']}",
        f"- Planned hands: `{summary['planned_hands']:,}`",
        f"- Policy mode: `{summary.get('policy', {}).get('policy_mode', 'greedy')}`",
        f"- Policy temperature: `{summary.get('policy', {}).get('temperature', 1.0)}`",
        f"- Min training hands: `{summary['min_training_hands']:,}`",
        f"- Checkpoint: `{summary['checkpoint_path']}`",
        f"- Tag: `{summary['tag']}`",
        "",
        "Checks:",
        "",
    ]
    for check in summary["checks"]:
        lines.append(f"- {check['status']}: `{check['name']}` - {check['detail']}")

    promotion_prereq = summary.get("promotion20k_prerequisite")
    quality_gate = summary.get("quality_gate")
    if quality_gate:
        lines += [
            "",
            "Quality gate:",
            "",
            f"- Required: `{quality_gate.get('required')}`",
            f"- Status: `{quality_gate.get('status')}`",
            f"- Detail: {quality_gate.get('detail')}",
            f"- Scorecard: `{quality_gate.get('scorecard_path')}`",
            f"- Quality status: `{quality_gate.get('quality_status')}`",
            f"- Preflop overall: `{quality_gate.get('preflop_overall')}`",
        ]

    if promotion_prereq:
        lines += [
            "",
            "Formal prerequisite:",
            "",
            f"- Required: `{promotion_prereq.get('required')}`",
            f"- Status: `{promotion_prereq.get('status')}`",
            f"- Detail: {promotion_prereq.get('detail')}",
            f"- Gate JSON: `{promotion_prereq.get('path')}`",
        ]

    lines += [
        "",
        "Command:",
        "",
        "```powershell",
        summary["command"],
        "```",
    ]
    artifacts = summary.get("artifacts") if isinstance(summary.get("artifacts"), dict) else {}
    if artifacts:
        lines += [
            "",
            "Artifacts:",
            "",
            f"- CI JSON: `{artifacts.get('ci_json')}`",
            f"- Promotion gate JSON: `{artifacts.get('promotion_json')}`",
            f"- Loss report JSON: `{artifacts.get('loss_report_json')}`",
            f"- Artifact audit JSON: `{artifacts.get('artifact_audit_json')}`",
            f"- Hand review JSON: `{artifacts.get('hand_review_json')}`",
            f"- Hand review MD: `{artifacts.get('hand_review_md')}`",
        ]
    lines += [
        "",
        "Notes:",
        "",
    ]
    for note in summary["notes"]:
        lines.append(f"- {note}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="", help="Defaults to <run-dir>/latest.pt.")
    parser.add_argument("--stage", choices=sorted(STAGES), default="promotion20k")
    parser.add_argument("--tag", default="")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--sessions", type=int, default=0)
    parser.add_argument("--hands-per-session", type=int, default=0)
    parser.add_argument("--min-training-hands", type=int, default=None)
    parser.add_argument("--allow-early", action="store_true")
    parser.add_argument("--allow-existing-output", action="store_true")
    parser.add_argument("--promotion-gate-json", default="", help="For formal100k, explicit promotion20k promotion_gate.json prerequisite.")
    parser.add_argument("--no-require-promotion20k", action="store_true", help="Allow formal100k planning without a strong promotion20k gate.")
    parser.add_argument("--no-require-quality-gate", action="store_true", help="Allow promotion/formal planning even when scorecard quality gate is WARN/FAIL.")
    parser.add_argument("--max-health-age-seconds", type=int, default=600)
    parser.add_argument("--no-health-age-check", action="store_true")
    parser.add_argument("--terminal-endpoint-status-json", default="", help="Fail-closed frozen endpoint PASS evidence for a finished run.")
    parser.add_argument("--terminal-protocol-status-json", default="", help="Matching finished protocol PASS evidence for a finished run.")
    parser.add_argument("--active-window-sentinel", default="reports/v5_active_window.json")
    parser.add_argument(
        "--policy-mode",
        choices=["greedy", "greedy-guarded", "preflop-callguard", "sample", "guarded", "preflop-mixed"],
        default="greedy",
    )
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--guarded-allin-max-spr", type=float, default=2.0)
    parser.add_argument("--guarded-allin-min-prob", type=float, default=0.65)
    parser.add_argument("--callguard-min-prob", type=float, default=0.20)
    parser.add_argument("--callguard-ratio", type=float, default=0.65)
    parser.add_argument("--callguard-include-open", action="store_true")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = evaluate(args)
    print(f"overall={summary['overall']}")
    print(f"stage={summary['stage']}")
    print(f"planned_hands={summary['planned_hands']}")
    print(f"min_training_hands={summary['min_training_hands']}")
    print(f"tag={summary['tag']}")
    if summary["command"]:
        print("command:")
        print(summary["command"])
    else:
        print("command_emission=BLOCKED")

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

    return 0 if summary["overall"] in {"READY", "READY_WITH_WARNINGS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
