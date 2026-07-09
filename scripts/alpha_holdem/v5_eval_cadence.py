#!/usr/bin/env python3
"""Read-only evaluation cadence for the V5 L6 run.

This schedule makes the testing policy explicit:
- internal probes are frequent regression checks;
- quick Slumbot screens are noisy external smoke tests;
- promotion20k and formal100k are the only stages that can support promotion;
- L5/L6 claims require formal Slumbot CI evidence.
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

from v5_run_dashboard import build_summary, format_duration


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        obj = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return {}
    return obj if isinstance(obj, dict) else {}


def infer_artifact_hands_from_name(path: Path) -> int | None:
    match = re.search(r"(?:^|_)(\d+)M(?:_|$)", path.stem)
    if not match:
        return None
    return int(match.group(1)) * 1_000_000


def existing_ci(
    output_dir: Path,
    run_id: str,
    stage: str,
    *,
    target_hands: int | None = None,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    target_m_token = f"{int(target_hands or 0) // 1_000_000}M" if target_hands else ""
    for path_text in glob.glob(str(output_dir / f"bench_v55_*{run_id}*{stage}*_ci_summary.json")):
        path = Path(path_text)
        inferred_hands = infer_artifact_hands_from_name(path)
        if target_hands is not None:
            if inferred_hands is None:
                if target_m_token and target_m_token not in path.stem:
                    continue
            elif inferred_hands < int(target_hands):
                continue
        data = load_json(path)
        items.append(
            {
                "path": str(path),
                "exists": bool(data),
                "artifact_checkpoint_hands_inferred": inferred_hands,
                "hands": data.get("hands"),
                "bb_per_100": data.get("bb_per_100"),
                "lower_bound_bb_per_100": data.get("lower_bound_bb_per_100"),
                "milestone_level": data.get("milestone_level"),
                "l5_formal_win": data.get("l5_formal_win"),
                "l6_near_paper_target": data.get("l6_near_paper_target"),
            }
        )
    return sorted(items, key=lambda item: str(item.get("path")))


def milestone_targets(interval: int, until: int) -> list[int]:
    if interval <= 0 or until <= 0:
        return []
    return list(range(interval, until + 1, interval))


def min_target(args: argparse.Namespace, name: str, default: int) -> int:
    try:
        value = int(getattr(args, name, default) or default)
    except (TypeError, ValueError):
        value = default
    return max(default, value)


def targets_at_or_after(targets: list[int], minimum: int) -> list[int]:
    return [target for target in targets if target >= minimum]


def target_status(
    *,
    target_hands: int,
    checkpoint_hands: int,
    current_hands: int,
    hps: float | None,
    existing: list[dict[str, Any]],
) -> dict[str, Any]:
    remaining_checkpoint = max(0, target_hands - checkpoint_hands)
    remaining_live = max(0, target_hands - current_hands)
    eta_seconds = remaining_live / hps if hps and hps > 0 else None
    if existing:
        state = "DONE"
    elif checkpoint_hands >= target_hands:
        state = "DUE"
    else:
        state = "WAITING"
    return {
        "target_hands": target_hands,
        "state": state,
        "checkpoint_hands": checkpoint_hands,
        "current_hands": current_hands,
        "remaining_checkpoint_hands": remaining_checkpoint,
        "eta_seconds_live": eta_seconds,
        "eta_duration_live": format_duration(eta_seconds),
        "existing_ci": existing,
    }


def first_actionable(items: list[dict[str, Any]]) -> dict[str, Any] | None:
    for item in items:
        if item.get("state") in {"DUE", "WAITING"}:
            return item
    return None


def build_cadence(run_dir: Path, output_dir: Path, args: argparse.Namespace) -> dict[str, Any]:
    dashboard = build_summary(run_dir)
    run_id = dashboard.get("run_id") or run_dir.name
    training = dashboard.get("training") or {}
    checkpoint = dashboard.get("checkpoint") or {}
    current_hands = int(training.get("current_hands") or 0)
    checkpoint_hands = int(checkpoint.get("total_hands") or 0)
    hps = training.get("recent_hands_per_second")
    hps_float = float(hps) if hps else None

    min_quick_target_hands = min_target(args, "min_quick_target_hands", 50_000_000)
    min_promotion_target_hands = min_target(args, "min_promotion_target_hands", 250_000_000)
    min_formal_target_hands = min_target(args, "min_formal_target_hands", 250_000_000)

    quick_targets = targets_at_or_after(
        milestone_targets(args.quick_interval_hands, args.quick_until_hands),
        min_quick_target_hands,
    )
    quick_screens = [
        {
            "stage": "quick5k",
            "purpose": "external API/loader and coarse regression smoke; not a promotion claim",
            **target_status(
                target_hands=target,
                checkpoint_hands=checkpoint_hands,
                current_hands=current_hands,
                hps=hps_float,
                existing=existing_ci(output_dir, run_id, "quick5k", target_hands=target),
            ),
        }
        for target in quick_targets
    ]

    promotion_targets = targets_at_or_after(
        milestone_targets(args.promotion_interval_hands, args.promotion_until_hands),
        min_promotion_target_hands,
    )
    promotion_screens = [
        {
            "stage": "promotion20k",
            "purpose": "20k promotion screen; still not enough for L5/L6",
            **target_status(
                target_hands=target,
                checkpoint_hands=checkpoint_hands,
                current_hands=current_hands,
                hps=hps_float,
                existing=existing_ci(output_dir, run_id, "promotion20k", target_hands=target),
            ),
        }
        for target in promotion_targets
    ]

    formal_targets = targets_at_or_after(
        milestone_targets(args.formal_interval_hands, args.formal_until_hands),
        min_formal_target_hands,
    )
    formal_screens = [
        {
            "stage": "formal100k",
            "purpose": "formal L5/L6-eligible benchmark after promotion20k strong gate",
            **target_status(
                target_hands=target,
                checkpoint_hands=checkpoint_hands,
                current_hands=current_hands,
                hps=hps_float,
                existing=existing_ci(output_dir, run_id, "formal100k", target_hands=target),
            ),
        }
        for target in formal_targets
    ]

    internal = (dashboard.get("watchers") or {}).get("internal_strength") or {}
    next_quick = first_actionable(quick_screens)
    next_promotion = first_actionable(promotion_screens)
    next_formal = first_actionable(formal_screens)

    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "run_id": run_id,
        "current_hands": current_hands,
        "checkpoint_hands": checkpoint_hands,
        "checkpoint_iteration": checkpoint.get("iteration"),
        "recent_hands_per_second": hps,
        "internal_probe": {
            "targets": internal.get("targets"),
            "completed": internal.get("completed"),
            "latest_target": internal.get("latest_target"),
            "latest_overall": internal.get("latest_overall"),
            "next_due": internal.get("next_target"),
            "next_overall": internal.get("next_overall"),
        },
        "slumbot_quick_screens": quick_screens,
        "slumbot_promotion_screens": promotion_screens,
        "slumbot_formal_screens": formal_screens,
        "next_external_eval": next_quick or next_promotion or next_formal,
        "next_promotion_eval": next_promotion,
        "next_formal_eval": next_formal,
        "min_quick_target_hands": min_quick_target_hands,
        "min_promotion_target_hands": min_promotion_target_hands,
        "min_formal_target_hands": min_formal_target_hands,
        "policy": {
            "quick5k": f"every {args.quick_interval_hands:,} checkpoint hands from {min_quick_target_hands:,} until {args.quick_until_hands:,}",
            "promotion20k": f"every {args.promotion_interval_hands:,} checkpoint hands from {min_promotion_target_hands:,} until {args.promotion_until_hands:,}",
            "formal100k": f"every {args.formal_interval_hands:,} checkpoint hands from {min_formal_target_hands:,} until {args.formal_until_hands:,}, only after promotion20k strong gate",
            "claim_rule": "Only 100k+ Slumbot CI with bb/100 > 0 and lower bound > 0 can prove L5; L6 needs near +11.1 bb/100 formal evidence.",
        },
        "notes": [
            "This cadence artifact is read-only and does not call Slumbot by itself.",
            "The dedicated quick5k watcher is the preferred first 50M path; v5_eval_cadence_watch.py can backstop it if that launcher is skipped.",
            "v5_eval_cadence_watch.py launches due screens through guarded benchmark watchers to avoid duplicates and API contention.",
        ],
    }


def write_markdown(summary: dict[str, Any], path: Path) -> None:
    lines = [
        "# V5 Evaluation Cadence",
        "",
        f"- Checked at: `{summary.get('checked_at')}`",
        f"- Run: `{summary.get('run_id')}`",
        f"- Current hands: `{summary.get('current_hands')}`",
        f"- Checkpoint hands: `{summary.get('checkpoint_hands')}`",
        f"- Checkpoint iteration: `{summary.get('checkpoint_iteration')}`",
        "",
        "## Internal",
        "",
        f"- Next internal probe target: `{(summary.get('internal_probe') or {}).get('next_due')}`",
        f"- Completed internal probes: `{(summary.get('internal_probe') or {}).get('completed')}`",
        "",
        "## Slumbot Quick Screens",
        "",
        "| target hands | state | ETA | existing CI |",
        "|---:|---|---:|---:|",
    ]
    for item in summary.get("slumbot_quick_screens") or []:
        lines.append(
            f"| {int(item.get('target_hands') or 0):,} | {item.get('state')} | {item.get('eta_duration_live')} | {len(item.get('existing_ci') or [])} |"
        )

    lines.extend(
        [
            "",
            "## Promotion Screens",
            "",
            "| target hands | state | ETA | existing CI |",
            "|---:|---|---:|---:|",
        ]
    )
    for item in summary.get("slumbot_promotion_screens") or []:
        lines.append(
            f"| {int(item.get('target_hands') or 0):,} | {item.get('state')} | {item.get('eta_duration_live')} | {len(item.get('existing_ci') or [])} |"
        )

    lines.extend(
        [
            "",
            "## Formal Screens",
            "",
            "| target hands | state | ETA | existing CI |",
            "|---:|---|---:|---:|",
        ]
    )
    for item in summary.get("slumbot_formal_screens") or []:
        lines.append(
            f"| {int(item.get('target_hands') or 0):,} | {item.get('state')} | {item.get('eta_duration_live')} | {len(item.get('existing_ci') or [])} |"
        )

    policy = summary.get("policy") or {}
    lines.extend(
        [
            "",
            "## Policy",
            "",
            f"- quick5k: {policy.get('quick5k')}",
            f"- promotion20k: {policy.get('promotion20k')}",
            f"- formal100k: {policy.get('formal100k')}",
            f"- claim rule: {policy.get('claim_rule')}",
            "",
            "## Notes",
            "",
        ]
    )
    for note in summary.get("notes") or []:
        lines.append(f"- {note}")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a V5 evaluation cadence artifact.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output-dir", default="models")
    parser.add_argument("--quick-interval-hands", type=int, default=50_000_000)
    parser.add_argument("--quick-until-hands", type=int, default=200_000_000)
    parser.add_argument("--min-quick-target-hands", type=int, default=50_000_000)
    parser.add_argument("--promotion-interval-hands", type=int, default=250_000_000)
    parser.add_argument("--promotion-until-hands", type=int, default=1_000_000_000)
    parser.add_argument("--min-promotion-target-hands", type=int, default=250_000_000)
    parser.add_argument("--formal-interval-hands", type=int, default=250_000_000)
    parser.add_argument("--formal-until-hands", type=int, default=1_000_000_000)
    parser.add_argument("--min-formal-target-hands", type=int, default=250_000_000)
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    summary = build_cadence(Path(args.run_dir), Path(args.output_dir), args)
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
