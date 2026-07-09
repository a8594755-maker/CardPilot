#!/usr/bin/env python3
"""Build a V5 evidence scorecard for model-quality tracking.

This is read-only. It answers a narrower question than the run dashboard:
"Do we have evidence that the newest model is better?" Training health,
internal probes, and Slumbot CI results are kept separate so noisy or indirect
signals cannot be mistaken for a Slumbot win.
"""

from __future__ import annotations

import argparse
import glob
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_monitor import parse_log


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"_missing": True, "_path": str(path)}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"_load_error": str(exc), "_path": str(path)}
    if not isinstance(obj, dict):
        return {"_load_error": f"JSON root is {type(obj).__name__}, not object", "_path": str(path)}
    return obj


def safe_mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    if value is None or not math.isfinite(value):
        return None
    return round(value, digits)


def tail_avg(rows: list[dict[str, Any]], field: str) -> float | None:
    values = [float(row[field]) for row in rows if row.get(field) is not None]
    return safe_mean(values)


def summarize_training_trend(run_dir: Path) -> dict[str, Any]:
    rows = parse_log(run_dir / "latest_train.log")
    if not rows:
        return {"overall": "UNKNOWN", "reason": "no parsed training log rows"}

    latest = rows[-1]
    prev = rows[-200:-100]
    last = rows[-100:]
    fields = ["reward_window_100", "hands_per_second", "entropy", "approx_kl", "clip_frac"]
    comparisons: dict[str, Any] = {}
    for field in fields:
        prev_avg = tail_avg(prev, field)
        last_avg = tail_avg(last, field)
        comparisons[field] = {
            "prev100_avg": round_or_none(prev_avg),
            "last100_avg": round_or_none(last_avg),
            "delta": round_or_none(last_avg - prev_avg if prev_avg is not None and last_avg is not None else None),
        }

    health = load_json(run_dir / "health_status.json")
    health_overall = health.get("overall")
    if health_overall == "PASS":
        overall = "HEALTHY"
    elif health_overall:
        overall = str(health_overall)
    else:
        overall = "UNKNOWN"

    return {
        "overall": overall,
        "latest": {
            "iteration": latest.get("iteration"),
            "hands": latest.get("hands"),
            "reward_window_100": latest.get("reward_window_100"),
            "hands_per_second": latest.get("hands_per_second"),
            "entropy": latest.get("entropy"),
            "approx_kl": latest.get("approx_kl"),
            "clip_frac": latest.get("clip_frac"),
            "action_mix": latest.get("action_mix"),
            "preflop_action_mix": latest.get("preflop_action_mix"),
            "postflop_action_mix": latest.get("postflop_action_mix"),
        },
        "last200_comparison": comparisons,
        "note": "Self-play reward is a health/trend signal only, not a Slumbot strength score.",
    }


def summarize_gates(run_dir: Path) -> dict[str, Any]:
    gates: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("gate_*_status.json")):
        data = load_json(path)
        target = data.get("target_iteration")
        if target is None:
            continue
        gates.append(
            {
                "path": str(path),
                "target_iteration": int(target),
                "overall": data.get("overall"),
                "checkpoint_iteration": (data.get("checkpoint") or {}).get("iteration"),
                "checkpoint_hands": (data.get("checkpoint") or {}).get("total_hands"),
                "health_overall": data.get("health_overall"),
            }
        )

    passed = [gate for gate in gates if gate.get("overall") == "PASS"]
    pending = [gate for gate in gates if gate.get("overall") == "PENDING"]
    return {
        "latest_pass": max(passed, key=lambda x: x["target_iteration"]) if passed else None,
        "next_pending": min(pending, key=lambda x: x["target_iteration"]) if pending else None,
        "tail": sorted(gates, key=lambda x: x["target_iteration"])[-8:],
    }


