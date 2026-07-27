#!/usr/bin/env python3
"""Compare adjacent V5 checkpoints using local guardrail evidence.

This is deliberately not a strength benchmark. It answers whether the latest
checkpoint looks cleaner on local gates/probes than the prior checkpoint, while
keeping Slumbot strength claims evidence-gated.
"""

from __future__ import annotations

import argparse
import json
import statistics
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


def checkpoint_iteration(obj: dict[str, Any]) -> int | None:
    value = pick(obj, "checkpoint", "iteration")
    if isinstance(value, int):
        return value
    return None


def warning_count(probe: dict[str, Any]) -> int:
    count = 0
    for check in probe.get("checks") or []:
        if isinstance(check, dict) and check.get("status") in {"WARN", "FAIL"}:
            count += 1
    for case in probe.get("cases") or []:
        if not isinstance(case, dict):
            continue
        for check in case.get("checks") or []:
            if isinstance(check, dict) and check.get("status") in {"WARN", "FAIL"}:
                count += 1
    return count


def case_key(case: dict[str, Any]) -> str:
    action = case.get("action_str")
    if action is not None and str(action).strip():
        return str(action)
    return str(case.get("description") or case.get("name") or case.get("case") or "root")


def class_rates(case: dict[str, Any]) -> dict[str, float]:
    rates = case.get("greedy_class_rates")
    if isinstance(rates, dict):
        return {
            "fold": float(rates.get("fold") or 0.0),
            "call": float(rates.get("call") or 0.0),
            "raise": float(rates.get("raise") or 0.0),
            "allin": float(rates.get("allin") or 0.0),
        }
    return {"fold": 0.0, "call": 0.0, "raise": 0.0, "allin": 0.0}


def summarize_probe(path: Path, probe: dict[str, Any]) -> dict[str, Any]:
    cases = [case for case in probe.get("cases") or [] if isinstance(case, dict)]
    rates_by_case = {case_key(case): class_rates(case) for case in cases}
    folds = [rates["fold"] for rates in rates_by_case.values()]
    calls = [rates["call"] for rates in rates_by_case.values()]
    raises = [rates["raise"] for rates in rates_by_case.values()]
    allins = [rates["allin"] for rates in rates_by_case.values()]
    return {
        "path": str(path),
        "overall": probe.get("overall"),
        "checkpoint_iteration": checkpoint_iteration(probe),
        "checkpoint_hands": pick(probe, "checkpoint", "total_hands"),
        "warning_count": warning_count(probe),
        "case_count": len(cases),
        "rates_by_case": rates_by_case,
        "means": {
            "fold": statistics.fmean(folds) if folds else None,
            "call": statistics.fmean(calls) if calls else None,
            "raise": statistics.fmean(raises) if raises else None,
            "allin": statistics.fmean(allins) if allins else None,
        },
    }


def probe_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted((run_dir / "preflop_probe_history").glob("*.json")):
        probe = load_json(path)
        iteration = checkpoint_iteration(probe)
        if iteration is None:
            continue
        records.append({"path": path, "iteration": iteration, "probe": probe})
    latest_path = run_dir / "v5_preflop_probe_latest.json"
    latest_probe = load_json(latest_path)
    latest_iteration = checkpoint_iteration(latest_probe)
    if latest_iteration is not None and all(item["iteration"] != latest_iteration for item in records):
        records.append({"path": latest_path, "iteration": latest_iteration, "probe": latest_probe})
    return sorted(records, key=lambda item: int(item["iteration"]))


def gate_records(run_dir: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("gate_*_status.json")):
        gate = load_json(path)
        target = gate_target_from(path, gate)
        if target is None:
            continue
        records.append({"path": path, "target": target, "gate": gate})
    return sorted(records, key=lambda item: int(item["target"]))


def delta(a: Any, b: Any) -> float | None:
    if a is None or b is None:
        return None
    try:
        return float(b) - float(a)
    except Exception:
        return None


