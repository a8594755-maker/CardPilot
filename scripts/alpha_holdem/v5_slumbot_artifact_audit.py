#!/usr/bin/env python3
"""Audit saved Slumbot benchmark artifacts for a single bench_v55 tag.

This is a non-network checker. It verifies that a completed Slumbot benchmark
has the hand-level evidence and derived reports required before anyone trusts
the score or tunes training from it.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEFAULT_RATE_FIELDS = (
    "sb_open_fold_rate",
    "sb_open_call_rate",
    "sb_open_raise_rate",
    "sb_open_allin_rate",
    "bb_vs_open_call_rate",
    "bb_vs_open_raise_rate",
)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def add_check(checks: list[dict[str, str]], name: str, status: str, detail: str) -> None:
    checks.append({"name": name, "status": status, "detail": detail})


def jsonl_count(path: Path) -> tuple[int, str | None]:
    count = 0
    try:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line_no, line in enumerate(f, start=1):
                if not line.strip():
                    continue
                try:
                    json.loads(line)
                except Exception as exc:  # pragma: no cover - detail path only
                    return count, f"line {line_no}: {type(exc).__name__}: {exc}"
                count += 1
    except Exception as exc:  # pragma: no cover - detail path only
        return count, f"{type(exc).__name__}: {exc}"
    return count, None


def file_info(path: Path) -> dict[str, Any]:
    return {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
    }


def audit(args: argparse.Namespace) -> dict[str, Any]:
    output_dir = Path(args.output_dir)
    tag = str(args.tag)
    prefix = output_dir / f"bench_v55_{tag}"

    artifacts = {
        "hands_glob": str(output_dir / f"bench_v55_{tag}_part*_hands.jsonl"),
        "dump_glob": str(output_dir / f"bench_v55_{tag}_part*_dump.jsonl"),
        "ci_json": str(prefix) + "_ci_summary.json",
        "promotion_json": str(prefix) + "_promotion_gate.json",
        "promotion_md": str(prefix) + "_promotion_gate.md",
        "dump_analysis": str(prefix) + "_dump_analysis.txt",
        "loss_report_json": str(prefix) + "_loss_report.json",
        "loss_report_md": str(prefix) + "_loss_report.md",
    }

    checks: list[dict[str, str]] = []
    hand_files = [Path(p) for p in sorted(glob.glob(artifacts["hands_glob"]))]
    dump_files = [Path(p) for p in sorted(glob.glob(artifacts["dump_glob"]))]

    if hand_files:
        add_check(checks, "hand_files", "PASS", f"{len(hand_files)} file(s)")
    else:
        add_check(checks, "hand_files", "FAIL", f"no matches for {artifacts['hands_glob']}")

    if dump_files:
        add_check(checks, "dump_files", "PASS", f"{len(dump_files)} file(s)")
    else:
        add_check(checks, "dump_files", "FAIL", f"no matches for {artifacts['dump_glob']}")

    if args.expected_parts is not None:
        status = "PASS" if len(hand_files) == args.expected_parts else "FAIL"
        add_check(checks, "expected_hand_parts", status, f"{len(hand_files)} vs expected {args.expected_parts}")
        status = "PASS" if len(dump_files) == args.expected_parts else "FAIL"
        add_check(checks, "expected_dump_parts", status, f"{len(dump_files)} vs expected {args.expected_parts}")
    else:
        status = "PASS" if len(hand_files) >= args.min_parts else "FAIL"
        add_check(checks, "min_hand_parts", status, f"{len(hand_files)} vs min {args.min_parts}")
        status = "PASS" if len(dump_files) >= args.min_parts else "FAIL"
        add_check(checks, "min_dump_parts", status, f"{len(dump_files)} vs min {args.min_parts}")

    hand_counts: dict[str, int] = {}
    dump_counts: dict[str, int] = {}
    hand_parse_errors: dict[str, str] = {}
    dump_parse_errors: dict[str, str] = {}

    for path in hand_files:
        count, error = jsonl_count(path)
        hand_counts[str(path)] = count
        if error:
            hand_parse_errors[str(path)] = error
    for path in dump_files:
        count, error = jsonl_count(path)
        dump_counts[str(path)] = count
        if error:
            dump_parse_errors[str(path)] = error

    total_hands = sum(hand_counts.values())
    total_decisions = sum(dump_counts.values())
    add_check(
        checks,
        "hand_jsonl_parse",
        "PASS" if not hand_parse_errors else "FAIL",
        "valid JSONL" if not hand_parse_errors else f"{len(hand_parse_errors)} parse error(s)",
    )
    add_check(
        checks,
        "dump_jsonl_parse",
        "PASS" if not dump_parse_errors else "FAIL",
        "valid JSONL" if not dump_parse_errors else f"{len(dump_parse_errors)} parse error(s)",
    )
    add_check(
        checks,
        "min_hands",
        "PASS" if total_hands >= args.min_hands else "FAIL",
        f"{total_hands} vs min {args.min_hands}",
    )
    if args.expected_hands is not None:
        add_check(
            checks,
            "expected_hands",
            "PASS" if total_hands == args.expected_hands else "FAIL",
            f"{total_hands} vs expected {args.expected_hands}",
        )
    add_check(
        checks,
        "decision_dump_nonempty",
        "PASS" if total_decisions > 0 else "FAIL",
        f"{total_decisions} decision row(s)",
    )

    ci_json_path = Path(artifacts["ci_json"])
    promotion_json_path = Path(artifacts["promotion_json"])
    promotion_md_path = Path(artifacts["promotion_md"])
    dump_analysis_path = Path(artifacts["dump_analysis"])
    loss_report_json_path = Path(artifacts["loss_report_json"])
    loss_report_md_path = Path(artifacts["loss_report_md"])

    fixed_paths = {
        "ci_json": ci_json_path,
        "promotion_json": promotion_json_path,
        "promotion_md": promotion_md_path,
        "dump_analysis": dump_analysis_path,
        "loss_report_json": loss_report_json_path,
        "loss_report_md": loss_report_md_path,
    }
    for name, path in fixed_paths.items():
        add_check(checks, name, "PASS" if path.exists() else "FAIL", str(path))

    ci_summary: dict[str, Any] = {}
    if ci_json_path.exists():
        try:
            loaded = load_json(ci_json_path)
            ci_summary = loaded if isinstance(loaded, dict) else {}
            add_check(checks, "ci_json_load", "PASS", "loaded")
        except Exception as exc:
            add_check(checks, "ci_json_load", "FAIL", f"{type(exc).__name__}: {exc}")
    else:
        add_check(checks, "ci_json_load", "FAIL", "missing")

    ci_hands = ci_summary.get("hands")
    if isinstance(ci_hands, int):
        add_check(
            checks,
            "ci_hands_match_hand_jsonl",
            "PASS" if ci_hands == total_hands else "FAIL",
            f"ci={ci_hands}; hand_jsonl={total_hands}",
        )
    else:
        add_check(checks, "ci_hands_match_hand_jsonl", "FAIL", f"ci hands unavailable: {ci_hands!r}")

    input_files = ci_summary.get("input_files") if isinstance(ci_summary.get("input_files"), list) else []
    if input_files:
        missing_inputs = [p for p in input_files if not Path(str(p)).exists()]
        add_check(
            checks,
            "ci_input_files_exist",
            "PASS" if not missing_inputs else "FAIL",
            "all exist" if not missing_inputs else f"{len(missing_inputs)} missing",
        )
    else:
        add_check(checks, "ci_input_files_exist", "WARN", "ci input_files empty or unavailable")

    promotion_summary: dict[str, Any] = {}
    if promotion_json_path.exists():
        try:
            loaded = load_json(promotion_json_path)
            promotion_summary = loaded if isinstance(loaded, dict) else {}
            add_check(checks, "promotion_json_load", "PASS", "loaded")
        except Exception as exc:
            add_check(checks, "promotion_json_load", "FAIL", f"{type(exc).__name__}: {exc}")

    loss_report: dict[str, Any] = {}
    if loss_report_json_path.exists():
        try:
            loaded = load_json(loss_report_json_path)
            loss_report = loaded if isinstance(loaded, dict) else {}
            add_check(checks, "loss_report_json_load", "PASS", "loaded")
        except Exception as exc:
            add_check(checks, "loss_report_json_load", "FAIL", f"{type(exc).__name__}: {exc}")
    else:
        add_check(checks, "loss_report_json_load", "FAIL", "missing")

    loss_hands = loss_report.get("hands")
    if isinstance(loss_hands, int):
        add_check(
            checks,
            "loss_report_hands_match_hand_jsonl",
            "PASS" if loss_hands == total_hands else "FAIL",
            f"loss={loss_hands}; hand_jsonl={total_hands}",
        )
    else:
        add_check(checks, "loss_report_hands_match_hand_jsonl", "FAIL", f"loss hands unavailable: {loss_hands!r}")

    rates = loss_report.get("rates") if isinstance(loss_report.get("rates"), dict) else {}
    missing_rate_fields = [field for field in args.require_rate_field if rates.get(field) is None]
    add_check(
        checks,
        "loss_report_required_rates",
        "PASS" if not missing_rate_fields else "FAIL",
        "all required rates present" if not missing_rate_fields else ", ".join(missing_rate_fields),
    )

    fail_count = sum(1 for check in checks if check["status"] == "FAIL")
    warn_count = sum(1 for check in checks if check["status"] == "WARN")
    overall = "PASS" if fail_count == 0 else "FAIL"

    return {
        "checked_at": now_iso(),
        "overall": overall,
        "tag": tag,
        "output_dir": str(output_dir),
        "artifacts": artifacts,
        "checks": checks,
        "fail_count": fail_count,
        "warn_count": warn_count,
        "hand_files": [file_info(path) | {"jsonl_rows": hand_counts.get(str(path), 0)} for path in hand_files],
        "dump_files": [file_info(path) | {"jsonl_rows": dump_counts.get(str(path), 0)} for path in dump_files],
        "hand_parse_errors": hand_parse_errors,
        "dump_parse_errors": dump_parse_errors,
        "total_hands": total_hands,
        "total_decisions": total_decisions,
        "ci_summary": {
            "hands": ci_summary.get("hands"),
            "bb_per_100": ci_summary.get("bb_per_100"),
            "lower_bound_bb_per_100": ci_summary.get("lower_bound_bb_per_100"),
            "upper_bound_bb_per_100": ci_summary.get("upper_bound_bb_per_100"),
            "milestone_level": ci_summary.get("milestone_level"),
        },
        "promotion_summary": {
            "overall": promotion_summary.get("overall"),
            "health_overall": promotion_summary.get("health_overall"),
        },
        "loss_report_summary": {
            "hands": loss_report.get("hands"),
            "bb_per_100": loss_report.get("bb_per_100"),
            "rates": {field: rates.get(field) for field in args.require_rate_field},
            "warning_count": len(loss_report.get("warnings") or []) if isinstance(loss_report.get("warnings"), list) else None,
        },
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Slumbot Artifact Audit",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Overall: **{summary.get('overall')}**",
        f"- Tag: `{summary.get('tag')}`",
        f"- Hands / decisions: `{summary.get('total_hands')}` / `{summary.get('total_decisions')}`",
        f"- Fails / warnings: `{summary.get('fail_count')}` / `{summary.get('warn_count')}`",
        "",
        "## Score",
        "",
        f"- bb/100: `{summary.get('ci_summary', {}).get('bb_per_100')}`",
        f"- CI lower / upper: `{summary.get('ci_summary', {}).get('lower_bound_bb_per_100')}` / `{summary.get('ci_summary', {}).get('upper_bound_bb_per_100')}`",
        f"- Milestone: `{summary.get('ci_summary', {}).get('milestone_level')}`",
        "",
        "## Loss Rates",
        "",
    ]
    rates = summary.get("loss_report_summary", {}).get("rates") or {}
    for key, value in rates.items():
        lines.append(f"- {key}: `{value}`")
    lines.extend(["", "## Checks", ""])
    for check in summary.get("checks", []):
        lines.append(f"- {check.get('status')}: `{check.get('name')}` - {check.get('detail')}")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True, help="Benchmark tag without the bench_v55_ prefix.")
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--min-parts", type=int, default=1)
    parser.add_argument("--expected-parts", type=int)
    parser.add_argument("--min-hands", type=int, default=1)
    parser.add_argument("--expected-hands", type=int)
    parser.add_argument("--require-rate-field", action="append", default=None)
    parser.add_argument("--out-json", required=True)
    parser.add_argument("--out-md", required=True)
    args = parser.parse_args(argv)
    if args.require_rate_field is None:
        args.require_rate_field = list(DEFAULT_RATE_FIELDS)
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    summary = audit(args)
    out_json = Path(args.out_json)
    out_md = Path(args.out_md)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    write_markdown(summary, out_md)
    print(f"overall={summary['overall']} tag={summary['tag']} hands={summary['total_hands']} decisions={summary['total_decisions']}")
    return 0 if summary["overall"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