def latest_candidate_rows(probe: dict[str, Any]) -> list[dict[str, Any]]:
    results = [row for row in probe.get("results") or [] if isinstance(row, dict)]
    latest = [row for row in results if row.get("candidate_kind") == "checkpoint_latest"]
    if latest:
        return latest
    if not results:
        return []
    max_hands = max(int(row.get("candidate_hands") or 0) for row in results)
    return [row for row in results if int(row.get("candidate_hands") or 0) == max_hands]


def summarize_probe(path: Path) -> dict[str, Any] | None:
    probe = load_json(path)
    if probe.get("_missing") or probe.get("_load_error"):
        return None

    latest_rows = latest_candidate_rows(probe)
    latest_scores = [float(row.get("bb100") or 0.0) for row in latest_rows]
    latest_lcbs = [float(row.get("bb100") or 0.0) - float(row.get("ci95_bb100") or 0.0) for row in latest_rows]
    trends = probe.get("trends") or {}
    latest_is_best = [
        bool(trend.get("latest_is_best"))
        for trend in trends.values()
        if isinstance(trend, dict) and "latest_is_best" in trend
    ]
    positive_steps = [
        (int(trend.get("positive_adjacent_steps") or 0), int(trend.get("total_adjacent_steps") or 0))
        for trend in trends.values()
        if isinstance(trend, dict)
    ]
    total_positive = sum(item[0] for item in positive_steps)
    total_steps = sum(item[1] for item in positive_steps)

    all_latest_best = bool(latest_is_best) and all(latest_is_best)
    any_latest_best = any(latest_is_best)
    if all_latest_best:
        verdict = "LATEST_BEST_INTERNAL"
    elif any_latest_best:
        verdict = "MIXED_INTERNAL"
    elif latest_rows:
        verdict = "REGRESSION_RISK_INTERNAL"
    else:
        verdict = "UNKNOWN"

    return {
        "path": str(path),
        "checked_at": probe.get("checked_at"),
        "checkpoint_iteration": (probe.get("checkpoint") or {}).get("iteration"),
        "checkpoint_hands": (probe.get("checkpoint") or {}).get("total_hands"),
        "hands_per_match": probe.get("hands_per_match"),
        "opponents": probe.get("opponents"),
        "latest_rows": [
            {
                "candidate": row.get("candidate"),
                "opponent": row.get("opponent"),
                "bb100": row.get("bb100"),
                "ci95_bb100": row.get("ci95_bb100"),
                "lower_bound_bb100": float(row.get("bb100") or 0.0) - float(row.get("ci95_bb100") or 0.0),
                "hands": row.get("hands"),
                "wins": row.get("wins"),
                "losses": row.get("losses"),
                "draws": row.get("draws"),
            }
            for row in latest_rows
        ],
        "mean_latest_bb100": round_or_none(safe_mean(latest_scores), 3),
        "mean_latest_lower_bound_bb100": round_or_none(safe_mean(latest_lcbs), 3),
        "latest_is_best_opponents": sum(1 for item in latest_is_best if item),
        "opponent_count": len(latest_is_best),
        "positive_adjacent_steps": total_positive,
        "total_adjacent_steps": total_steps,
        "verdict": verdict,
    }