def compare_cases(previous: dict[str, Any], latest: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prev_cases = previous.get("rates_by_case") or {}
    latest_cases = latest.get("rates_by_case") or {}
    for key in sorted(set(prev_cases) & set(latest_cases)):
        prev = prev_cases[key]
        cur = latest_cases[key]
        rows.append(
            {
                "case": key,
                "fold_delta": delta(prev.get("fold"), cur.get("fold")),
                "call_delta": delta(prev.get("call"), cur.get("call")),
                "raise_delta": delta(prev.get("raise"), cur.get("raise")),
                "allin_delta": delta(prev.get("allin"), cur.get("allin")),
                "previous": prev,
                "latest": cur,
            }
        )
    return rows


def classify(previous: dict[str, Any] | None, latest: dict[str, Any] | None, baseline: dict[str, Any]) -> tuple[str, str]:
    if previous is None or latest is None:
        return "INSUFFICIENT_LOCAL_HISTORY", "Need at least two preflop probe checkpoints."
    prev_warn = int(previous.get("warning_count") or 0)
    cur_warn = int(latest.get("warning_count") or 0)
    latest_pass = latest.get("overall") == "PASS"
    prev_overall = previous.get("overall")
    no_new_slumbot = (pick(baseline, "latest_slumbot", "hands") or 0) < 20_000
    if latest_pass and cur_warn < prev_warn:
        return (
            "LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN",
            f"Preflop probe improved from {prev_overall} with {prev_warn} warnings to PASS with {cur_warn} warnings; Slumbot strength remains unproven."
            if no_new_slumbot
            else f"Preflop probe improved from {prev_overall} with {prev_warn} warnings to PASS with {cur_warn} warnings.",
        )
    if latest_pass:
        return "LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN", "Latest local guardrails pass, but there is no formal Slumbot proof."
    if cur_warn > prev_warn:
        return "LOCAL_GUARDRAILS_REGRESSED", f"Warning count increased from {prev_warn} to {cur_warn}."
    return "LOCAL_GUARDRAILS_MIXED", "Local checkpoint evidence is mixed; do not infer Slumbot strength."


def build_delta(run_dir: Path) -> dict[str, Any]:
    probes = probe_records(run_dir)
    gates = gate_records(run_dir)
    baseline = load_json(run_dir / "v5_baseline_gap.json")
    health_diag = load_json(run_dir / "v5_health_warning_diagnosis.json")

    pass_gates = [item for item in gates if item["gate"].get("overall") == "PASS"]
    latest_gate = pass_gates[-1] if pass_gates else None
    previous_gate = pass_gates[-2] if len(pass_gates) >= 2 else None

    latest_probe_record = probes[-1] if probes else None
    previous_probe_record = probes[-2] if len(probes) >= 2 else None
    latest_probe = (
        summarize_probe(latest_probe_record["path"], latest_probe_record["probe"]) if latest_probe_record else None
    )
    previous_probe = (
        summarize_probe(previous_probe_record["path"], previous_probe_record["probe"]) if previous_probe_record else None
    )
    overall, recommendation = classify(previous_probe, latest_probe, baseline)
    case_deltas = compare_cases(previous_probe, latest_probe) if previous_probe and latest_probe else []

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "overall": overall,
        "recommendation": recommendation,
        "previous_gate": {
            "target": previous_gate["target"] if previous_gate else None,
            "overall": previous_gate["gate"].get("overall") if previous_gate else None,
            "checkpoint_iteration": pick(previous_gate["gate"], "checkpoint", "iteration") if previous_gate else None,
            "checkpoint_hands": pick(previous_gate["gate"], "checkpoint", "total_hands") if previous_gate else None,
            "path": str(previous_gate["path"]) if previous_gate else None,
        },
        "latest_gate": {
            "target": latest_gate["target"] if latest_gate else None,
            "overall": latest_gate["gate"].get("overall") if latest_gate else None,
            "checkpoint_iteration": pick(latest_gate["gate"], "checkpoint", "iteration") if latest_gate else None,
            "checkpoint_hands": pick(latest_gate["gate"], "checkpoint", "total_hands") if latest_gate else None,
            "path": str(latest_gate["path"]) if latest_gate else None,
        },
        "previous_probe": previous_probe,
        "latest_probe": latest_probe,
        "probe_delta": {
            "warning_count": delta(previous_probe.get("warning_count"), latest_probe.get("warning_count"))
            if previous_probe and latest_probe
            else None,
            "mean_fold": delta(pick(previous_probe, "means", "fold"), pick(latest_probe, "means", "fold"))
            if previous_probe and latest_probe
            else None,
            "mean_call": delta(pick(previous_probe, "means", "call"), pick(latest_probe, "means", "call"))
            if previous_probe and latest_probe
            else None,
            "mean_raise": delta(pick(previous_probe, "means", "raise"), pick(latest_probe, "means", "raise"))
            if previous_probe and latest_probe
            else None,
            "mean_allin": delta(pick(previous_probe, "means", "allin"), pick(latest_probe, "means", "allin"))
            if previous_probe and latest_probe
            else None,
        },
        "case_deltas": case_deltas,
        "health_warning_diagnosis": {
            "overall": health_diag.get("overall"),
            "preflop_allin_mean": pick(health_diag, "metrics", "preflop_allin_mean"),
            "preflop_call_mean": pick(health_diag, "metrics", "preflop_call_mean"),
        },
        "slumbot": {
            "hands": pick(baseline, "latest_slumbot", "hands"),
            "bb_per_100": pick(baseline, "latest_slumbot", "bb_per_100"),
            "ci_lower": pick(baseline, "latest_slumbot", "lower_bound_bb_per_100"),
            "level": pick(baseline, "latest_slumbot", "milestone_level"),
            "claim_allowed": pick(baseline, "claim_rules", "can_claim_l5"),
        },
        "claim_note": "This report is local guardrail evidence only. It cannot prove V4/L5/L6 strength without formal Slumbot CI.",
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    prev_probe = summary.get("previous_probe") or {}
    latest_probe = summary.get("latest_probe") or {}
    probe_delta = summary.get("probe_delta") or {}
    slumbot = summary.get("slumbot") or {}
    lines = [
        "# V5 Checkpoint Delta",
        "",
        f"- Checked at: `{summary['checked_at']}`",
        f"- Overall: **{summary['overall']}**",
        f"- Recommendation: {summary['recommendation']}",
        "",
        "Gate comparison:",
        "",
        f"- Previous PASS gate: target `{summary['previous_gate']['target']}`, checkpoint `{summary['previous_gate']['checkpoint_iteration']}` / `{summary['previous_gate']['checkpoint_hands']}`",
        f"- Latest PASS gate: target `{summary['latest_gate']['target']}`, checkpoint `{summary['latest_gate']['checkpoint_iteration']}` / `{summary['latest_gate']['checkpoint_hands']}`",
        "",
        "Preflop probe comparison:",
        "",
        f"- Previous: checkpoint `{prev_probe.get('checkpoint_iteration')}`, overall `{prev_probe.get('overall')}`, warnings `{prev_probe.get('warning_count')}`",
        f"- Latest: checkpoint `{latest_probe.get('checkpoint_iteration')}`, overall `{latest_probe.get('overall')}`, warnings `{latest_probe.get('warning_count')}`",
        f"- Warning delta: `{fmt(probe_delta.get('warning_count'))}`",
        f"- Mean greedy fold/call/raise/all-in deltas: `{fmt(probe_delta.get('mean_fold'))}` / `{fmt(probe_delta.get('mean_call'))}` / `{fmt(probe_delta.get('mean_raise'))}` / `{fmt(probe_delta.get('mean_allin'))}`",
        "",
        "Case deltas:",
        "",
    ]
    for row in summary.get("case_deltas") or []:
        label = row["case"] if row["case"] else "sb_open_start"
        lines.append(
            f"- `{label}`: fold `{fmt(row['fold_delta'])}`, call `{fmt(row['call_delta'])}`, raise `{fmt(row['raise_delta'])}`, all-in `{fmt(row['allin_delta'])}`"
        )
    lines.extend(
        [
            "",
            "Health / Slumbot:",
            "",
            f"- Rolling health diagnosis: `{summary['health_warning_diagnosis']['overall']}`",
            f"- Latest Slumbot: hands `{slumbot.get('hands')}`, bb/100 `{fmt(slumbot.get('bb_per_100'))}`, CI lower `{fmt(slumbot.get('ci_lower'))}`, level `{slumbot.get('level')}`",
            f"- Formal claim allowed: `{slumbot.get('claim_allowed')}`",
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
    parser = argparse.ArgumentParser(description="Compare adjacent V5 checkpoint local guardrails.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_delta(Path(args.run_dir))
    print(f"overall={summary['overall']}")
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
