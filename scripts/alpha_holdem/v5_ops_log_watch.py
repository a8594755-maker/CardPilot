#!/usr/bin/env python3
"""Append mandatory V5 Ops-log rows for completed gate monitoring windows.

This watcher is reporting-only. It reads post-gate review artifacts and appends
one idempotent row per completed 100-gate monitoring window to
reports/v5_experiment_ledger.md. It never touches trainer state, checkpoints,
model weights, or evaluator launches.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python 3.9+ normally has zoneinfo.
    ZoneInfo = None  # type: ignore[assignment]


COMPLETED_REVIEW_STATES = {
    "REVIEW_REQUIRED_NO_AUTO_RESTART",
    "REVIEW_COMPLETE",
}
EXP003_JUDGMENT_TARGET_HANDS = 408_064_575


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def now_edt_label() -> str:
    if ZoneInfo is not None:
        return datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M")
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001 - diagnostics should survive bad artifacts.
        return {"_load_error": str(exc), "_path": str(path)}
    return payload if isinstance(payload, dict) else {"_load_error": "JSON root is not an object"}


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def as_rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve())).replace("\\", "/")
    except Exception:
        return str(path).replace("\\", "/")


def clean_cell(text: Any) -> str:
    return str(text).replace("|", "/").replace("\r", " ").replace("\n", " ")


def append_event_row(
    ledger_path: Path,
    *,
    event_id: str,
    title: str,
    detail: str,
    dry_run: bool,
) -> dict[str, Any]:
    """Append one idempotent UTF-8 event row without rewriting ledger history."""

    ledger_text = ledger_path.read_text(encoding="utf-8", errors="replace") if ledger_path.exists() else ""
    marker = f"[event_id={clean_cell(event_id)}]"
    if marker in ledger_text:
        return {"appended": False, "reason": "already_logged", "event_id": event_id, "row": None}
    row = f"| {now_edt_label()} | {clean_cell(title)} | {clean_cell(detail)} {marker} |"
    if not dry_run:
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
            if ledger_text and not ledger_text.endswith("\n"):
                handle.write("\n")
            handle.write(row + "\n")
    return {"appended": True, "reason": "dry_run" if dry_run else "appended", "event_id": event_id, "row": row}


def reconcile_status_fields(
    ledger_path: Path,
    spec_path: Path,
    *,
    dry_run: bool,
) -> dict[str, Any]:
    """Replace only explicitly authorized entry-status bytes.

    The Ops table remains append-only.  Byte-level replacement is used because
    a historical incident left one mixed-encoding row that must not be decoded,
    normalized, or rewritten semantically.
    """

    spec = load_json(spec_path)
    replacements = spec.get("replacements") if isinstance(spec.get("replacements"), list) else []
    if not replacements:
        return {"overall": "FAIL", "reason": "no replacements in spec", "checks": []}
    original = ledger_path.read_bytes()
    checks: list[dict[str, Any]] = []
    encoded: list[tuple[bytes, bytes]] = []
    for item in replacements:
        if not isinstance(item, dict):
            checks.append({"status": "FAIL", "detail": "replacement is not an object"})
            continue
        old = str(item.get("old") or "").encode("utf-8")
        new = str(item.get("new") or "").encode("utf-8")
        count = original.count(old) if old else 0
        status = "PASS" if old and new and count == 1 else "FAIL"
        checks.append(
            {
                "status": status,
                "count": count,
                "old": old.decode("utf-8", errors="replace"),
                "new": new.decode("utf-8", errors="replace"),
            }
        )
        if status == "PASS":
            encoded.append((old, new))
    if len(encoded) != len(replacements):
        return {"overall": "FAIL", "reason": "replacement precondition failed", "checks": checks}
    updated = original
    for old, new in encoded:
        updated = updated.replace(old, new, 1)
    if not dry_run:
        ledger_path.write_bytes(updated)
    return {
        "overall": "PASS",
        "reason": "dry_run" if dry_run else "status_fields_updated",
        "checks": checks,
        "original_bytes": len(original),
        "updated_bytes": len(updated),
    }


def review_target(path: Path, review: dict[str, Any]) -> int | None:
    target = review.get("target_iteration")
    if isinstance(target, int):
        return target
    name = path.name
    prefix = "v5_post_gate_review_"
    suffix = ".json"
    if name.startswith(prefix) and name.endswith(suffix):
        try:
            return int(name[len(prefix) : -len(suffix)])
        except ValueError:
            return None
    return None


def is_completed_review(review: dict[str, Any]) -> bool:
    gate = review.get("gate") if isinstance(review.get("gate"), dict) else {}
    return review.get("overall") in COMPLETED_REVIEW_STATES and gate.get("overall") == "PASS"


def ledger_has_gate_row(ledger_text: str, target: int) -> bool:
    """Return true only for a completed-evidence row, not a pending gate row."""

    return (
        f"| monitoring window gate_{target} |" in ledger_text
        or f"gate_{target} evidence update" in ledger_text
    )


def fmt_float(value: Any, digits: int = 3) -> str | None:
    try:
        return f"{float(value):.{digits}f}"
    except Exception:
        return None


def exp004_note(review: dict[str, Any], exp004_target_hands: int | None) -> str:
    if not exp004_target_hands:
        return "EXP-004 status not inferred by ops watcher."
    gate = review.get("gate") if isinstance(review.get("gate"), dict) else {}
    checkpoint_hands = gate.get("checkpoint_hands") or review.get("gate_checkpoint_hands")
    try:
        remaining = int(exp004_target_hands) - int(checkpoint_hands)
    except Exception:
        return f"EXP-004 step-1 target {exp004_target_hands:,} checkpoint hands; status requires separate judgment."
    if remaining > 0:
        return (
            f"EXP-004 step-1 remains unjudged "
            f"(checkpoint {int(checkpoint_hands):,} vs {int(exp004_target_hands):,} target, {remaining:,} remaining)"
        )
    return (
        f"EXP-004 step-1 target reached "
        f"(checkpoint {int(checkpoint_hands):,} >= {int(exp004_target_hands):,}); judge by registered mirror-eval gate before EXP-002 cutover"
    )


def build_gate_row(
    target: int,
    review_path: Path,
    review: dict[str, Any],
    exp004_target_hands: int | None,
) -> str:
    gate = review.get("gate") if isinstance(review.get("gate"), dict) else {}
    health = review.get("health") if isinstance(review.get("health"), dict) else {}
    internal = review.get("internal_probe") if isinstance(review.get("internal_probe"), dict) else {}
    preflop = review.get("preflop_probe") if isinstance(review.get("preflop_probe"), dict) else {}
    checkpoint_delta = review.get("checkpoint_delta") if isinstance(review.get("checkpoint_delta"), dict) else {}
    slumbot = review.get("slumbot_trend") if isinstance(review.get("slumbot_trend"), dict) else {}

    checkpoint_iter = gate.get("checkpoint_iteration") or review.get("gate_checkpoint_iteration")
    checkpoint_hands = gate.get("checkpoint_hands") or review.get("gate_checkpoint_hands")
    live_iter = gate.get("live_iteration") or review.get("gate_live_iteration")
    live_hands = gate.get("live_hands") or review.get("gate_live_hands")
    health_overall = health.get("overall")
    entropy = fmt_float(health.get("entropy"), 3)
    vloss = fmt_float(health.get("value_loss"), 3)

    if checkpoint_iter == live_iter and checkpoint_hands == live_hands:
        pass_text = f"PASS at checkpoint/live {checkpoint_iter}, {checkpoint_hands:,} hands"
    else:
        pass_text = (
            f"PASS at checkpoint {checkpoint_iter}, {checkpoint_hands:,} hands; "
            f"live {live_iter}, {live_hands:,} hands"
        )

    health_bits = [f"health {health_overall}"]
    if entropy is not None:
        health_bits.append(f"entropy {entropy}")
    if vloss is not None:
        health_bits.append(f"vloss {vloss}")

    internal_state = internal.get("state")
    internal_detail = ""
    if internal_state == "COMPLETED":
        internal_detail = (
            f"internal probe {target} completed with `{internal.get('latest_l6_verdict')}`"
        )
    elif internal_state == "NOT_SCHEDULED":
        internal_detail = f"internal probe NOT_SCHEDULED for {target}"
    else:
        internal_detail = f"internal probe {target} state `{internal_state}`"

    latest_official = slumbot.get("latest_official_bb100")
    latest_ci_lower = slumbot.get("latest_official_ci_lower")
    latest_hands = slumbot.get("latest_official_hands")
    official_text = (
        f"Latest official Slumbot unchanged/inherited {latest_hands} hands at "
        f"{latest_official} bb/100, CI lower {latest_ci_lower}, no strength claim"
    )

    detail_parts = [f"Detail `{as_rel(review_path)}`"]
    internal_json = review_path.with_name(f"internal_strength_probe_iter{target}_200h.json")
    if internal_state == "COMPLETED" and internal_json.exists():
        detail_parts.append(f"internal detail `{as_rel(internal_json)}`")

    run_id = review_path.parent.name
    if "exp003" in run_id.lower():
        try:
            remaining = max(0, EXP003_JUDGMENT_TARGET_HANDS - int(checkpoint_hands))
        except Exception:
            remaining = None
        internal_delta_mean = fmt_float(internal.get("latest_l6_delta_mean_bb100"), 3)
        internal_delta_lower = fmt_float(internal.get("latest_l6_delta_lower_bb100"), 3)
        delta_text = (
            f", delta mean/lower {internal_delta_mean} / {internal_delta_lower} bb/100"
            if internal_delta_mean is not None and internal_delta_lower is not None
            else ""
        )
        target_text = (
            f"fixed EXP-003 causal mirror bundle remains blocked until checkpoint hands "
            f">={EXP003_JUDGMENT_TARGET_HANDS:,} ({remaining:,} checkpoint hands remaining)"
            if remaining is not None and remaining > 0
            else (
                f"fixed EXP-003 causal mirror bundle is eligible at checkpoint hands "
                f">={EXP003_JUDGMENT_TARGET_HANDS:,}; follow the registered three-role protocol"
            )
        )
        note = (
            f"Evidence refresh completed for EXP-003 bounded-K run {run_id}: {pass_text}; "
            f"{', '.join(health_bits)}. Post-gate review `{review.get('overall')}`; "
            f"{internal_detail}{delta_text}; preflop {preflop.get('overall')} with "
            f"{preflop.get('warning_count')} warnings; checkpoint_delta "
            f"`{checkpoint_delta.get('overall')}`. {official_text}. Experiments retained: "
            f"EXP-002 multi-env, EXP-003 mirrored deals + bounded-K=200 all-in EV, and "
            f"EXP-004 stable prior floor 0.01/0.02; no prior decay. {target_text}. "
            f"Internal probes remain local smoke evidence only; no V4/L5/L6 strength claim. "
            f"{'; '.join(detail_parts)}."
        )
        title = f"EXP-003 run gate_{target} evidence update"
    else:
        note = (
            f"{pass_text}; {', '.join(health_bits)}. "
            f"Post-gate review `{review.get('overall')}`; {internal_detail}; "
            f"preflop {preflop.get('overall')} {preflop.get('warning_count')} and "
            f"checkpoint_delta `{checkpoint_delta.get('overall')}`. "
            f"{official_text}. {exp004_note(review, exp004_target_hands)}; "
            f"EXP-002 cutover remains blocked until EXP-004 step-1 registered-gate judgment plus gate PASS. "
            f"{'; '.join(detail_parts)}."
        )
        title = f"monitoring window gate_{target}"
    return f"| {now_edt_label()} | {title} | {clean_cell(note)} |"


def scan_once(
    run_dir: Path,
    ledger_path: Path,
    exp004_target_hands: int | None,
    dry_run: bool,
) -> dict[str, Any]:
    # The 2026-07-08 incident left a historical mixed-encoding row.  Read with
    # replacement so new rows can still be appended as UTF-8 without rewriting
    # or normalizing any historical bytes.
    ledger_text = ledger_path.read_text(encoding="utf-8", errors="replace") if ledger_path.exists() else ""
    appended: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []

    for review_path in sorted(
        run_dir.glob("v5_post_gate_review_*.json"),
        key=lambda p: review_target(p, load_json(p)) or -1,
    ):
        review = load_json(review_path)
        target = review_target(review_path, review)
        if target is None:
            skipped.append({"path": as_rel(review_path), "reason": "target_unknown"})
            continue
        if not is_completed_review(review):
            pending.append(
                {
                    "target": target,
                    "path": as_rel(review_path),
                    "overall": review.get("overall"),
                    "gate_overall": (review.get("gate") or {}).get("overall") if isinstance(review.get("gate"), dict) else None,
                }
            )
            continue
        if ledger_has_gate_row(ledger_text, target):
            skipped.append({"target": target, "path": as_rel(review_path), "reason": "already_logged"})
            continue

        row = build_gate_row(target, review_path, review, exp004_target_hands)
        appended.append({"target": target, "path": as_rel(review_path), "row": row, "dry_run": dry_run})
        if not dry_run:
            with ledger_path.open("a", encoding="utf-8", newline="\n") as handle:
                if ledger_text and not ledger_text.endswith("\n"):
                    handle.write("\n")
                handle.write(row + "\n")
            ledger_text += ("\n" if ledger_text and not ledger_text.endswith("\n") else "") + row + "\n"

    return {
        "checked_at": now_iso(),
        "run_dir": as_rel(run_dir),
        "ledger": as_rel(ledger_path),
        "dry_run": dry_run,
        "appended_count": len(appended),
        "appended": appended,
        "skipped_count": len(skipped),
        "skipped": skipped[-20:],
        "pending_count": len(pending),
        "pending": pending[-20:],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--ledger", default="reports/v5_experiment_ledger.md")
    parser.add_argument("--status-json", default="")
    parser.add_argument("--poll-seconds", type=float, default=120.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--exp004-target-hands", type=int, default=0)
    parser.add_argument("--event-id", default="")
    parser.add_argument("--event-title", default="")
    parser.add_argument("--event-detail", default="")
    parser.add_argument("--status-reconciliation-json", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    ledger_path = Path(args.ledger)
    status_json = Path(args.status_json) if args.status_json else run_dir / "v5_ops_log_watch_status.json"
    exp004_target_hands = args.exp004_target_hands or None

    if args.status_reconciliation_json:
        reconciliation = reconcile_status_fields(
            ledger_path,
            Path(args.status_reconciliation_json),
            dry_run=args.dry_run,
        )
        status = {
            "checked_at": now_iso(),
            "ledger": as_rel(ledger_path),
            "dry_run": args.dry_run,
            "status_reconciliation": reconciliation,
        }
        write_json(status_json, status)
        print(
            f"{status['checked_at']} status_reconciliation={reconciliation['overall']} "
            f"dry_run={args.dry_run}",
            flush=True,
        )
        return 0 if reconciliation["overall"] == "PASS" else 1

    if args.event_id:
        if not args.event_title or not args.event_detail:
            parser.error("--event-id requires --event-title and --event-detail")
        event = append_event_row(
            ledger_path,
            event_id=args.event_id,
            title=args.event_title,
            detail=args.event_detail,
            dry_run=args.dry_run,
        )
        status = {
            "checked_at": now_iso(),
            "run_dir": as_rel(run_dir),
            "ledger": as_rel(ledger_path),
            "dry_run": args.dry_run,
            "event": event,
        }
        write_json(status_json, status)
        print(f"{status['checked_at']} event={args.event_id} appended={event['appended']}", flush=True)
        return 0

    while True:
        status = scan_once(run_dir, ledger_path, exp004_target_hands, args.dry_run)
        write_json(status_json, status)
        print(
            f"{status['checked_at']} appended={status['appended_count']} "
            f"pending={status['pending_count']} dry_run={args.dry_run}",
            flush=True,
        )
        if args.once:
            return 0
        time.sleep(max(1.0, args.poll_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
