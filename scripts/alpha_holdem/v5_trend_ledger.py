#!/usr/bin/env python3
"""Build a read-only trend ledger for V5 model quality.

The ledger answers the operational question: "is this checkpoint better than
the prior evidence?" It deliberately keeps three evidence tiers separate:

1. training health, which can catch collapse but cannot prove strength;
2. internal fixed-opponent probes, which can catch regressions but are noisy;
3. Slumbot confidence intervals, which are the only promotion-quality score.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

from v5_run_dashboard import build_summary
from v5_scorecard import build_scorecard, summarize_probe


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def round_or_none(value: Any, digits: int = 3) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def load_internal_history(run_dir: Path) -> list[dict[str, Any]]:
    probes: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("internal_strength_probe_*.json")):
        if "smoke" in path.stem.lower():
            continue
        summary = summarize_probe(path)
        if not summary or summary.get("checkpoint_iteration") is None:
            continue
        probes.append(summary)

    probes.sort(key=lambda item: (int(item.get("checkpoint_iteration") or 0), int(item.get("checkpoint_hands") or 0)))
    rows: list[dict[str, Any]] = []
    previous_mean: float | None = None
    previous_lower: float | None = None
    for item in probes:
        mean = round_or_none(item.get("mean_latest_bb100"))
        lower = round_or_none(item.get("mean_latest_lower_bound_bb100"))
        rows.append(
            {
                "checkpoint_iteration": item.get("checkpoint_iteration"),
                "checkpoint_hands": item.get("checkpoint_hands"),
                "hands_per_match": item.get("hands_per_match"),
                "mean_latest_bb100": mean,
                "mean_latest_lower_bound_bb100": lower,
                "delta_mean_vs_previous": round_or_none(mean - previous_mean) if mean is not None and previous_mean is not None else None,
                "delta_lower_vs_previous": round_or_none(lower - previous_lower) if lower is not None and previous_lower is not None else None,
                "latest_is_best_opponents": item.get("latest_is_best_opponents"),
                "opponent_count": item.get("opponent_count"),
                "positive_adjacent_steps": item.get("positive_adjacent_steps"),
                "total_adjacent_steps": item.get("total_adjacent_steps"),
                "verdict": item.get("verdict"),
                "path": item.get("path"),
            }
        )
        previous_mean = mean
        previous_lower = lower
    return rows


def slumbot_history_from_scorecard(scorecard: dict[str, Any]) -> list[dict[str, Any]]:
    slumbot = scorecard.get("slumbot_ci") or {}
    history = slumbot.get("history_tail") or []
    latest = slumbot.get("latest")
    if not history and isinstance(latest, dict):
        history = [latest]
    rows: list[dict[str, Any]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        rows.append(
            {
                "hands": item.get("hands"),
                "bb_per_100": round_or_none(item.get("bb_per_100")),
                "lower_bound_bb_per_100": round_or_none(item.get("lower_bound_bb_per_100")),
                "upper_bound_bb_per_100": round_or_none(item.get("upper_bound_bb_per_100")),
                "milestone_level": item.get("milestone_level"),
                "l5_formal_win": item.get("l5_formal_win"),
                "l6_near_paper_target": item.get("l6_near_paper_target"),
                "path": item.get("path"),
            }
        )
    return rows


def load_parent_trend_ledger(run_dir: Path) -> tuple[dict[str, Any] | None, Path | None]:
    manifest = read_json_object(run_dir / "run_manifest.json")
    if not manifest:
        return None, None

    parent_text = manifest.get("lineage_parent_checkpoint")
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    if not parent_text:
        parent_text = config.get("resume")
    if not parent_text:
        return None, None

    parent_checkpoint = Path(str(parent_text))
    parent_dir = parent_checkpoint.parent
    if not parent_dir or parent_dir == run_dir:
        return None, None

    parent_trend_path = parent_dir / "v5_trend_ledger.json"
    parent_trend = read_json_object(parent_trend_path)
    return parent_trend, parent_trend_path if parent_trend else parent_trend_path


def clean_inherited_slumbot_rows(parent_trend: dict[str, Any] | None) -> list[dict[str, Any]]:
    rows = parent_trend.get("slumbot_history") if isinstance(parent_trend, dict) else []
    if not isinstance(rows, list):
        return []
    clean_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        clean_rows.append(
            {
                "hands": row.get("hands"),
                "bb_per_100": row.get("bb_per_100"),
                "lower_bound_bb_per_100": row.get("lower_bound_bb_per_100"),
                "upper_bound_bb_per_100": row.get("upper_bound_bb_per_100"),
                "milestone_level": row.get("milestone_level"),
                "l5_formal_win": row.get("l5_formal_win"),
                "l6_near_paper_target": row.get("l6_near_paper_target"),
                "path": row.get("path"),
                "source": "lineage_parent_trend",
            }
        )
    return clean_rows


def slumbot_row_key(row: dict[str, Any]) -> tuple[Any, ...]:
    path = row.get("path")
    if path:
        return ("path", str(path))
    return (
        "score",
        row.get("hands"),
        row.get("bb_per_100"),
        row.get("lower_bound_bb_per_100"),
        row.get("upper_bound_bb_per_100"),
    )


def merge_slumbot_history(parent_rows: list[dict[str, Any]], current_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for row in [*parent_rows, *current_rows]:
        key = slumbot_row_key(row)
        if key in seen:
            continue
        seen.add(key)
        merged.append(row)
    return merged


def read_json_object(path: Path) -> dict[str, Any] | None:
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return obj if isinstance(obj, dict) else None


def resolve_artifact_path(path_text: Any, output_dir: Path) -> Path | None:
    if not path_text:
        return None
    path = Path(str(path_text))
    if path.is_absolute():
        return path
    return path


def hand_review_path_from_ci(ci_path: Path | None) -> Path | None:
    if ci_path is None:
        return None
    text = str(ci_path)
    suffix = "_ci_summary.json"
    if not text.endswith(suffix):
        return None
    return Path(text[: -len(suffix)] + "_hand_review.json")


def sibling_artifact_from_ci(ci_path: Path | None, suffix: str) -> Path | None:
    if ci_path is None:
        return None
    text = str(ci_path)
    ci_suffix = "_ci_summary.json"
    if not text.endswith(ci_suffix):
        return None
    return Path(text[: -len(ci_suffix)] + suffix)


def loss_bucket_value(rows: Any, key: str, field: str = "bb_per_100") -> float | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("key") == key:
            return round_or_none(row.get(field))
    return None


def loss_bucket_row(rows: Any, key: str) -> dict[str, Any] | None:
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("key") == key:
            return row
    return None


def compact_loss_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
    if not row:
        return None
    return {
        "key": row.get("key"),
        "hands": row.get("hands"),
        "chips": row.get("chips"),
        "bb_per_100": round_or_none(row.get("bb_per_100")),
    }


def top_loss_rows(rows: Any, limit: int = 5) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    selected = [row for row in rows if isinstance(row, dict)]
    selected.sort(key=lambda row: (float(row.get("chips") or 0), -int(row.get("hands") or 0)))
    return [item for item in (compact_loss_row(row) for row in selected[:limit]) if item]


def first_hypothesis_areas(review: dict[str, Any] | None, limit: int = 3) -> list[str]:
    if not review:
        return []
    areas: list[str] = []
    for item in review.get("loss_hypotheses") or []:
        if not isinstance(item, dict):
            continue
        area = item.get("area")
        if area:
            areas.append(str(area))
        if len(areas) >= limit:
            break
    return areas


def official_loss_row_from_ci(
    *,
    slumbot_row: dict[str, Any],
    output_dir: Path,
    previous: dict[str, Any] | None,
) -> dict[str, Any]:
    ci_path = resolve_artifact_path(slumbot_row.get("path"), output_dir)
    loss_path = sibling_artifact_from_ci(ci_path, "_loss_report.json")
    review_path = hand_review_path_from_ci(ci_path)
    audit_path = sibling_artifact_from_ci(ci_path, "_artifact_audit.json")
    loss = read_json_object(loss_path) if loss_path and loss_path.exists() else None
    review = read_json_object(review_path) if review_path and review_path.exists() else None
    audit = read_json_object(audit_path) if audit_path and audit_path.exists() else None

    position = loss.get("position") if isinstance(loss, dict) and isinstance(loss.get("position"), list) else []
    terminal = loss.get("terminal") if isinstance(loss, dict) and isinstance(loss.get("terminal"), list) else []
    first_preflop = (
        loss.get("first_preflop_decision")
        if isinstance(loss, dict) and isinstance(loss.get("first_preflop_decision"), list)
        else []
    )
    hole_family = loss.get("hole_family") if isinstance(loss, dict) and isinstance(loss.get("hole_family"), list) else []
    rates = loss.get("rates") if isinstance(loss, dict) and isinstance(loss.get("rates"), dict) else {}

    row = {
        "hands": slumbot_row.get("hands"),
        "bb_per_100": slumbot_row.get("bb_per_100"),
        "lower_bound_bb_per_100": slumbot_row.get("lower_bound_bb_per_100"),
        "upper_bound_bb_per_100": slumbot_row.get("upper_bound_bb_per_100"),
        "milestone_level": slumbot_row.get("milestone_level"),
        "ci_path": str(ci_path) if ci_path else None,
        "loss_report_path": str(loss_path) if loss_path else None,
        "loss_report_exists": bool(loss),
        "artifact_audit_path": str(audit_path) if audit_path else None,
        "artifact_audit_overall": audit.get("overall") if audit else None,
        "hand_review_path": str(review_path) if review_path else None,
        "hand_review_exists": bool(review),
        "training_adjustment": review.get("training_adjustment") if review else None,
        "evidence_class": review.get("evidence_class") if review else None,
        "hypothesis_areas": first_hypothesis_areas(review, limit=5),
        "warnings": (loss.get("warnings") or [])[:8] if isinstance(loss, dict) else [],
        "position": {
            "sb_bb100": loss_bucket_value(position, "SB"),
            "bb_bb100": loss_bucket_value(position, "BB"),
            "sb_chips": loss_bucket_value(position, "SB", "chips"),
            "bb_chips": loss_bucket_value(position, "BB", "chips"),
        },
        "terminal": {
            "hero_fold_bb100": loss_bucket_value(terminal, "hero_fold"),
            "showdown_bb100": loss_bucket_value(terminal, "showdown"),
            "opp_fold_bb100": loss_bucket_value(terminal, "opp_fold"),
            "allin_runout_bb100": loss_bucket_value(terminal, "allin_runout"),
        },
        "rates": {
            "sb_open_fold": round_or_none(rates.get("sb_open_fold_rate")),
            "sb_open_call": round_or_none(rates.get("sb_open_call_rate")),
            "sb_open_raise": round_or_none(rates.get("sb_open_raise_rate")),
            "sb_open_allin": round_or_none(rates.get("sb_open_allin_rate")),
            "bb_vs_open_call": round_or_none(rates.get("bb_vs_open_call_rate")),
            "bb_vs_open_raise": round_or_none(rates.get("bb_vs_open_raise_rate")),
        },
        "worst_first_preflop_decisions": top_loss_rows(first_preflop, limit=5),
        "worst_hole_families": top_loss_rows(hole_family, limit=5),
    }

    if previous:
        row["delta_vs_previous"] = {
            "bb_per_100": round_or_none(_safe_float(row.get("bb_per_100")) - _safe_float(previous.get("bb_per_100")))
            if _safe_float(row.get("bb_per_100")) is not None and _safe_float(previous.get("bb_per_100")) is not None
            else None,
            "sb_bb100": round_or_none(
                _safe_float((row.get("position") or {}).get("sb_bb100"))
                - _safe_float((previous.get("position") or {}).get("sb_bb100"))
            )
            if _safe_float((row.get("position") or {}).get("sb_bb100")) is not None
            and _safe_float((previous.get("position") or {}).get("sb_bb100")) is not None
            else None,
            "bb_bb100": round_or_none(
                _safe_float((row.get("position") or {}).get("bb_bb100"))
                - _safe_float((previous.get("position") or {}).get("bb_bb100"))
            )
            if _safe_float((row.get("position") or {}).get("bb_bb100")) is not None
            and _safe_float((previous.get("position") or {}).get("bb_bb100")) is not None
            else None,
            "hero_fold_bb100": round_or_none(
                _safe_float((row.get("terminal") or {}).get("hero_fold_bb100"))
                - _safe_float((previous.get("terminal") or {}).get("hero_fold_bb100"))
            )
            if _safe_float((row.get("terminal") or {}).get("hero_fold_bb100")) is not None
            and _safe_float((previous.get("terminal") or {}).get("hero_fold_bb100")) is not None
            else None,
            "showdown_bb100": round_or_none(
                _safe_float((row.get("terminal") or {}).get("showdown_bb100"))
                - _safe_float((previous.get("terminal") or {}).get("showdown_bb100"))
            )
            if _safe_float((row.get("terminal") or {}).get("showdown_bb100")) is not None
            and _safe_float((previous.get("terminal") or {}).get("showdown_bb100")) is not None
            else None,
        }
    else:
        row["delta_vs_previous"] = {}
    return row


def load_official_slumbot_loss_trend(slumbot_rows: list[dict[str, Any]], output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    previous: dict[str, Any] | None = None
    for slumbot_row in slumbot_rows:
        row = official_loss_row_from_ci(slumbot_row=slumbot_row, output_dir=output_dir, previous=previous)
        rows.append(row)
        previous = row
    return rows


def slumbot_stage_from_ci_path(ci_path: Path) -> str | None:
    name = ci_path.name
    for stage in ("quick5k", "promotion20k", "formal100k"):
        if f"_{stage}_" in name or f"_{stage}_ci_summary.json" in name:
            return stage
    return None


def milestone_m_from_name(name: str) -> int | None:
    parts = name.split("_")
    for part in parts:
        if len(part) > 1 and part.endswith("M") and part[:-1].isdigit():
            return int(part[:-1])
    return None


def hand_review_is_usable(review: dict[str, Any] | None) -> bool:
    if not review:
        return False
    return review.get("overall") not in {None, "MISSING_CI", "INCOMPLETE"}


def slumbot_analysis_row(ci_path: Path) -> dict[str, Any]:
    ci = read_json_object(ci_path)
    loss_path = sibling_artifact_from_ci(ci_path, "_loss_report.json")
    audit_path = sibling_artifact_from_ci(ci_path, "_artifact_audit.json")
    review_path = hand_review_path_from_ci(ci_path)
    promotion_path = sibling_artifact_from_ci(ci_path, "_promotion_gate.json")

    loss = read_json_object(loss_path) if loss_path and loss_path.exists() else None
    audit = read_json_object(audit_path) if audit_path and audit_path.exists() else None
    review = read_json_object(review_path) if review_path and review_path.exists() else None
    promotion = read_json_object(promotion_path) if promotion_path and promotion_path.exists() else None

    missing_parts: list[str] = []
    if not ci:
        missing_parts.append("ci_summary_load")
    if not promotion:
        missing_parts.append("promotion_gate")
    if not loss:
        missing_parts.append("loss_report")
    if not audit:
        missing_parts.append("artifact_audit")
    elif audit.get("overall") != "PASS":
        missing_parts.append("artifact_audit_pass")
    if not hand_review_is_usable(review):
        missing_parts.append("hand_review")

    return {
        "ci_path": str(ci_path),
        "stage": slumbot_stage_from_ci_path(ci_path),
        "milestone_m": milestone_m_from_name(ci_path.name),
        "hands": ci.get("hands") if ci else None,
        "bb_per_100": round_or_none(ci.get("bb_per_100")) if ci else None,
        "lower_bound_bb_per_100": round_or_none(ci.get("lower_bound_bb_per_100")) if ci else None,
        "loss_report_path": str(loss_path) if loss_path else None,
        "loss_report_exists": bool(loss),
        "artifact_audit_path": str(audit_path) if audit_path else None,
        "artifact_audit_overall": audit.get("overall") if audit else None,
        "hand_review_path": str(review_path) if review_path else None,
        "hand_review_overall": review.get("overall") if review else None,
        "hand_review_exists": bool(review),
        "hand_review_usable": hand_review_is_usable(review),
        "promotion_gate_path": str(promotion_path) if promotion_path else None,
        "promotion_gate_exists": bool(promotion),
        "promotion_gate_overall": promotion.get("overall") if promotion else None,
        "analysis_complete": not missing_parts,
        "missing_parts": missing_parts,
    }


def load_slumbot_analysis_coverage(output_dir: Path) -> dict[str, Any]:
    rows = [
        slumbot_analysis_row(path)
        for path in sorted(output_dir.glob("bench_v55_*_ci_summary.json"))
        if slumbot_stage_from_ci_path(path) is not None
    ]
    rows.sort(
        key=lambda row: (
            int(row.get("milestone_m") or -1),
            {"quick5k": 0, "promotion20k": 1, "formal100k": 2}.get(str(row.get("stage")), 99),
            str(row.get("ci_path") or ""),
        )
    )
    complete_rows = [row for row in rows if row.get("analysis_complete")]
    incomplete_rows = [row for row in rows if not row.get("analysis_complete")]
    latest = rows[-1] if rows else None
    latest_complete = complete_rows[-1] if complete_rows else None
    if not rows:
        overall = "NO_SLUMBOT_CI"
    elif latest and not latest.get("analysis_complete"):
        overall = "REVIEW_REQUIRED"
    elif incomplete_rows:
        overall = "WARN_HISTORICAL_INCOMPLETE"
    else:
        overall = "PASS"

    return {
        "overall": overall,
        "total_count": len(rows),
        "complete_count": len(complete_rows),
        "incomplete_count": len(incomplete_rows),
        "latest": latest,
        "latest_complete": latest_complete,
        "rows": rows,
    }


def summarize_selector_policy(
    *,
    policy: str,
    plan: dict[str, Any],
    result: dict[str, Any],
    output_dir: Path,
) -> dict[str, Any]:
    artifacts = plan.get("artifacts") if isinstance(plan.get("artifacts"), dict) else {}
    ci_path = resolve_artifact_path(artifacts.get("ci_json"), output_dir)
    review_path = hand_review_path_from_ci(ci_path)
    review = read_json_object(review_path) if review_path and review_path.exists() else None

    ci = result.get("ci_summary") if isinstance(result.get("ci_summary"), dict) else {}
    loss = review.get("loss") if isinstance(review, dict) and isinstance(review.get("loss"), dict) else {}
    rates = loss.get("rates") if isinstance(loss.get("rates"), dict) else {}
    position = loss.get("position") if isinstance(loss.get("position"), list) else []
    terminal = loss.get("terminal") if isinstance(loss.get("terminal"), list) else []

    return {
        "policy": policy,
        "status": result.get("status"),
        "hands": ci.get("hands"),
        "bb_per_100": round_or_none(ci.get("bb_per_100")),
        "lower_bound_bb_per_100": round_or_none(ci.get("lower_bound_bb_per_100")),
        "upper_bound_bb_per_100": round_or_none(ci.get("upper_bound_bb_per_100")),
        "milestone_level": ci.get("milestone_level"),
        "artifact_audit_overall": (
            (result.get("artifact_audit") or {}).get("overall")
            if isinstance(result.get("artifact_audit"), dict)
            else None
        ),
        "hand_review_path": str(review_path) if review_path else None,
        "hand_review_exists": bool(review),
        "training_adjustment": review.get("training_adjustment") if review else None,
        "evidence_class": review.get("evidence_class") if review else None,
        "warning_count": len(((loss.get("diagnostics") or {}).get("warnings") or [])) if loss else None,
        "hypothesis_areas": first_hypothesis_areas(review),
        "rates": {
            "sb_open_fold": round_or_none(rates.get("sb_open_fold_rate")),
            "sb_open_call": round_or_none(rates.get("sb_open_call_rate")),
            "sb_open_raise": round_or_none(rates.get("sb_open_raise_rate")),
            "bb_vs_open_call": round_or_none(rates.get("bb_vs_open_call_rate")),
            "bb_vs_open_raise": round_or_none(rates.get("bb_vs_open_raise_rate")),
        },
        "position": {
            "sb_bb100": loss_bucket_value(position, "SB"),
            "bb_bb100": loss_bucket_value(position, "BB"),
        },
        "terminal": {
            "showdown_bb100": loss_bucket_value(terminal, "showdown"),
            "hero_fold_bb100": loss_bucket_value(terminal, "hero_fold"),
            "opp_fold_bb100": loss_bucket_value(terminal, "opp_fold"),
            "allin_runout_bb100": loss_bucket_value(terminal, "allin_runout"),
        },
        "ci_path": str(ci_path) if ci_path else None,
    }


def load_selector_pair_history(run_dir: Path, output_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(run_dir.glob("slumbot_selector_pair_*_status.json")):
        status = read_json_object(path)
        if not status:
            continue
        frozen = status.get("frozen_summary") if isinstance(status.get("frozen_summary"), dict) else {}
        results = status.get("results") if isinstance(status.get("results"), dict) else {}
        plans = status.get("plans") if isinstance(status.get("plans"), dict) else {}
        if not results:
            continue

        policy_rows: dict[str, dict[str, Any]] = {}
        for policy in ("greedy", "preflop-callguard"):
            result = results.get(policy)
            if not isinstance(result, dict):
                continue
            plan = plans.get(policy) if isinstance(plans.get(policy), dict) else {}
            policy_rows[policy] = summarize_selector_policy(
                policy=policy,
                plan=plan,
                result=result,
                output_dir=output_dir,
            )

        greedy = policy_rows.get("greedy") or {}
        callguard = policy_rows.get("preflop-callguard") or {}
        greedy_bb = _safe_float(greedy.get("bb_per_100"))
        callguard_bb = _safe_float(callguard.get("bb_per_100"))
        rows.append(
            {
                "path": str(path),
                "label": path.stem.replace("slumbot_selector_pair_", "").replace("_status", ""),
                "state": status.get("state"),
                "checked_at": status.get("checked_at"),
                "checkpoint_iteration": frozen.get("iteration"),
                "checkpoint_hands": frozen.get("total_hands"),
                "planned_hands_per_policy": status.get("planned_hands_per_policy"),
                "delta_callguard_vs_greedy_bb_per_100": (
                    round_or_none(callguard_bb - greedy_bb)
                    if callguard_bb is not None and greedy_bb is not None
                    else round_or_none(status.get("delta_callguard_vs_greedy_bb_per_100"))
                ),
                "policies": policy_rows,
            }
        )

    rows.sort(
        key=lambda row: (
            int(row.get("checkpoint_iteration") or 0),
            int(row.get("checkpoint_hands") or 0),
            str(row.get("label") or ""),
        )
    )
    return rows


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return number


def summarize_preflop_probe(path: Path) -> dict[str, Any] | None:
    try:
        probe = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    if not isinstance(probe, dict):
        return None

    cases = [case for case in probe.get("cases") or [] if isinstance(case, dict)]
    call_gaps: list[float] = []
    greedy_call_rates: list[float] = []
    greedy_fold_rates: list[float] = []
    greedy_raise_rates: list[float] = []
    callguard_call_rates: list[float] = []
    case_rows: dict[str, dict[str, Any]] = {}

    for case in cases:
        name = str(case.get("name") or "")
        mass = case.get("mean_class_prob_mass") or {}
        greedy = case.get("greedy_class_rates") or {}
        callguard = (case.get("callguard") or {}).get("class_rates") or {}

        mean_call = _safe_float(mass.get("call"))
        greedy_call = _safe_float(greedy.get("call"))
        greedy_fold = _safe_float(greedy.get("fold"))
        greedy_raise = _safe_float(greedy.get("raise"))
        callguard_call = _safe_float(callguard.get("call"))

        if mean_call is not None and greedy_call is not None:
            call_gaps.append(mean_call - greedy_call)
        if greedy_call is not None:
            greedy_call_rates.append(greedy_call)
        if greedy_fold is not None:
            greedy_fold_rates.append(greedy_fold)
        if greedy_raise is not None:
            greedy_raise_rates.append(greedy_raise)
        if callguard_call is not None:
            callguard_call_rates.append(callguard_call)

        if name:
            case_rows[name] = {
                "mean_call_prob": round_or_none(mean_call),
                "greedy_call_rate": round_or_none(greedy_call),
                "greedy_fold_rate": round_or_none(greedy_fold),
                "greedy_raise_rate": round_or_none(greedy_raise),
                "call_gap": round_or_none(mean_call - greedy_call) if mean_call is not None and greedy_call is not None else None,
                "callguard_call_rate": round_or_none(callguard_call),
            }

    checkpoint = probe.get("checkpoint") or {}
    return {
        "path": str(path),
        "checked_at": probe.get("checked_at"),
        "checkpoint_iteration": checkpoint.get("iteration"),
        "checkpoint_hands": checkpoint.get("total_hands"),
        "overall": probe.get("overall"),
        "warning_count": len(probe.get("warnings") or []),
        "failure_count": len(probe.get("failures") or []),
        "mean_call_gap": round_or_none(sum(call_gaps) / len(call_gaps) if call_gaps else None),
        "mean_greedy_call_rate": round_or_none(sum(greedy_call_rates) / len(greedy_call_rates) if greedy_call_rates else None),
        "mean_greedy_fold_rate": round_or_none(sum(greedy_fold_rates) / len(greedy_fold_rates) if greedy_fold_rates else None),
        "mean_greedy_raise_rate": round_or_none(sum(greedy_raise_rates) / len(greedy_raise_rates) if greedy_raise_rates else None),
        "mean_callguard_call_rate": round_or_none(sum(callguard_call_rates) / len(callguard_call_rates) if callguard_call_rates else None),
        "cases": case_rows,
    }


def load_preflop_history(run_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[tuple[int, int]] = set()
    for path in sorted((run_dir / "preflop_probe_history").glob("*.json")):
        row = summarize_preflop_probe(path)
        if not row:
            continue
        iteration = row.get("checkpoint_iteration")
        hands = row.get("checkpoint_hands")
        if iteration is None or hands is None:
            continue
        key = (int(iteration), int(hands))
        seen.add(key)
        rows.append(row)

    latest_path = run_dir / "v5_preflop_probe_latest.json"
    latest = summarize_preflop_probe(latest_path) if latest_path.exists() else None
    if latest and latest.get("checkpoint_iteration") is not None and latest.get("checkpoint_hands") is not None:
        key = (int(latest["checkpoint_iteration"]), int(latest["checkpoint_hands"]))
        if key not in seen:
            rows.append(latest)

    rows.sort(key=lambda item: (int(item.get("checkpoint_iteration") or 0), int(item.get("checkpoint_hands") or 0)))
    previous_gap: float | None = None
    previous_warnings: int | None = None
    previous_greedy_call: float | None = None
    for row in rows:
        gap = _safe_float(row.get("mean_call_gap"))
        warnings = int(row.get("warning_count") or 0)
        greedy_call = _safe_float(row.get("mean_greedy_call_rate"))
        row["delta_call_gap_vs_previous"] = (
            round_or_none(gap - previous_gap) if gap is not None and previous_gap is not None else None
        )
        row["delta_warning_count_vs_previous"] = warnings - previous_warnings if previous_warnings is not None else None
        row["delta_greedy_call_rate_vs_previous"] = (
            round_or_none(greedy_call - previous_greedy_call)
            if greedy_call is not None and previous_greedy_call is not None
            else None
        )
        previous_gap = gap
        previous_warnings = warnings
        previous_greedy_call = greedy_call
    return rows


def classify_direction(
    *,
    scorecard: dict[str, Any],
    internal_rows: list[dict[str, Any]],
    slumbot_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    slumbot = scorecard.get("slumbot_ci") or {}
    if slumbot.get("formal_l6_proven"):
        return {
            "answer": "L6_PROVEN_BY_SLUMBOT_CI",
            "claim_allowed": True,
            "basis": "100k+ Slumbot CI evidence reaches the near-paper target.",
        }
    if slumbot.get("formal_l5_proven"):
        return {
            "answer": "L5_PROVEN_BY_SLUMBOT_CI",
            "claim_allowed": True,
            "basis": "100k+ Slumbot CI lower bound is above zero.",
        }
    if len(slumbot_rows) >= 2:
        latest = slumbot_rows[-1]
        previous = slumbot_rows[-2]
        latest_bb = latest.get("bb_per_100")
        previous_bb = previous.get("bb_per_100")
        if latest_bb is not None and previous_bb is not None and latest_bb > previous_bb:
            return {
                "answer": "SLUMBOT_POINT_ESTIMATE_UP_CI_UNPROVEN",
                "claim_allowed": False,
                "basis": "Latest Slumbot point estimate is higher, but formal CI gate has not passed.",
            }
        if latest_bb is not None and previous_bb is not None and latest_bb < previous_bb:
            return {
                "answer": "SLUMBOT_POINT_ESTIMATE_DOWN",
                "claim_allowed": False,
                "basis": "Latest Slumbot point estimate is lower than the previous Slumbot result.",
            }
        return {
            "answer": "SLUMBOT_POINT_ESTIMATE_FLAT_OR_UNKNOWN",
            "claim_allowed": False,
            "basis": "Slumbot results exist, but they do not prove improvement.",
        }
    if len(slumbot_rows) == 1:
        return {
            "answer": "ONE_SLUMBOT_RESULT_ONLY",
            "claim_allowed": False,
            "basis": "One Slumbot result is not enough for a trend, and formal CI gate has not passed.",
        }

    if len(internal_rows) >= 2:
        latest = internal_rows[-1]
        delta = latest.get("delta_mean_vs_previous")
        latest_best = int(latest.get("latest_is_best_opponents") or 0)
        opponent_count = int(latest.get("opponent_count") or 0)
        if delta is not None and delta > 0 and latest_best == opponent_count and opponent_count > 0:
            return {
                "answer": "INTERNAL_POINT_ESTIMATE_UP_LATEST_BEST",
                "claim_allowed": False,
                "basis": "Internal probe improved and latest is best for all fixed opponents, but this is not Slumbot evidence.",
            }
        if delta is not None and delta > 0:
            return {
                "answer": "INTERNAL_POINT_ESTIMATE_UP_WITH_REGRESSION_RISK",
                "claim_allowed": False,
                "basis": "Internal mean improved versus the previous probe, but latest is not best across fixed opponents.",
            }
        if delta is not None and delta < 0:
            return {
                "answer": "INTERNAL_POINT_ESTIMATE_DOWN",
                "claim_allowed": False,
                "basis": "Internal mean dropped versus the previous probe.",
            }
        return {
            "answer": "INTERNAL_NO_CLEAR_CHANGE",
            "claim_allowed": False,
            "basis": "Internal probes exist, but the latest delta is inconclusive.",
        }

    return {
        "answer": "UNKNOWN_INSUFFICIENT_EVIDENCE",
        "claim_allowed": False,
        "basis": "No Slumbot score and not enough internal probe history.",
    }


def next_evidence_events(dashboard: dict[str, Any]) -> dict[str, Any]:
    progress = dashboard.get("progress") or {}
    gates = dashboard.get("gates") or {}
    watchers = dashboard.get("watchers") or {}
    eval_cadence = watchers.get("eval_cadence") or {}
    eval_cadence_watch = watchers.get("eval_cadence_watch") or {}
    checkpoint_eta = progress.get("checkpoint_eligibility") or {}
    return {
        "next_gate": gates.get("next_pending"),
        "internal_probe": watchers.get("internal_strength"),
        "next_external_eval": eval_cadence.get("next_external_eval"),
        "next_promotion_eval": eval_cadence.get("next_promotion_eval"),
        "next_formal_eval": eval_cadence.get("next_formal_eval"),
        "eval_cadence_policy": eval_cadence.get("policy"),
        "eval_cadence_status_age_seconds": eval_cadence.get("status_age_seconds"),
        "eval_cadence_watch": eval_cadence_watch,
        "quick5k_checkpoint_eligibility": checkpoint_eta.get("quick5k"),
        "promotion20k_checkpoint_eligibility": checkpoint_eta.get("promotion20k"),
        "formal100k_checkpoint_eligibility": checkpoint_eta.get("formal100k"),
    }


def build_trend_ledger(run_dir: Path, output_dir: Path) -> dict[str, Any]:
    dashboard = build_summary(run_dir)
    scorecard = build_scorecard(run_dir, output_dir)
    internal_rows = load_internal_history(run_dir)
    current_slumbot_rows = slumbot_history_from_scorecard(scorecard)
    parent_trend, parent_trend_path = load_parent_trend_ledger(run_dir)
    inherited_slumbot_rows = clean_inherited_slumbot_rows(parent_trend)
    slumbot_rows = merge_slumbot_history(inherited_slumbot_rows, current_slumbot_rows)
    official_loss_rows = load_official_slumbot_loss_trend(slumbot_rows, output_dir)
    slumbot_analysis_coverage = load_slumbot_analysis_coverage(output_dir)
    preflop_rows = load_preflop_history(run_dir)
    selector_rows = load_selector_pair_history(run_dir, output_dir)
    direction = classify_direction(scorecard=scorecard, internal_rows=internal_rows, slumbot_rows=slumbot_rows)
    latest_official = slumbot_rows[-1] if slumbot_rows else None
    trend_direction = direction.get("answer")
    claim_latest_is_better = bool(direction.get("claim_allowed"))
    overall = "LATEST_BETTER_CLAIMABLE" if claim_latest_is_better else str(trend_direction or "UNKNOWN")

    training = scorecard.get("training") or {}
    return {
        "checked_at": now_iso(),
        "overall": overall,
        "run_dir": str(run_dir),
        "run_id": dashboard.get("run_id") or run_dir.name,
        "latest_official": latest_official,
        "lineage_parent_trend": {
            "path": str(parent_trend_path) if parent_trend_path else None,
            "loaded": bool(parent_trend),
            "inherited_slumbot_rows": len(inherited_slumbot_rows),
            "current_slumbot_rows": len(current_slumbot_rows),
        },
        "trend_direction": trend_direction,
        "decision": {
            "claim_latest_is_better": claim_latest_is_better,
            "claim_latest_is_better_reason": direction.get("basis"),
            "promote_strength_claim": False,
            "promote_strength_claim_reason": "Only formal 100k+ greedy Slumbot evidence with bb/100 > 0 and CI lower > 0 can prove strength.",
        },
        "live": {
            "health": (dashboard.get("health") or {}).get("overall"),
            "iteration": ((dashboard.get("training") or {}).get("latest") or {}).get("iteration"),
            "hands": (dashboard.get("training") or {}).get("current_hands"),
            "recent_hands_per_second": (dashboard.get("training") or {}).get("recent_hands_per_second"),
            "checkpoint_iteration": (dashboard.get("checkpoint") or {}).get("iteration"),
            "checkpoint_hands": (dashboard.get("checkpoint") or {}).get("total_hands"),
        },
        "direction": direction,
        "training_health_trend": {
            "overall": training.get("overall"),
            "last200_comparison": training.get("last200_comparison"),
            "note": training.get("note"),
        },
        "internal_probe_history": internal_rows,
        "preflop_probe_history": preflop_rows,
        "slumbot_history": slumbot_rows,
        "slumbot_analysis_coverage": slumbot_analysis_coverage,
        "official_slumbot_loss_trend": official_loss_rows,
        "selector_pair_history": selector_rows,
        "next_evidence_events": next_evidence_events(dashboard),
        "claim_rules": {
            "can_claim_latest_is_better": bool(direction.get("claim_allowed")),
            "can_claim_l5": bool((scorecard.get("slumbot_ci") or {}).get("formal_l5_proven")),
            "can_claim_l6": bool((scorecard.get("slumbot_ci") or {}).get("formal_l6_proven")),
            "required_for_l5": "100k+ Slumbot hands, bb/100 > 0, and 95% CI lower bound > 0.",
            "required_for_l6": "Formal Slumbot evidence at or near +11.1 bb/100.",
        },
    }


def markdown_table(rows: list[list[Any]]) -> list[str]:
    if not rows:
        return []
    widths = [0 for _ in rows[0]]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(str(cell)))
    lines = []
    for row_index, row in enumerate(rows):
        line = "| " + " | ".join(str(cell).ljust(widths[index]) for index, cell in enumerate(row)) + " |"
        lines.append(line)
        if row_index == 0:
            lines.append("| " + " | ".join("-" * widths[index] for index in range(len(row))) + " |")
    return lines


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    live = summary.get("live") or {}
    direction = summary.get("direction") or {}
    next_events = summary.get("next_evidence_events") or {}
    quick5k = next_events.get("quick5k_checkpoint_eligibility") or {}
    internal_event = next_events.get("internal_probe") or {}
    next_external = next_events.get("next_external_eval") or {}
    next_promotion = next_events.get("next_promotion_eval") or {}
    next_formal = next_events.get("next_formal_eval") or {}
    cadence_watch = next_events.get("eval_cadence_watch") or {}

    lines = [
        "# V5 Trend Ledger",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Run: `{summary.get('run_id')}`",
        f"- Health: `{live.get('health')}`",
        f"- Live iteration / hands: `{live.get('iteration')}` / `{live.get('hands')}`",
        f"- Checkpoint iteration / hands: `{live.get('checkpoint_iteration')}` / `{live.get('checkpoint_hands')}`",
        f"- Direction answer: `{direction.get('answer')}`",
        f"- Claim latest is better: `{direction.get('claim_allowed')}`",
        f"- Basis: {direction.get('basis')}",
        "",
        "## Internal Probe History",
        "",
    ]

    internal_rows = summary.get("internal_probe_history") or []
    if internal_rows:
        rows = [
            ["iter", "hands", "mean bb/100", "mean lower", "delta mean", "latest best", "verdict"],
        ]
        for row in internal_rows:
            rows.append(
                [
                    row.get("checkpoint_iteration"),
                    row.get("checkpoint_hands"),
                    row.get("mean_latest_bb100"),
                    row.get("mean_latest_lower_bound_bb100"),
                    row.get("delta_mean_vs_previous"),
                    f"{row.get('latest_is_best_opponents')}/{row.get('opponent_count')}",
                    row.get("verdict"),
                ]
            )
        lines.extend(markdown_table(rows))
    else:
        lines.append("- No internal probe history yet.")

    lines.extend(["", "## Preflop Probe History", ""])
    preflop_rows = summary.get("preflop_probe_history") or []
    if preflop_rows:
        rows = [
            [
                "iter",
                "hands",
                "overall",
                "warn",
                "call gap",
                "delta gap",
                "greedy call",
                "delta call",
            ],
        ]
        for row in preflop_rows:
            rows.append(
                [
                    row.get("checkpoint_iteration"),
                    row.get("checkpoint_hands"),
                    row.get("overall"),
                    row.get("warning_count"),
                    row.get("mean_call_gap"),
                    row.get("delta_call_gap_vs_previous"),
                    row.get("mean_greedy_call_rate"),
                    row.get("delta_greedy_call_rate_vs_previous"),
                ]
            )
        lines.extend(markdown_table(rows))
        lines.extend(
            [
                "",
                "Call gap is mean policy call probability minus greedy realized call rate across probe cases; lower is better only if Slumbot score does not regress.",
            ]
        )
    else:
        lines.append("- No preflop probe history yet.")

    lines.extend(["", "## Slumbot History", ""])
    slumbot_rows = summary.get("slumbot_history") or []
    if slumbot_rows:
        rows = [["hands", "bb/100", "lower", "upper", "level", "L5", "L6"]]
        for row in slumbot_rows:
            rows.append(
                [
                    row.get("hands"),
                    row.get("bb_per_100"),
                    row.get("lower_bound_bb_per_100"),
                    row.get("upper_bound_bb_per_100"),
                    row.get("milestone_level"),
                    row.get("l5_formal_win"),
                    row.get("l6_near_paper_target"),
                ]
            )
        lines.extend(markdown_table(rows))
    else:
        lines.append("- No Slumbot CI artifact exists for this V5 run yet.")

    lines.extend(["", "## Slumbot Analysis Coverage", ""])
    coverage = summary.get("slumbot_analysis_coverage") or {}
    coverage_rows = coverage.get("rows") or []
    lines.extend(
        [
            f"- Overall: `{coverage.get('overall')}`",
            f"- Complete / total: `{coverage.get('complete_count')}` / `{coverage.get('total_count')}`",
            f"- Incomplete historical rows: `{coverage.get('incomplete_count')}`",
            "",
        ]
    )
    if coverage_rows:
        rows = [
            [
                "target",
                "stage",
                "hands",
                "bb/100",
                "loss",
                "audit",
                "review",
                "promo",
                "complete",
                "missing",
            ]
        ]
        for row in coverage_rows:
            rows.append(
                [
                    row.get("milestone_m"),
                    row.get("stage"),
                    row.get("hands"),
                    row.get("bb_per_100"),
                    row.get("loss_report_exists"),
                    row.get("artifact_audit_overall"),
                    row.get("hand_review_overall") or row.get("hand_review_exists"),
                    row.get("promotion_gate_overall") or row.get("promotion_gate_exists"),
                    row.get("analysis_complete"),
                    ",".join(row.get("missing_parts") or []),
                ]
            )
        lines.extend(markdown_table(rows))
        lines.extend(
            [
                "",
                "Rows marked incomplete are historical diagnostics only. A Slumbot result is actionable for training only after CI, promotion gate, loss report, artifact audit PASS, and usable hand review are all present.",
            ]
        )
    else:
        lines.append("- No Slumbot benchmark CI rows were found in the output directory.")

    lines.extend(["", "## Official Slumbot Loss Trend", ""])
    official_loss_rows = summary.get("official_slumbot_loss_trend") or []
    if official_loss_rows:
        rows = [
            [
                "hands",
                "bb/100",
                "delta",
                "SB",
                "BB",
                "hero fold",
                "showdown",
                "SB F/C/R",
                "BB C/R",
                "audit",
                "review",
                "top leak areas",
            ]
        ]
        for row in official_loss_rows:
            position = row.get("position") or {}
            terminal = row.get("terminal") or {}
            rates = row.get("rates") or {}
            delta = row.get("delta_vs_previous") or {}
            rows.append(
                [
                    row.get("hands"),
                    row.get("bb_per_100"),
                    delta.get("bb_per_100"),
                    position.get("sb_bb100"),
                    position.get("bb_bb100"),
                    terminal.get("hero_fold_bb100"),
                    terminal.get("showdown_bb100"),
                    f"{rates.get('sb_open_fold')}/{rates.get('sb_open_call')}/{rates.get('sb_open_raise')}",
                    f"{rates.get('bb_vs_open_call')}/{rates.get('bb_vs_open_raise')}",
                    row.get("artifact_audit_overall"),
                    row.get("training_adjustment") or ("missing" if not row.get("hand_review_exists") else None),
                    ",".join(row.get("hypothesis_areas") or []),
                ]
            )
        lines.extend(markdown_table(rows))

        latest_loss = official_loss_rows[-1]
        worst_preflop = latest_loss.get("worst_first_preflop_decisions") or []
        worst_holes = latest_loss.get("worst_hole_families") or []
        if worst_preflop:
            lines.extend(["", "Latest worst first preflop decisions:"])
            lines.extend(
                f"- `{item.get('key')}`: chips `{item.get('chips')}`, bb/100 `{item.get('bb_per_100')}`, hands `{item.get('hands')}`"
                for item in worst_preflop
            )
        if worst_holes:
            lines.extend(["", "Latest worst hole families:"])
            lines.extend(
                f"- `{item.get('key')}`: chips `{item.get('chips')}`, bb/100 `{item.get('bb_per_100')}`, hands `{item.get('hands')}`"
                for item in worst_holes
            )
        lines.extend(
            [
                "",
                "This section is derived from official Slumbot hand logs through loss report, artifact audit, and hand review artifacts. It is the required starting point before changing training from Slumbot evidence.",
            ]
        )
    else:
        lines.append("- No official Slumbot loss reports were found for the current scorecard history.")

    lines.extend(["", "## Selector Pair Diagnostic History", ""])
    selector_rows = summary.get("selector_pair_history") or []
    if selector_rows:
        rows = [
            [
                "iter",
                "hands",
                "greedy",
                "g lower",
                "callguard",
                "delta",
                "g SB",
                "g BB",
                "g rates",
                "review",
                "top leak areas",
            ]
        ]
        for row in selector_rows:
            policies = row.get("policies") or {}
            greedy = policies.get("greedy") or {}
            callguard = policies.get("preflop-callguard") or {}
            rates = greedy.get("rates") or {}
            position = greedy.get("position") or {}
            rows.append(
                [
                    row.get("checkpoint_iteration") or row.get("label"),
                    row.get("checkpoint_hands"),
                    greedy.get("bb_per_100"),
                    greedy.get("lower_bound_bb_per_100"),
                    callguard.get("bb_per_100"),
                    row.get("delta_callguard_vs_greedy_bb_per_100"),
                    position.get("sb_bb100"),
                    position.get("bb_bb100"),
                    (
                        f"SB F/C/R {rates.get('sb_open_fold')}/{rates.get('sb_open_call')}/{rates.get('sb_open_raise')}; "
                        f"BB C/R {rates.get('bb_vs_open_call')}/{rates.get('bb_vs_open_raise')}"
                    ),
                    greedy.get("training_adjustment") or ("missing" if not greedy.get("hand_review_exists") else None),
                    ",".join(greedy.get("hypothesis_areas") or []),
                ]
            )
        lines.extend(markdown_table(rows))
        lines.extend(
            [
                "",
                "Selector-pair rows are diagnostic only. They expose checkpoint-to-checkpoint leaks and policy-margin issues, but they do not support V4/L5/L6 strength claims.",
            ]
        )
    else:
        lines.append("- No selector-pair diagnostic status files were found.")

    lines.extend(
        [
            "",
            "## Next Evidence",
            "",
            f"- Internal probe watcher: `{internal_event.get('latest_overall')}` target `{internal_event.get('latest_target')}`",
            (
                f"- Next external eval: `{next_external.get('stage')}` target `{next_external.get('target_hands')}` "
                f"state `{next_external.get('state')}` ETA `{next_external.get('eta_duration_live')}`"
                if next_external
                else f"- quick5k checkpoint eligibility fallback: iter `{quick5k.get('target_checkpoint_iteration')}` / ETA `{quick5k.get('eta_duration')}`"
            ),
            (
                f"- Next promotion eval: `{next_promotion.get('stage')}` target `{next_promotion.get('target_hands')}` "
                f"state `{next_promotion.get('state')}` ETA `{next_promotion.get('eta_duration_live')}`"
                if next_promotion
                else "- Next promotion eval: `None`"
            ),
            (
                f"- Next formal eval: `{next_formal.get('stage')}` target `{next_formal.get('target_hands')}` "
                f"state `{next_formal.get('state')}` ETA `{next_formal.get('eta_duration_live')}`"
                if next_formal
                else "- Next formal eval: `None`"
            ),
            f"- Eval cadence launcher: candidates `{cadence_watch.get('candidate_count')}` launchable `{cadence_watch.get('launchable_key')}`",
            "",
            "## Claim Rules",
            "",
            f"- Can claim L5: `{(summary.get('claim_rules') or {}).get('can_claim_l5')}`",
            f"- Can claim L6: `{(summary.get('claim_rules') or {}).get('can_claim_l6')}`",
            f"- L5 rule: {(summary.get('claim_rules') or {}).get('required_for_l5')}",
            f"- L6 rule: {(summary.get('claim_rules') or {}).get('required_for_l6')}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a V5 trend ledger.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_trend_ledger(Path(args.run_dir), Path(args.output_dir))
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