def summarize_internal_probes(run_dir: Path) -> dict[str, Any]:
    probe_paths = [
        path
        for path in sorted(run_dir.glob("internal_strength_probe_*.json"))
        if "smoke" not in path.stem.lower()
    ]
    probes = [
        item
        for item in (summarize_probe(path) for path in probe_paths)
        if item is not None
    ]
    probes = [probe for probe in probes if probe.get("checkpoint_iteration") is not None]
    probes.sort(key=lambda item: (int(item.get("checkpoint_iteration") or 0), int(item.get("checkpoint_hands") or 0)))

    if not probes:
        return {
            "overall": "NO_INTERNAL_PROBE",
            "latest": None,
            "previous": None,
            "latest_vs_previous_delta_mean_bb100": None,
            "note": "No internal probe evidence exists yet.",
        }

    latest = probes[-1]
    previous = probes[-2] if len(probes) >= 2 else None
    delta = None
    if previous and latest.get("mean_latest_bb100") is not None and previous.get("mean_latest_bb100") is not None:
        delta = float(latest["mean_latest_bb100"]) - float(previous["mean_latest_bb100"])

    if previous is None:
        overall = "ONE_PROBE_ONLY"
    elif delta is not None and delta > 0 and latest.get("verdict") != "REGRESSION_RISK_INTERNAL":
        overall = "IMPROVING_INTERNAL_TREND"
    elif delta is not None and delta < 0:
        overall = "WORSE_THAN_PREVIOUS_INTERNAL"
    else:
        overall = str(latest.get("verdict") or "MIXED_INTERNAL")

    return {
        "overall": overall,
        "latest": latest,
        "previous": previous,
        "latest_vs_previous_delta_mean_bb100": round_or_none(delta, 3),
        "history_tail": probes[-8:],
        "note": "Internal probes are for regression detection only. They do not prove Slumbot strength.",
    }


def ci_level(ci: dict[str, Any]) -> str:
    return str(ci.get("milestone_level") or "UNKNOWN")


def slumbot_artifact_policy(path_text: str) -> str:
    path_text = path_text.lower()
    if "preflop-callguard" in path_text or "callguard" in path_text:
        return "preflop-callguard"
    if "greedy-guarded" in path_text:
        return "greedy-guarded"
    if "preflop-mixed" in path_text or "preflop_mixed" in path_text:
        return "preflop-mixed"
    if "policy_sample" in path_text or "_sample" in path_text:
        return "sample"
    if "guarded" in path_text:
        return "guarded"
    return "greedy"


def slumbot_artifact_target_m(path_text: str) -> int | None:
    matches = re.findall(r"(?<!\d)(\d+)m(?![a-z0-9])", path_text.lower())
    if not matches:
        return None
    return int(matches[-1])


def slumbot_artifact_kind(item: dict[str, Any]) -> str:
    """Classify Slumbot CI artifacts by evidentiary strength.

    Selector sweeps and policy-ablation runs are useful diagnostics, but they
    must not lift the run's official Slumbot level. Promotion/baseline claims
    start at the project's 20.4k baseline scale; formal L5/L6 claims start at
    100k.
    """
    path_text = str(item.get("path") or "").lower()
    diagnostic_markers = (
        "callguard",
        "guarded",
        "greedy-guarded",
        "preflop-mixed",
        "preflop_mixed",
        "policy_sample",
        "_sample",
        "selector",
    )
    if any(marker in path_text for marker in diagnostic_markers):
        return "diagnostic"

    hands = int(item.get("hands") or 0)
    if hands < 5_000:
        return "diagnostic"
    if hands < 20_400:
        return "smoke"
    if hands < 100_000:
        return "promotion"
    return "formal"


