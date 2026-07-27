#!/usr/bin/env python3
"""Build a compact hand-review summary for a saved V5 Slumbot benchmark.

This is a read-only derived report. It does not call Slumbot. It ties together
the CI score, artifact audit, and loss report so training changes are based on
hand-level evidence instead of bb/100 alone.
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
REPO_ROOT = SCRIPT_DIR.parents[1]
sys.path.insert(0, str(SCRIPT_DIR))

from v5_scorecard import build_scorecard


DEFAULT_BASELINE_BB100 = -71.383
DEFAULT_L6_TARGET_BB100 = 11.1


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        loaded = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def resolve_path(value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    if path.is_absolute():
        return path
    return REPO_ROOT / path


def round_or_none(value: Any, digits: int = 3) -> float | None:
    try:
        number = float(value)
    except Exception:
        return None
    if not math.isfinite(number):
        return None
    return round(number, digits)


def fmt(value: Any, digits: int = 3, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, (int, float)):
        spec = f"{'+' if signed else ''}.{digits}f"
        return format(float(value), spec)
    return str(value)


def fmt_int(value: Any) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return "n/a"


def tag_from_ci_path(path: Path) -> str | None:
    stem = path.name
    prefix = "bench_v55_"
    suffix = "_ci_summary.json"
    if stem.startswith(prefix) and stem.endswith(suffix):
        return stem[len(prefix) : -len(suffix)]
    return None


def paths_for_tag(output_dir: Path, tag: str) -> dict[str, Path]:
    prefix = output_dir / f"bench_v55_{tag}"
    return {
        "ci_json": Path(str(prefix) + "_ci_summary.json"),
        "loss_report_json": Path(str(prefix) + "_loss_report.json"),
        "loss_report_md": Path(str(prefix) + "_loss_report.md"),
        "artifact_audit_json": Path(str(prefix) + "_artifact_audit.json"),
        "artifact_audit_md": Path(str(prefix) + "_artifact_audit.md"),
        "promotion_json": Path(str(prefix) + "_promotion_gate.json"),
        "dump_analysis": Path(str(prefix) + "_dump_analysis.txt"),
    }


def select_ci_from_scorecard(run_dir: Path, output_dir: Path, selection: str, policy: str) -> tuple[Path | None, dict[str, Any] | None]:
    scorecard = build_scorecard(run_dir, output_dir)
    slumbot = scorecard.get("slumbot_ci") if isinstance(scorecard.get("slumbot_ci"), dict) else {}
    selected: dict[str, Any] | None = None
    if selection == "official":
        selected = slumbot.get("latest") if isinstance(slumbot.get("latest"), dict) else None
    elif selection == "diagnostic":
        by_policy = slumbot.get("latest_diagnostic_by_policy") if isinstance(slumbot.get("latest_diagnostic_by_policy"), dict) else {}
        selected = by_policy.get(policy) if isinstance(by_policy.get(policy), dict) else None
        if selected is None:
            selected = slumbot.get("latest_diagnostic") if isinstance(slumbot.get("latest_diagnostic"), dict) else None
    else:
        selected = slumbot.get("latest") if isinstance(slumbot.get("latest"), dict) else None
        if selected is None:
            selected = slumbot.get("latest_diagnostic") if isinstance(slumbot.get("latest_diagnostic"), dict) else None

    if not selected:
        return None, None
    path = resolve_path(str(selected.get("path") or ""))
    return path, selected


def first_rows(loss_report: dict[str, Any], key: str, limit: int) -> list[dict[str, Any]]:
    rows = loss_report.get(key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows[:limit] if isinstance(row, dict)]


def row_by_key(rows: list[dict[str, Any]], key: str) -> dict[str, Any] | None:
    for row in rows:
        if row.get("key") == key:
            return row
    return None


def rates_summary(rates: dict[str, Any]) -> dict[str, float | None]:
    fields = (
        "sb_open_fold_rate",
        "sb_open_call_rate",
        "sb_open_raise_rate",
        "sb_open_allin_rate",
        "bb_vs_open_call_rate",
        "bb_vs_open_raise_rate",
    )
    return {field: round_or_none(rates.get(field)) for field in fields}


def classify_evidence(ci: dict[str, Any], tag: str, policy_mode: str | None) -> str:
    hands = int(ci.get("hands") or 0)
    diagnostic = bool(ci.get("diagnostic")) or "selector_pair" in tag or (policy_mode not in (None, "", "greedy"))
    if diagnostic:
        return "diagnostic"
    if hands >= 100_000:
        return "formal"
    if hands >= 20_000:
        return "promotion_scale"
    if hands >= 5_000:
        return "quick_screen"
    return "small_sample"


def claim_status(ci: dict[str, Any], evidence_class: str, l6_target: float) -> dict[str, Any]:
    hands = int(ci.get("hands") or 0)
    bb100 = round_or_none(ci.get("bb_per_100"))
    lower = round_or_none(ci.get("lower_bound_bb_per_100"))
    blockers: list[str] = []
    if evidence_class == "diagnostic":
        blockers.append("diagnostic result")
    if hands < 100_000:
        blockers.append("hands < 100000")
    if bb100 is None or bb100 <= 0:
        blockers.append("bb/100 <= 0")
    if lower is None or lower <= 0:
        blockers.append("95% CI lower <= 0")
    l5 = not blockers
    l6 = l5 and bb100 is not None and bb100 >= l6_target - 2.0
    if l5 and not l6:
        blockers.append(f"bb/100 below L6 threshold {l6_target - 2.0:.1f}")
    return {
        "can_claim_l5": l5,
        "can_claim_l6": l6,
        "blockers": blockers,
    }


def build_hypotheses(loss_report: dict[str, Any]) -> list[dict[str, Any]]:
    rates = loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {}
    position = loss_report.get("position") if isinstance(loss_report.get("position"), list) else []
    terminal = loss_report.get("terminal") if isinstance(loss_report.get("terminal"), list) else []
    hypotheses: list[dict[str, Any]] = []

    sb = row_by_key([row for row in position if isinstance(row, dict)], "SB")
    bb = row_by_key([row for row in position if isinstance(row, dict)], "BB")
    if sb and float(sb.get("chips") or 0) < 0:
        hypotheses.append(
            {
                "area": "SB_EV",
                "evidence": f"SB chips {int(sb.get('chips') or 0):+,}; bb/100 {fmt(sb.get('bb_per_100'), 1, True)}",
                "training_signal": "Review SB open and continuation quality before changing global priors.",
            }
        )
    if bb and float(bb.get("chips") or 0) < 0:
        hypotheses.append(
            {
                "area": "BB_EV",
                "evidence": f"BB chips {int(bb.get('chips') or 0):+,}; bb/100 {fmt(bb.get('bb_per_100'), 1, True)}",
                "training_signal": "Check BB defense and postflop realization.",
            }
        )

    sb_fold = rates.get("sb_open_fold_rate")
    sb_call = rates.get("sb_open_call_rate")
    sb_raise = rates.get("sb_open_raise_rate")
    if isinstance(sb_fold, (int, float)) and sb_fold > 0.30:
        hypotheses.append(
            {
                "area": "SB_OPEN_FOLD",
                "evidence": f"SB open fold rate {sb_fold:.3f}",
                "training_signal": "Possible SB first-action leak; prefer context-conditioned SB-open review.",
            }
        )
    if isinstance(sb_call, (int, float)) and sb_call > 0.45:
        hypotheses.append(
            {
                "area": "SB_OPEN_LIMP_HEAVY",
                "evidence": f"SB open call rate {sb_call:.3f}",
                "training_signal": "Check for under-raising first action rather than adding broad call pressure.",
            }
        )
    if isinstance(sb_raise, (int, float)) and sb_raise < 0.20:
        hypotheses.append(
            {
                "area": "SB_OPEN_UNDERRAISING",
                "evidence": f"SB open raise rate {sb_raise:.3f}",
                "training_signal": "Review SB-open raise target and selector margins.",
            }
        )

    bb_call = rates.get("bb_vs_open_call_rate")
    bb_raise = rates.get("bb_vs_open_raise_rate")
    if isinstance(bb_call, (int, float)) and bb_call < 0.05:
        hypotheses.append(
            {
                "area": "BB_DEFENSE_CALL_SUPPRESSION",
                "evidence": f"BB vs open call rate {bb_call:.3f}",
                "training_signal": "Selector/training margin leak; do not force callguard as official policy without score evidence.",
            }
        )
    if isinstance(bb_raise, (int, float)) and bb_raise > 0.45:
        hypotheses.append(
            {
                "area": "BB_DEFENSE_3BET_HEAVY",
                "evidence": f"BB vs open raise rate {bb_raise:.3f}",
                "training_signal": "Check whether BB defense is fold/3bet-heavy and loses postflop/showdown value.",
            }
        )

    for key, area in (
        ("showdown", "SHOWDOWN_VALUE"),
        ("hero_fold", "FOLDING_OR_REALIZATION"),
        ("allin_runout", "ALLIN_OR_BIG_POT"),
    ):
        row = row_by_key([item for item in terminal if isinstance(item, dict)], key)
        if row and float(row.get("chips") or 0) < 0:
            hypotheses.append(
                {
                    "area": area,
                    "evidence": f"{key} chips {int(row.get('chips') or 0):+,}; bb/100 {fmt(row.get('bb_per_100'), 1, True)}",
                    "training_signal": "If repeated, inspect postflop/value targets, not only preflop priors.",
                }
            )

    return hypotheses


def adjustment_policy(evidence_class: str, audit_ok: bool, claim: dict[str, Any]) -> str:
    if not audit_ok:
        return "NO_TUNE_ARTIFACT_INCOMPLETE"
    if claim.get("can_claim_l6"):
        return "L6_CANDIDATE_FORMAL_REVIEW"
    if claim.get("can_claim_l5"):
        return "L5_CANDIDATE_FORMAL_REVIEW"
    if evidence_class == "diagnostic":
        return "DIAGNOSTIC_ONLY_NO_AUTO_TUNE"
    if evidence_class == "quick_screen":
        return "SMOKE_ONLY_USE_AS_ONE_SIGNAL"
    if evidence_class == "promotion_scale":
        return "PROMOTION_SCALE_REVIEW_IF_LEAK_REPEATS"
    if evidence_class == "formal":
        return "FORMAL_LOSS_REVIEW_REQUIRED"
    return "SMALL_SAMPLE_NO_AUTO_TUNE"


def build_review(args: argparse.Namespace) -> dict[str, Any]:
    run_dir = Path(args.run_dir) if args.run_dir else Path(".")
    output_dir = Path(args.output_dir)
    if not output_dir.is_absolute():
        output_dir = REPO_ROOT / output_dir

    ci_path = resolve_path(args.ci_json)
    selected_from_scorecard: dict[str, Any] | None = None
    if ci_path is None and not args.tag:
        ci_path, selected_from_scorecard = select_ci_from_scorecard(run_dir, output_dir, args.selection, args.policy_mode)
    tag = args.tag
    if not tag and ci_path is not None:
        tag = tag_from_ci_path(ci_path) or ""
    if not tag:
        return {
            "checked_at": now_iso(),
            "overall": "MISSING_CI",
            "error": "No tag or CI summary could be selected.",
            "selection": args.selection,
        }

    paths = paths_for_tag(output_dir, tag)
    if ci_path is not None:
        paths["ci_json"] = ci_path
    if args.loss_report_json:
        paths["loss_report_json"] = resolve_path(args.loss_report_json) or paths["loss_report_json"]
    if args.artifact_audit_json:
        paths["artifact_audit_json"] = resolve_path(args.artifact_audit_json) or paths["artifact_audit_json"]

    ci = load_json(paths["ci_json"])
    loss_report = load_json(paths["loss_report_json"])
    artifact_audit = load_json(paths["artifact_audit_json"])
    if ci is None and selected_from_scorecard:
        ci = selected_from_scorecard
    if ci is None:
        return {
            "checked_at": now_iso(),
            "overall": "MISSING_CI",
            "tag": tag,
            "paths": {name: str(path) for name, path in paths.items()},
        }

    policy_mode = str(ci.get("policy_mode") or args.policy_mode or "")
    evidence_class = classify_evidence(ci, tag, policy_mode)
    claim = claim_status(ci, evidence_class, args.l6_target_bb100)
    audit_overall = (artifact_audit or {}).get("overall")
    audit_ok = audit_overall == "PASS" if artifact_audit is not None else False
    loss_ok = loss_report is not None
    overall = "PASS" if audit_ok and loss_ok else "INCOMPLETE"
    if claim.get("can_claim_l6"):
        overall = "L6_CANDIDATE"
    elif claim.get("can_claim_l5"):
        overall = "L5_CANDIDATE"

    rates = {}
    warnings: list[str] = []
    hypotheses: list[dict[str, Any]] = []
    if loss_report:
        rates = rates_summary(loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {})
        warnings = [str(item) for item in loss_report.get("warnings", []) if isinstance(item, str)]
        hypotheses = build_hypotheses(loss_report)

    bb100 = round_or_none(ci.get("bb_per_100"))
    lower = round_or_none(ci.get("lower_bound_bb_per_100"))
    baseline_delta = bb100 - args.baseline_bb100 if bb100 is not None else None
    gap_to_l6 = args.l6_target_bb100 - bb100 if bb100 is not None else None

    return {
        "checked_at": now_iso(),
        "overall": overall,
        "tag": tag,
        "selection": args.selection,
        "evidence_class": evidence_class,
        "policy_mode": policy_mode or None,
        "training_adjustment": adjustment_policy(evidence_class, audit_ok and loss_ok, claim),
        "paths": {name: str(path) for name, path in paths.items()},
        "ci": {
            "hands": ci.get("hands"),
            "bb_per_100": bb100,
            "lower_bound_bb_per_100": lower,
            "upper_bound_bb_per_100": round_or_none(ci.get("upper_bound_bb_per_100")),
            "milestone_level": ci.get("milestone_level"),
            "diagnostic": bool(ci.get("diagnostic")),
            "kind": ci.get("kind"),
            "baseline_delta_bb_per_100": round_or_none(baseline_delta),
            "gap_to_l6_bb_per_100": round_or_none(gap_to_l6),
        },
        "claim": claim,
        "artifact_audit": {
            "exists": artifact_audit is not None,
            "overall": audit_overall,
            "fail_count": (artifact_audit or {}).get("fail_count"),
            "warn_count": (artifact_audit or {}).get("warn_count"),
        },
        "loss": {
            "exists": loss_ok,
            "hands": (loss_report or {}).get("hands"),
            "bb_per_100": round_or_none((loss_report or {}).get("bb_per_100")),
            "move_records": (loss_report or {}).get("move_records"),
            "rates": rates,
            "warnings": warnings,
            "position": first_rows(loss_report or {}, "position", 4),
            "terminal": first_rows(loss_report or {}, "terminal", 6),
            "terminal_street": first_rows(loss_report or {}, "terminal_street", 8),
            "first_preflop_decision": first_rows(loss_report or {}, "first_preflop_decision", 8),
            "top_losing_preflop_lines": first_rows(loss_report or {}, "top_losing_preflop_lines", 8),
            "hole_family": first_rows(loss_report or {}, "hole_family", 8),
        },
        "loss_hypotheses": hypotheses,
        "rules": {
            "baseline_bb_per_100": args.baseline_bb100,
            "l6_target_bb_per_100": args.l6_target_bb100,
            "claim_rule": "L5/L6 requires 100k+ official greedy Slumbot hands, bb/100 > 0, and 95% CI lower > 0; L6 also needs near +11.1 bb/100.",
            "tuning_rule": "Do not tune from bb/100 alone; require complete artifacts and repeated agreement between Slumbot loss reports, probes, selector diagnostics, and health.",
        },
    }


def table(rows: list[dict[str, Any]], title: str) -> list[str]:
    lines = [title, "", "| key | hands | chips | bb/100 |", "|---|---:|---:|---:|"]
    if not rows:
        lines.append("| n/a |  |  |  |")
    for row in rows:
        lines.append(
            f"| `{row.get('key')}` | {fmt_int(row.get('hands'))} | {fmt_int(row.get('chips'))} | {fmt(row.get('bb_per_100'), 1, True)} |"
        )
    lines.append("")
    return lines


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    ci = summary.get("ci") if isinstance(summary.get("ci"), dict) else {}
    claim = summary.get("claim") if isinstance(summary.get("claim"), dict) else {}
    loss = summary.get("loss") if isinstance(summary.get("loss"), dict) else {}
    audit = summary.get("artifact_audit") if isinstance(summary.get("artifact_audit"), dict) else {}
    rates = loss.get("rates") if isinstance(loss.get("rates"), dict) else {}
    lines = [
        "# V5 Slumbot Hand Review",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Overall: **{summary.get('overall')}**",
        f"- Tag: `{summary.get('tag')}`",
        f"- Evidence class: `{summary.get('evidence_class')}`",
        f"- Policy mode: `{summary.get('policy_mode')}`",
        f"- Training adjustment: `{summary.get('training_adjustment')}`",
        "",
        "Score:",
        "",
        f"- Hands: `{fmt_int(ci.get('hands'))}`",
        f"- bb/100: `{fmt(ci.get('bb_per_100'), 3, True)}`",
        f"- 95% CI lower / upper: `{fmt(ci.get('lower_bound_bb_per_100'), 3, True)}` / `{fmt(ci.get('upper_bound_bb_per_100'), 3, True)}`",
        f"- Milestone: `{ci.get('milestone_level')}`",
        f"- Delta vs V4 baseline: `{fmt(ci.get('baseline_delta_bb_per_100'), 3, True)}` bb/100",
        f"- Gap to L6 target: `{fmt(ci.get('gap_to_l6_bb_per_100'), 3, False)}` bb/100",
        f"- Can claim L5 / L6: `{claim.get('can_claim_l5')}` / `{claim.get('can_claim_l6')}`",
        "",
        "Artifacts:",
        "",
        f"- Artifact audit: `{audit.get('overall')}`",
        f"- Loss report exists: `{loss.get('exists')}`",
        f"- Loss report hands / move records: `{fmt_int(loss.get('hands'))}` / `{fmt_int(loss.get('move_records'))}`",
        "",
        "Preflop Rates:",
        "",
        f"- SB open fold / call / raise / all-in: `{fmt(rates.get('sb_open_fold_rate'))}` / `{fmt(rates.get('sb_open_call_rate'))}` / `{fmt(rates.get('sb_open_raise_rate'))}` / `{fmt(rates.get('sb_open_allin_rate'))}`",
        f"- BB vs open call / raise: `{fmt(rates.get('bb_vs_open_call_rate'))}` / `{fmt(rates.get('bb_vs_open_raise_rate'))}`",
        "",
        "Warnings:",
        "",
    ]
    warnings = loss.get("warnings") if isinstance(loss.get("warnings"), list) else []
    if warnings:
        lines.extend(f"- {warning}" for warning in warnings[:10])
    else:
        lines.append("- none")
    lines.append("")
    lines.append("Loss hypotheses:")
    lines.append("")
    hypotheses = summary.get("loss_hypotheses") if isinstance(summary.get("loss_hypotheses"), list) else []
    if hypotheses:
        for item in hypotheses[:12]:
            lines.append(f"- `{item.get('area')}`: {item.get('evidence')} -> {item.get('training_signal')}")
    else:
        lines.append("- none")
    lines.append("")
    lines.extend(table(loss.get("position") if isinstance(loss.get("position"), list) else [], "## Position"))
    lines.extend(table(loss.get("terminal") if isinstance(loss.get("terminal"), list) else [], "## Terminal"))
    lines.extend(table(loss.get("first_preflop_decision") if isinstance(loss.get("first_preflop_decision"), list) else [], "## First Preflop Decision"))
    lines.extend(table(loss.get("top_losing_preflop_lines") if isinstance(loss.get("top_losing_preflop_lines"), list) else [], "## Top Losing Preflop Lines"))
    lines.extend(
        [
            "Rules:",
            "",
            f"- {summary.get('rules', {}).get('claim_rule')}",
            f"- {summary.get('rules', {}).get('tuning_rule')}",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a V5 Slumbot hand-review summary from saved artifacts.")
    parser.add_argument("--run-dir", default="")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--tag", default="")
    parser.add_argument("--ci-json", default="")
    parser.add_argument("--loss-report-json", default="")
    parser.add_argument("--artifact-audit-json", default="")
    parser.add_argument("--selection", choices=["official", "diagnostic", "auto"], default="official")
    parser.add_argument("--policy-mode", default="greedy")
    parser.add_argument("--baseline-bb100", type=float, default=DEFAULT_BASELINE_BB100)
    parser.add_argument("--l6-target-bb100", type=float, default=DEFAULT_L6_TARGET_BB100)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_review(args)
    print(f"overall={summary.get('overall')}")
    print(f"tag={summary.get('tag')}")
    print(f"adjustment={summary.get('training_adjustment')}")
    if args.out_json:
        write_json(Path(args.out_json), summary)
    if args.out_md:
        write_markdown(summary, Path(args.out_md))
    return 0 if summary.get("overall") not in {"MISSING_CI"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
