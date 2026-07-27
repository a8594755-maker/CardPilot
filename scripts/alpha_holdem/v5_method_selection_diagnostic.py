#!/usr/bin/env python3
"""Read-only pre-500M evidence for choosing EXP-005 versus isolated EXP-006A.

This diagnostic freezes quantitative selection rules before the 500M Slumbot
result.  It does not register, authorize, or launch a behavior change.  Internal
probe results are retained only as context because their 200-hand intervals are
too wide for method selection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v5.method_selection.pre500m.v1"
KL_TARGET_MAX = 0.03
KL_MEDIAN_SUPPORT_MIN = 0.03
KL_OVER_TARGET_FRACTION_MIN = 0.50
KL_GT_010_FRACTION_MIN = 0.10
CLIPFRAC_MEAN_SUPPORT_MIN = 0.25
GATE_ROWS_MIN = 6
PREFLOP_WARNING_RANGE_MIN = 4
PREFLOP_STATUS_SWITCHES_MIN = 2


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise TypeError(f"expected JSON object: {path}")
    return value


def exact_positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        return None
    return value


def parse_train_line(line: str) -> dict[str, float | int] | None:
    iteration_match = re.match(r"^\[(\d+)\]", line)
    if not iteration_match:
        return None

    def number(name: str) -> float | None:
        match = re.search(rf"(?:^|\s){re.escape(name)}=([+-]?(?:\d+(?:\.\d*)?|\.\d+))", line)
        return float(match.group(1)) if match else None

    hands_match = re.search(r"(?:^|\s)hands=([0-9,]+)", line)
    values = {
        "value_loss": number("vloss"),
        "entropy": number("ent"),
        "kl": number("kl"),
        "clipfrac": number("clipfrac"),
    }
    if hands_match is None or any(value is None for value in values.values()):
        return None
    return {
        "iteration": int(iteration_match.group(1)),
        "hands": int(hands_match.group(1).replace(",", "")),
        **{key: float(value) for key, value in values.items()},
    }


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def metric_summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "median": 0.0, "p95": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": float(statistics.fmean(values)),
        "median": float(statistics.median(values)),
        "p95": percentile(values, 0.95),
        "min": float(min(values)),
        "max": float(max(values)),
    }


def load_train_rows(run_dir: Path, tail: int) -> tuple[list[dict[str, Any]], Path]:
    path = run_dir / "latest_train.log"
    rows = [row for line in path.read_text(encoding="utf-8").splitlines() if (row := parse_train_line(line))]
    if tail > 0:
        rows = rows[-tail:]
    return rows, path


def exact_gate_review(run_dir: Path, target: int, review_path: Path) -> dict[str, Any] | None:
    gate_path = run_dir / f"gate_{target}_status.json"
    if not gate_path.exists():
        return None
    gate = load_json(gate_path)
    review = load_json(review_path)
    gate_target = exact_positive_int(gate.get("target_iteration"))
    checkpoint_iteration = exact_positive_int(gate.get("checkpoint_iteration"))
    review_target = exact_positive_int(review.get("target_iteration"))
    review_checkpoint = exact_positive_int(review.get("gate_checkpoint_iteration"))
    if (
        gate.get("overall") != "PASS"
        or review.get("gate_overall") != "PASS"
        or gate_target != target
        or checkpoint_iteration != target
        or review_target != target
        or review_checkpoint != target
    ):
        return None
    preflop = review.get("preflop_probe") if isinstance(review.get("preflop_probe"), dict) else {}
    internal = review.get("internal_probe") if isinstance(review.get("internal_probe"), dict) else {}
    warning_count = preflop.get("warning_count")
    if isinstance(warning_count, bool) or not isinstance(warning_count, int) or warning_count < 0:
        return None
    return {
        "target_iteration": target,
        "checkpoint_hands": gate.get("checkpoint_hands"),
        "preflop_overall": preflop.get("overall"),
        "preflop_warning_count": warning_count,
        "internal_verdict": internal.get("latest_l6_verdict"),
        "internal_delta_mean_bb100": internal.get("latest_l6_delta_mean_bb100"),
        "internal_delta_lower_bb100": internal.get("latest_l6_delta_lower_bb100"),
        "review_path": str(review_path.resolve()),
        "review_sha256": sha256_file(review_path),
        "gate_path": str(gate_path.resolve()),
        "gate_sha256": sha256_file(gate_path),
    }


def load_gate_rows(run_dir: Path, gate_tail: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in run_dir.glob("v5_post_gate_review_*.json"):
        match = re.search(r"_(\d+)$", path.stem)
        if not match:
            continue
        target = int(match.group(1))
        row = exact_gate_review(run_dir, target, path)
        if row is not None:
            rows.append(row)
    rows.sort(key=lambda item: item["target_iteration"])
    return rows[-gate_tail:] if gate_tail > 0 else rows


def ppo_diagnostic(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("no parseable training rows")
    kl = [float(row["kl"]) for row in rows]
    clip = [float(row["clipfrac"]) for row in rows]
    entropy = [float(row["entropy"]) for row in rows]
    value_loss = [float(row["value_loss"]) for row in rows]
    fraction_over_target = sum(value > KL_TARGET_MAX for value in kl) / len(kl)
    fraction_over_010 = sum(value > 0.10 for value in kl) / len(kl)
    metrics = {
        "rows": len(rows),
        "first_iteration": rows[0]["iteration"],
        "last_iteration": rows[-1]["iteration"],
        "first_hands": rows[0]["hands"],
        "last_hands": rows[-1]["hands"],
        "kl": metric_summary(kl),
        "kl_gt_003_fraction": fraction_over_target,
        "kl_gt_010_fraction": fraction_over_010,
        "clipfrac": metric_summary(clip),
        "entropy": metric_summary(entropy),
        "value_loss": metric_summary(value_loss),
    }
    checks = [
        {
            "name": "median_kl",
            "pass": metrics["kl"]["median"] > KL_MEDIAN_SUPPORT_MIN,
            "detail": f"median={metrics['kl']['median']:.6f} > {KL_MEDIAN_SUPPORT_MIN:.6f}",
        },
        {
            "name": "kl_over_target_fraction",
            "pass": fraction_over_target >= KL_OVER_TARGET_FRACTION_MIN,
            "detail": f"fraction={fraction_over_target:.6f} >= {KL_OVER_TARGET_FRACTION_MIN:.6f}",
        },
        {
            "name": "high_kl_or_clipping",
            "pass": fraction_over_010 >= KL_GT_010_FRACTION_MIN
            or metrics["clipfrac"]["mean"] >= CLIPFRAC_MEAN_SUPPORT_MIN,
            "detail": (
                f"kl>0.10 fraction={fraction_over_010:.6f} (min {KL_GT_010_FRACTION_MIN:.6f}) OR "
                f"clip mean={metrics['clipfrac']['mean']:.6f} (min {CLIPFRAC_MEAN_SUPPORT_MIN:.6f})"
            ),
        },
    ]
    return {
        "metrics": metrics,
        "checks": checks,
        "exp006a_isolated_kl_support": all(check["pass"] for check in checks),
        "interpretation": "direct PPO update-size evidence; does not prove Slumbot strength",
    }


def gate_instability_diagnostic(gates: list[dict[str, Any]], opponent_assignment: str) -> dict[str, Any]:
    warning_counts = [int(row["preflop_warning_count"]) for row in gates]
    statuses = [str(row.get("preflop_overall")) for row in gates]
    switches = sum(left != right for left, right in zip(statuses, statuses[1:]))
    warning_range = max(warning_counts) - min(warning_counts) if warning_counts else 0
    internal_counts = Counter(str(row.get("internal_verdict")) for row in gates)
    checks = [
        {
            "name": "per_iteration_assignment",
            "pass": opponent_assignment == "per-iteration",
            "detail": f"opponent_assignment={opponent_assignment}",
        },
        {
            "name": "enough_exact_gates",
            "pass": len(gates) >= GATE_ROWS_MIN,
            "detail": f"exact gates={len(gates)} >= {GATE_ROWS_MIN}",
        },
        {
            "name": "preflop_warning_range",
            "pass": warning_range >= PREFLOP_WARNING_RANGE_MIN,
            "detail": f"range={warning_range} >= {PREFLOP_WARNING_RANGE_MIN}",
        },
        {
            "name": "preflop_status_switches",
            "pass": switches >= PREFLOP_STATUS_SWITCHES_MIN,
            "detail": f"switches={switches} >= {PREFLOP_STATUS_SWITCHES_MIN}",
        },
    ]
    return {
        "exact_gate_rows": gates,
        "warning_counts": warning_counts,
        "warning_range": warning_range,
        "preflop_status_switches": switches,
        "internal_verdict_counts": dict(internal_counts),
        "checks": checks,
        "exp005_group_assignment_support": all(check["pass"] for check in checks),
        "interpretation": (
            "structural M3 support plus local oscillation; not causal proof and not a strength signal"
        ),
    }


def latest_official_evidence(run_dir: Path) -> dict[str, Any]:
    path = run_dir / "v5_trend_ledger.json"
    if not path.exists():
        return {"status": "MISSING", "path": str(path)}
    trend = load_json(path)
    latest = trend.get("latest_official") if isinstance(trend.get("latest_official"), dict) else {}
    direction = trend.get("direction") if isinstance(trend.get("direction"), dict) else {}
    return {
        "status": "AVAILABLE",
        "path": str(path.resolve()),
        "sha256": sha256_file(path),
        "hands": latest.get("hands"),
        "bb100": latest.get("bb_per_100"),
        "ci_lower": latest.get("lower_bound_bb_per_100"),
        "ci_upper": latest.get("upper_bound_bb_per_100"),
        "level": latest.get("milestone_level"),
        "direction": direction.get("answer"),
        "claim_allowed": direction.get("claim_allowed"),
    }


def build_diagnostic(run_dir: Path, *, tail: int = 1_000, gate_tail: int = 10) -> dict[str, Any]:
    manifest_path = run_dir / "run_manifest.json"
    manifest = load_json(manifest_path)
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    opponent_assignment = str(config.get("opponent_assignment") or "")
    train_rows, train_log_path = load_train_rows(run_dir, tail)
    gate_rows = load_gate_rows(run_dir, gate_tail)
    ppo = ppo_diagnostic(train_rows)
    instability = gate_instability_diagnostic(gate_rows, opponent_assignment)
    exp006 = bool(ppo["exp006a_isolated_kl_support"])
    exp005 = bool(instability["exp005_group_assignment_support"])
    if exp006 and exp005:
        priority = "EXP006A_DIRECT_SIGNAL_PRIORITY_EXP005_STRUCTURAL_SECONDARY"
    elif exp006:
        priority = "EXP006A_DIRECT_SIGNAL_PRIORITY"
    elif exp005:
        priority = "EXP005_STRUCTURAL_PRIORITY"
    else:
        priority = "NO_METHOD_PRIORITY_PROVEN"
    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": utc_now(),
        "run_dir": str(run_dir.resolve()),
        "run_id": manifest.get("run_id") or config.get("run_id"),
        "claim_scope": "pre500m_method_selection_diagnostic_only_not_behavior_authorization_not_strength",
        "selection_status": "WAIT_FOR_500M_OFFICIAL_PROMOTION_RESULT",
        "current_priority": priority,
        "thresholds_frozen_before_500m_result": {
            "kl_target_max": KL_TARGET_MAX,
            "kl_median_support_min": KL_MEDIAN_SUPPORT_MIN,
            "kl_over_target_fraction_min": KL_OVER_TARGET_FRACTION_MIN,
            "kl_gt_010_fraction_min": KL_GT_010_FRACTION_MIN,
            "clipfrac_mean_support_min": CLIPFRAC_MEAN_SUPPORT_MIN,
            "gate_rows_min": GATE_ROWS_MIN,
            "preflop_warning_range_min": PREFLOP_WARNING_RANGE_MIN,
            "preflop_status_switches_min": PREFLOP_STATUS_SWITCHES_MIN,
        },
        "inputs": {
            "manifest_path": str(manifest_path.resolve()),
            "manifest_sha256": sha256_file(manifest_path),
            "train_log_path": str(train_log_path.resolve()),
            "train_log_sha256": sha256_file(train_log_path),
            "train_tail_rows": tail,
            "gate_tail_rows": gate_tail,
        },
        "ppo_stability": ppo,
        "opponent_distribution_instability": instability,
        "latest_official_slumbot": latest_official_evidence(run_dir),
        "decision_rule": {
            "if_500m_promotion_strong": "launch formal100k; no method cutover",
            "if_not_strong_and_exp006a_support": (
                "separately register isolated KL early-stop only; do not bundle entropy schedule/value rescale"
            ),
            "if_not_strong_and_only_exp005_support": "separately register group opponent assignment",
            "if_both_support": (
                "current pre-500M priority is isolated EXP-006A because KL is a direct measured fault; "
                "retain EXP-005 as the next structural candidate and reassess after the isolated window"
            ),
            "no_cutover_before_500m": True,
        },
        "recommendation": (
            "Preserve the current trainer through the 500M promotion gate. This diagnostic may rank a future "
            "experiment only after a non-strong official promotion result and full loss review."
        ),
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    ppo = result["ppo_stability"]["metrics"]
    instability = result["opponent_distribution_instability"]
    lines = [
        "# V5 Pre-500M Method-Selection Diagnostic",
        "",
        f"- Checked at: `{result['checked_at']}`",
        f"- Current priority: `{result['current_priority']}`",
        f"- Selection status: `{result['selection_status']}`",
        "",
        "This is read-only decision support. It does not authorize a behavior change and does not prove strength.",
        "",
        "## PPO Stability (EXP-006A)",
        "",
        f"- Rows: `{ppo['rows']}` (`{ppo['first_iteration']}..{ppo['last_iteration']}`)",
        f"- KL mean / median / p95 / max: `{ppo['kl']['mean']:.4f}` / `{ppo['kl']['median']:.4f}` / `{ppo['kl']['p95']:.4f}` / `{ppo['kl']['max']:.4f}`",
        f"- KL > 0.03 fraction: `{ppo['kl_gt_003_fraction']:.3f}`",
        f"- KL > 0.10 fraction: `{ppo['kl_gt_010_fraction']:.3f}`",
        f"- Clipfrac mean / p95: `{ppo['clipfrac']['mean']:.3f}` / `{ppo['clipfrac']['p95']:.3f}`",
        f"- Isolated EXP-006A support: `{result['ppo_stability']['exp006a_isolated_kl_support']}`",
        "",
        "## Opponent-Distribution Instability (EXP-005)",
        "",
        f"- Exact gate warning counts: `{instability['warning_counts']}`",
        f"- Warning range: `{instability['warning_range']}`",
        f"- PASS/WARN switches: `{instability['preflop_status_switches']}`",
        f"- EXP-005 structural support: `{instability['exp005_group_assignment_support']}`",
        "",
        "## Decision Boundary",
        "",
        "- No method cutover before the official 500M promotion result.",
        "- A strong promotion launches formal100k, not a method experiment.",
        "- A non-strong result requires the full loss review before exactly one separately registered cutover.",
        "- When both signals persist, isolated KL early-stop is ranked first because KL is directly measured; group assignment remains the structural follow-up candidate.",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only pre-500M EXP-005 vs EXP-006A diagnostic")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--tail", type=int, default=1_000)
    parser.add_argument("--gate-tail", type=int, default=10)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()
    result = build_diagnostic(Path(args.run_dir), tail=args.tail, gate_tail=args.gate_tail)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    print(rendered)
    if args.out_json:
        path = Path(args.out_json)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite fixed pre-500M diagnostic: {path}")
        path.write_text(rendered + "\n", encoding="utf-8")
    if args.out_md:
        path = Path(args.out_md)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            raise FileExistsError(f"refusing to overwrite fixed pre-500M diagnostic: {path}")
        write_markdown(result, path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