def summarize_slumbot_ci(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    run_id = run_dir.name
    paths = [Path(path) for path in glob.glob(str(output_dir / f"bench_v55_*{run_id}*_ci_summary.json"))]
    items: list[dict[str, Any]] = []
    for path in sorted(set(paths)):
        ci = load_json(path)
        if ci.get("_missing") or ci.get("_load_error"):
            continue
        try:
            modified_ts = path.stat().st_mtime
            modified_at = datetime.fromtimestamp(modified_ts, timezone.utc).isoformat()
        except OSError:
            modified_ts = 0.0
            modified_at = None
        item = {
            "path": str(path),
            "modified_at": modified_at,
            "modified_ts": modified_ts,
            "hands": int(ci.get("hands") or 0),
            "bb_per_100": float(ci.get("bb_per_100") or 0.0),
            "lower_bound_bb_per_100": float(ci.get("lower_bound_bb_per_100") or 0.0),
            "upper_bound_bb_per_100": ci.get("upper_bound_bb_per_100"),
            "milestone_level": ci_level(ci),
            "l5_formal_win": bool(ci.get("l5_formal_win")),
            "l6_near_paper_target": bool(ci.get("l6_near_paper_target")),
            "baseline_delta_bb_per_100": ci.get("baseline_delta_bb_per_100"),
            "input_files": ci.get("input_files"),
        }
        item["policy_mode"] = slumbot_artifact_policy(item["path"])
        item["target_m"] = slumbot_artifact_target_m(item["path"])
        item["kind"] = slumbot_artifact_kind(item)
        item["diagnostic"] = item["kind"] == "diagnostic"
        items.append(item)

    if not items:
        return {
            "overall": "NO_SLUMBOT_SCORE",
            "latest": None,
            "best_by_lower_bound": None,
            "latest_diagnostic": None,
            "best_diagnostic_by_lower_bound": None,
            "formal_l5_proven": False,
            "formal_l6_proven": False,
            "score_trend": "UNKNOWN_NO_SLUMBOT_DATA",
            "note": "No Slumbot CI artifact exists for this V5 run yet.",
        }

    items.sort(key=lambda item: (float(item.get("modified_ts") or 0.0), item["path"]))
    evidence_items = [item for item in items if not item.get("diagnostic")]
    diagnostic_items = [item for item in items if item.get("diagnostic")]
    latest_diag_by_policy: dict[str, dict[str, Any]] = {}
    for item in diagnostic_items:
        latest_diag_by_policy[str(item.get("policy_mode") or "unknown")] = item
    diagnostic_pairs: list[dict[str, Any]] = []
    grouped_by_target: dict[int, list[dict[str, Any]]] = {}
    for item in diagnostic_items:
        target_m = item.get("target_m")
        if target_m is None:
            continue
        grouped_by_target.setdefault(int(target_m), []).append(item)
    for target_m, target_items in sorted(grouped_by_target.items()):
        by_policy: dict[str, dict[str, Any]] = {}
        for item in sorted(target_items, key=lambda row: (float(row.get("modified_ts") or 0.0), row["path"])):
            by_policy[str(item.get("policy_mode") or "unknown")] = item
        greedy = by_policy.get("greedy")
        callguard = by_policy.get("preflop-callguard")
        if not greedy or not callguard:
            continue
        diagnostic_pairs.append(
            {
                "target_m": target_m,
                "greedy": greedy,
                "preflop_callguard": callguard,
                "delta_callguard_vs_greedy_bb_per_100": round_or_none(
                    float(callguard["bb_per_100"]) - float(greedy["bb_per_100"]),
                    3,
                ),
                "combined_hands": int(greedy["hands"]) + int(callguard["hands"]),
            }
        )

    latest = evidence_items[-1] if evidence_items else None
    latest_diagnostic = diagnostic_items[-1] if diagnostic_items else None
    best_lcb = (
        max(evidence_items, key=lambda item: (float(item["lower_bound_bb_per_100"]), float(item["bb_per_100"])))
        if evidence_items
        else None
    )
    best_diag_lcb = (
        max(diagnostic_items, key=lambda item: (float(item["lower_bound_bb_per_100"]), float(item["bb_per_100"])))
        if diagnostic_items
        else None
    )
    formal_l5 = any(bool(item["l5_formal_win"]) for item in evidence_items)
    formal_l6 = any(bool(item["l6_near_paper_target"]) for item in evidence_items)

    if not evidence_items:
        score_trend = "DIAGNOSTIC_ONLY_NO_CLAIM_EVIDENCE"
    elif len(evidence_items) < 2:
        score_trend = "ONE_SLUMBOT_EVIDENCE_RESULT_ONLY"
    else:
        previous = evidence_items[-2]
        if latest["bb_per_100"] > previous["bb_per_100"]:
            score_trend = "LATEST_POINT_ESTIMATE_UP"
        elif latest["bb_per_100"] < previous["bb_per_100"]:
            score_trend = "LATEST_POINT_ESTIMATE_DOWN"
        else:
            score_trend = "LATEST_POINT_ESTIMATE_FLAT"

    return {
        "overall": ci_level(best_lcb) if best_lcb else "DIAGNOSTIC_ONLY",
        "latest": latest,
        "best_by_lower_bound": best_lcb,
        "latest_diagnostic": latest_diagnostic,
        "latest_diagnostic_by_policy": latest_diag_by_policy,
        "best_diagnostic_by_lower_bound": best_diag_lcb,
        "diagnostic_pairs": diagnostic_pairs[-8:],
        "formal_l5_proven": formal_l5,
        "formal_l6_proven": formal_l6,
        "score_trend": score_trend,
        "history_tail": evidence_items[-8:],
        "diagnostic_history_tail": diagnostic_items[-8:],
        "all_history_tail": items[-8:],
        "note": "Diagnostic Slumbot CI artifacts are excluded from official level/trend claims.",
    }


def build_scorecard(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    manifest = load_json(run_dir / "run_manifest.json")
    training = summarize_training_trend(run_dir)
    gates = summarize_gates(run_dir)
    internal = summarize_internal_probes(run_dir)
    slumbot = summarize_slumbot_ci(run_dir, output_dir)
    preflop_probe = load_json(run_dir / "v5_preflop_probe_latest.json")
    if not preflop_probe.get("_missing"):
        preflop_probe["path"] = str(run_dir / "v5_preflop_probe_latest.json")

    blockers: list[str] = []
    if training.get("overall") != "HEALTHY":
        blockers.append(f"training health is {training.get('overall')}")
    preflop_overall = preflop_probe.get("overall")
    if preflop_overall in {"WARN", "FAIL"}:
        blockers.append(f"preflop guardrail is {preflop_overall}")
    if slumbot.get("overall") == "NO_SLUMBOT_SCORE":
        blockers.append("no Slumbot CI score exists for this run")
    if not slumbot.get("formal_l5_proven"):
        blockers.append("formal L5 not proven: need 100k+ Slumbot hands, bb/100 > 0, CI lower > 0")
    if not slumbot.get("formal_l6_proven"):
        blockers.append("L6 not proven: need near +11.1 bb/100 with formal Slumbot evidence")

    if slumbot.get("formal_l6_proven"):
        quality_status = "L6_PROVEN"
    elif slumbot.get("formal_l5_proven"):
        quality_status = "L5_PROVEN"
    elif preflop_overall in {"WARN", "FAIL"}:
        quality_status = "PREFLOP_GUARDRAIL_WARN"
    elif slumbot.get("latest"):
        quality_status = "SLUMBOT_CANDIDATE_ONLY"
    elif internal.get("overall") in {"IMPROVING_INTERNAL_TREND", "LATEST_BEST_INTERNAL"}:
        quality_status = "INTERNAL_ONLY_IMPROVING"
    else:
        quality_status = "UNPROVEN"

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "run_id": manifest.get("run_id") or run_dir.name,
        "quality_status": quality_status,
        "training": training,
        "gates": gates,
        "internal_probes": internal,
        "slumbot_ci": slumbot,
        "preflop_probe": preflop_probe,
        "is_latest_training_better": {
            "answer": "UNKNOWN_WITHOUT_SLUMBOT" if not slumbot.get("latest") else slumbot.get("score_trend"),
            "reason": "Internal/self-play signals are not enough to claim real Slumbot improvement.",
        },
        "blockers": blockers,
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    training = summary.get("training") or {}
    latest_train = training.get("latest") or {}
    internal = summary.get("internal_probes") or {}
    latest_internal = internal.get("latest") or {}
    slumbot = summary.get("slumbot_ci") or {}
    latest_slumbot = slumbot.get("latest") or {}
    latest_diagnostic = slumbot.get("latest_diagnostic") or {}
    preflop_probe = summary.get("preflop_probe") or {}
    gates = summary.get("gates") or {}

    lines = [
        "# V5 Scorecard",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Run: `{summary.get('run_id')}`",
        f"- Quality status: **{summary.get('quality_status')}**",
        f"- Is latest training better?: `{(summary.get('is_latest_training_better') or {}).get('answer')}`",
        "",
        "## Training Health",
        "",
        f"- Overall: `{training.get('overall')}`",
        f"- Live iteration: `{latest_train.get('iteration')}`",
        f"- Live hands: `{latest_train.get('hands')}`",
        f"- Latest rew100: `{latest_train.get('reward_window_100')}`",
        f"- Latest entropy: `{latest_train.get('entropy')}`",
        f"- Latest h/s: `{latest_train.get('hands_per_second')}`",
        "",
        "Last 100 vs previous 100:",
        "",
    ]
    for key, row in (training.get("last200_comparison") or {}).items():
        lines.append(
            f"- `{key}`: prev `{row.get('prev100_avg')}`, last `{row.get('last100_avg')}`, delta `{row.get('delta')}`"
        )

    lines.extend(
        [
            "",
            "## Gates",
            "",
            f"- Latest PASS: `{((gates.get('latest_pass') or {}).get('target_iteration'))}`",
            f"- Next pending: `{((gates.get('next_pending') or {}).get('target_iteration'))}`",
            "",
            "## Internal Probe",
            "",
            f"- Overall: `{internal.get('overall')}`",
            f"- Latest checkpoint iteration: `{latest_internal.get('checkpoint_iteration')}`",
            f"- Latest checkpoint hands: `{latest_internal.get('checkpoint_hands')}`",
            f"- Mean latest bb/100: `{latest_internal.get('mean_latest_bb100')}`",
            f"- Mean latest lower bound bb/100: `{latest_internal.get('mean_latest_lower_bound_bb100')}`",
            f"- Latest-is-best opponents: `{latest_internal.get('latest_is_best_opponents')}/{latest_internal.get('opponent_count')}`",
            f"- Delta vs previous probe mean bb/100: `{internal.get('latest_vs_previous_delta_mean_bb100')}`",
            "",
            "## Slumbot",
            "",
            f"- Overall: `{slumbot.get('overall')}`",
            f"- Latest hands: `{latest_slumbot.get('hands')}`",
            f"- Latest bb/100: `{latest_slumbot.get('bb_per_100')}`",
            f"- Latest 95% CI lower: `{latest_slumbot.get('lower_bound_bb_per_100')}`",
            f"- Latest evidence kind: `{latest_slumbot.get('kind')}`",
            f"- Latest diagnostic hands: `{latest_diagnostic.get('hands')}`",
            f"- Latest diagnostic bb/100: `{latest_diagnostic.get('bb_per_100')}`",
            f"- Formal L5 proven: `{slumbot.get('formal_l5_proven')}`",
            f"- Formal L6 proven: `{slumbot.get('formal_l6_proven')}`",
            "",
            "## Preflop Guardrail",
            "",
            f"- Overall: `{preflop_probe.get('overall')}`",
            f"- Probe JSON: `{preflop_probe.get('path')}`",
        ]
    )
    for warning in preflop_probe.get("warnings") or []:
        lines.append(f"- Warning: `{warning.get('case')}` `{warning.get('name')}` - {warning.get('detail')}")
    lines.extend(["", "## Blockers", ""])
    for blocker in summary.get("blockers") or []:
        lines.append(f"- {blocker}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a V5 model-quality scorecard.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_scorecard(Path(args.run_dir), Path(args.output_dir))
    text = json.dumps(summary, indent=2, sort_keys=True)
    print(text)
    if args.out_json:
        out_json = Path(args.out_json)
        out_json.parent.mkdir(parents=True, exist_ok=True)
        out_json.write_text(text + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
