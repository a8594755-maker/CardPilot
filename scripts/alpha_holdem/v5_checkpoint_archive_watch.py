#!/usr/bin/env python3
"""Archive V5 checkpoints at hand-count milestones.

The trainer overwrites latest.pt. This watcher preserves immutable milestone
checkpoints for future Slumbot re-runs, internal comparisons, and audit trails.
It is read-only with respect to training and only writes archive artifacts.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch


DEFAULT_MILESTONES = [
    50_000_000,
    100_000_000,
    250_000_000,
    500_000_000,
    1_000_000_000,
    1_500_000_000,
    2_000_000_000,
    2_700_000_000,
]

EXPECTED_METADATA = {
    "version": "v5.zero",
    "env_version": "v55",
    "obs_version": "v55",
    "action_space_version": "9slot_v5",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


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


def checkpoint_summary(path: Path) -> dict[str, Any]:
    ckpt = load_checkpoint(path)
    if ckpt.get("_missing") or ckpt.get("_load_error"):
        return ckpt
    pool = ckpt.get("pool_snapshots") or []
    pool_hands = []
    if isinstance(pool, list):
        for item in pool:
            if isinstance(item, dict):
                pool_hands.append(item.get("hands", item.get("total_hands")))
    return {
        "path": str(path),
        "iteration": ckpt.get("iteration"),
        "total_hands": ckpt.get("total_hands"),
        "run_id": ckpt.get("run_id"),
        "version": ckpt.get("version"),
        "env_version": ckpt.get("env_version"),
        "obs_version": ckpt.get("obs_version"),
        "action_space_version": ckpt.get("action_space_version"),
        "starting_stack_bb": ckpt.get("starting_stack_bb"),
        "actual_hand_accounting": ckpt.get("actual_hand_accounting"),
        "fresh_from_zero_lineage": ckpt.get("fresh_from_zero_lineage"),
        "pool_snapshots": len(pool) if isinstance(pool, list) else 0,
        "pool_hands": pool_hands,
        "file_size": path.stat().st_size if path.exists() else None,
    }


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fp:
        for chunk in iter(lambda: fp.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_milestones(values: list[str] | None) -> list[int]:
    if not values:
        return DEFAULT_MILESTONES[:]
    parsed = []
    for value in values:
        text = str(value).replace(",", "").strip().lower()
        if text.endswith("b"):
            parsed.append(int(float(text[:-1]) * 1_000_000_000))
        elif text.endswith("m"):
            parsed.append(int(float(text[:-1]) * 1_000_000))
        else:
            parsed.append(int(text))
    return sorted(set(parsed))


def milestone_label(hands: int) -> str:
    if hands % 1_000_000_000 == 0:
        return f"{hands // 1_000_000_000}B"
    if hands >= 1_000_000_000:
        return f"{hands / 1_000_000_000:.1f}B".replace(".", "p")
    if hands % 1_000_000 == 0:
        return f"{hands // 1_000_000}M"
    return str(hands)


def archive_run_token(run_id: str) -> str:
    safe = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in run_id)
    if len(safe) <= 40:
        return safe
    digest = hashlib.sha256(run_id.encode("utf-8")).hexdigest()[:12]
    return f"{safe[:12]}_{digest}"


def archive_paths(archive_dir: Path, run_id: str, milestone_hands: int, iteration: Any, total_hands: int) -> tuple[Path, Path]:
    label = milestone_label(milestone_hands)
    hand_m = total_hands // 1_000_000
    iter_part = f"iter{iteration}" if iteration is not None else "iterna"
    stem = f"{archive_run_token(run_id)}_{label}_{iter_part}_{hand_m}M"
    return archive_dir / f"{stem}.pt", archive_dir / f"{stem}.json"


def inherited_parent_summary(run_dir: Path) -> dict[str, Any]:
    """Return the checkpoint this continuation inherited from, if any.

    Continuation runs may start with total_hands already above early milestones.
    Those milestones belong to the parent lineage; copying latest.pt again under
    50M/100M names in the child run creates misleading duplicate archives.
    """
    manifest = load_json(run_dir / "run_manifest.json")
    if manifest.get("_missing") or manifest.get("_load_error"):
        return {"available": False, "reason": "run_manifest unavailable", "manifest": manifest}

    candidates: list[str] = []
    for key in ("lineage_parent_checkpoint",):
        value = manifest.get(key)
        if isinstance(value, str) and value:
            candidates.append(value)
    config = manifest.get("config") if isinstance(manifest.get("config"), dict) else {}
    value = config.get("resume")
    if isinstance(value, str) and value:
        candidates.append(value)

    seen: set[str] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        path = Path(candidate)
        if not path.exists():
            continue
        summary = checkpoint_summary(path)
        if summary.get("_missing") or summary.get("_load_error"):
            continue
        total_hands = int(summary.get("total_hands") or 0)
        if total_hands > 0:
            return {"available": True, "path": str(path), "total_hands": total_hands, "checkpoint": summary}

    return {"available": False, "reason": "no usable parent checkpoint", "candidates": candidates}


def inherited_result(milestone_hands: int, parent: dict[str, Any]) -> dict[str, Any]:
    checkpoint = parent.get("checkpoint") if isinstance(parent.get("checkpoint"), dict) else {}
    return {
        "checked_at": now_iso(),
        "milestone_hands": milestone_hands,
        "overall": "INHERITED_PARENT",
        "reason": (
            f"milestone {milestone_hands:,} was already reached by parent checkpoint "
            f"at {int(parent.get('total_hands') or 0):,} hands"
        ),
        "parent_checkpoint": checkpoint,
        "parent_checkpoint_path": parent.get("path"),
        "source": checkpoint,
        "checks": [
            {
                "name": "continuation_parent_milestone",
                "status": "PASS",
                "detail": (
                    f"parent hands {int(parent.get('total_hands') or 0):,} >= "
                    f"milestone {milestone_hands:,}; not re-archiving in child run"
                ),
            }
        ],
    }


def validate_summary(summary: dict[str, Any], milestone_hands: int) -> list[dict[str, str]]:
    checks: list[dict[str, str]] = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"name": name, "status": status, "detail": detail})

    if summary.get("_missing"):
        add("checkpoint_load", "PENDING", "checkpoint missing")
        return checks
    if summary.get("_load_error"):
        add("checkpoint_load", "PENDING", str(summary["_load_error"]))
        return checks
    add("checkpoint_load", "PASS", "checkpoint loaded")

    for key, expected in EXPECTED_METADATA.items():
        actual = summary.get(key)
        if actual == expected:
            add(key, "PASS", f"{key}={actual}")
        else:
            add(key, "FAIL", f"{key}={actual!r}, expected {expected!r}")

    if float(summary.get("starting_stack_bb") or 0.0) == 200.0:
        add("starting_stack_bb", "PASS", "starting_stack_bb=200.0")
    else:
        add("starting_stack_bb", "FAIL", f"starting_stack_bb={summary.get('starting_stack_bb')!r}")

    if summary.get("actual_hand_accounting") is True:
        add("actual_hand_accounting", "PASS", "actual_hand_accounting=True")
    else:
        add("actual_hand_accounting", "FAIL", f"actual_hand_accounting={summary.get('actual_hand_accounting')!r}")

    if summary.get("fresh_from_zero_lineage") is True:
        add("fresh_from_zero_lineage", "PASS", "fresh_from_zero_lineage=True")
    else:
        add("fresh_from_zero_lineage", "FAIL", f"fresh_from_zero_lineage={summary.get('fresh_from_zero_lineage')!r}")

    total_hands = int(summary.get("total_hands") or 0)
    if total_hands >= milestone_hands:
        add("milestone_hands", "PASS", f"checkpoint hands {total_hands:,} >= {milestone_hands:,}")
    else:
        add("milestone_hands", "PENDING", f"checkpoint hands {total_hands:,} < {milestone_hands:,}")

    return checks


def overall_from_checks(checks: list[dict[str, str]]) -> str:
    if any(c["status"] == "FAIL" for c in checks):
        return "FAIL"
    if any(c["status"] == "PENDING" for c in checks):
        return "PENDING"
    return "READY"


def archive_checkpoint(
    source_path: Path,
    archive_dir: Path,
    milestone_hands: int,
    *,
    compute_sha256: bool,
    force: bool,
    retries: int,
) -> dict[str, Any]:
    source = checkpoint_summary(source_path)
    checks = validate_summary(source, milestone_hands)
    readiness = overall_from_checks(checks)
    if readiness != "READY":
        return {
            "checked_at": now_iso(),
            "milestone_hands": milestone_hands,
            "overall": readiness,
            "source": source,
            "checks": checks,
        }

    run_id = str(source.get("run_id") or "unknown_run")
    iteration = source.get("iteration")
    total_hands = int(source.get("total_hands") or 0)
    archive_pt, manifest_path = archive_paths(archive_dir, run_id, milestone_hands, iteration, total_hands)

    if manifest_path.exists() and archive_pt.exists() and not force:
        manifest = load_json(manifest_path)
        return {
            "checked_at": now_iso(),
            "milestone_hands": milestone_hands,
            "overall": "SKIPPED_EXISTS",
            "archive_path": str(archive_pt),
            "manifest_path": str(manifest_path),
            "existing_manifest": manifest,
            "source": source,
            "checks": checks,
        }

    archive_dir.mkdir(parents=True, exist_ok=True)
    last_error = ""
    copied_summary: dict[str, Any] = {}
    for attempt in range(1, retries + 1):
        try:
            shutil.copy2(source_path, archive_pt)
            copied_summary = checkpoint_summary(archive_pt)
            compare_keys = [
                "iteration",
                "total_hands",
                "version",
                "env_version",
                "obs_version",
                "action_space_version",
                "starting_stack_bb",
                "actual_hand_accounting",
                "fresh_from_zero_lineage",
            ]
            mismatches = [
                f"{key}: copied={copied_summary.get(key)!r} source={source.get(key)!r}"
                for key in compare_keys
                if copied_summary.get(key) != source.get(key)
            ]
            if mismatches:
                raise RuntimeError("; ".join(mismatches))
            break
        except Exception as exc:
            last_error = str(exc)
            time.sleep(min(5, attempt))
    else:
        return {
            "checked_at": now_iso(),
            "milestone_hands": milestone_hands,
            "overall": "FAIL",
            "source": source,
            "archive_path": str(archive_pt),
            "manifest_path": str(manifest_path),
            "checks": checks + [{"name": "archive_copy", "status": "FAIL", "detail": last_error}],
        }

    archive_manifest = {
        "archived_at": now_iso(),
        "milestone_hands": milestone_hands,
        "milestone_label": milestone_label(milestone_hands),
        "source_path": str(source_path),
        "archive_path": str(archive_pt),
        "source": source,
        "copied": copied_summary,
        "checks": checks + [{"name": "archive_copy", "status": "PASS", "detail": f"copied and reloaded {archive_pt}"}],
    }
    if compute_sha256:
        archive_manifest["sha256"] = sha256_file(archive_pt)
    write_json(manifest_path, archive_manifest)
    return {
        "checked_at": now_iso(),
        "milestone_hands": milestone_hands,
        "overall": "PASS",
        "archive_path": str(archive_pt),
        "manifest_path": str(manifest_path),
        "source": source,
        "copied": copied_summary,
        "checks": archive_manifest["checks"],
        "sha256": archive_manifest.get("sha256"),
    }


def append_report(report_path: Path | None, result: dict[str, Any]) -> None:
    if report_path is None or result.get("overall") not in {"PASS", "SKIPPED_EXISTS", "INHERITED_PARENT"}:
        return
    report_path.parent.mkdir(parents=True, exist_ok=True)
    copied = result.get("copied") or result.get("existing_manifest", {}).get("copied") or {}
    if result.get("overall") == "INHERITED_PARENT":
        copied = result.get("parent_checkpoint") or {}
    copied_hands = copied.get("total_hands")
    try:
        copied_hands_text = f"{int(copied_hands):,}"
    except Exception:
        copied_hands_text = str(copied_hands)
    lines = [
        "",
        f"## Checkpoint Archive {milestone_label(int(result['milestone_hands']))}",
        "",
        f"- checked at: `{result.get('checked_at')}`",
        f"- status: `{result.get('overall')}`",
        f"- archive: `{result.get('archive_path') or result.get('parent_checkpoint_path')}`",
        f"- manifest: `{result.get('manifest_path')}`",
        f"- checkpoint iteration: `{copied.get('iteration')}`",
        f"- checkpoint hands: `{copied_hands_text}`",
        "- scope: immutable milestone archive for later internal/Slumbot re-runs",
    ]
    report_path.open("a", encoding="utf-8").write("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description="Archive V5 latest.pt at hand-count milestones.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="", help="Defaults to <run-dir>/latest.pt")
    parser.add_argument("--archive-dir", default="", help="Defaults to <run-dir>/milestone_archives")
    parser.add_argument("--milestones", nargs="*", default=None, help="Hand milestones, e.g. 50M 250M 1B")
    parser.add_argument("--sleep-seconds", type=float, default=300.0)
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--no-sha256", action="store_true")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--status-json", default="")
    parser.add_argument("--log", default="")
    parser.add_argument("--append-report", default="")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else run_dir / "latest.pt"
    archive_dir = Path(args.archive_dir) if args.archive_dir else run_dir / "milestone_archives"
    milestones = parse_milestones(args.milestones)
    status_path = Path(args.status_json) if args.status_json else run_dir / "checkpoint_archive_status.json"
    log_path = Path(args.log) if args.log else run_dir / "checkpoint_archive_watch.log"
    report_path = Path(args.append_report) if args.append_report else None
    completed: set[int] = set()
    history: list[dict[str, Any]] = []
    parent = inherited_parent_summary(run_dir)
    parent_hands = int(parent.get("total_hands") or 0) if parent.get("available") else 0

    def log(message: str) -> None:
        line = f"{now_iso()} {message}"
        print(line, flush=True)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        log_path.open("a", encoding="utf-8").write(line + "\n")

    log(
        f"checkpoint archive watcher started run_dir={run_dir} milestones={milestones} "
        f"parent_hands={parent_hands if parent_hands else 'none'}"
    )
    while True:
        made_progress = False
        for milestone in milestones:
            if milestone in completed:
                continue
            if parent_hands >= milestone and not args.force:
                result = inherited_result(milestone, parent)
            else:
                result = archive_checkpoint(
                    checkpoint_path,
                    archive_dir,
                    milestone,
                    compute_sha256=not args.no_sha256,
                    force=args.force,
                    retries=args.retries,
                )
            history.append(result)
            write_json(
                status_path,
                {
                    "checked_at": now_iso(),
                    "run_dir": str(run_dir),
                    "checkpoint": str(checkpoint_path),
                    "archive_dir": str(archive_dir),
                    "milestones": milestones,
                    "inherited_parent": parent,
                    "completed": sorted(completed),
                    "latest_result": result,
                    "history_tail": history[-20:],
                },
            )
            source = result.get("source") or {}
            log(
                f"milestone={milestone_label(milestone)} overall={result['overall']} "
                f"ckpt_iter={source.get('iteration')} hands={source.get('total_hands')}"
            )
            if result["overall"] in {"PASS", "SKIPPED_EXISTS", "INHERITED_PARENT"}:
                completed.add(milestone)
                append_report(report_path, result)
                made_progress = True
                continue
            if result["overall"] == "FAIL":
                return 1
            # Milestones are ordered; if this one is pending, later ones are not ready.
            break

        write_json(
            status_path,
            {
                "checked_at": now_iso(),
                "run_dir": str(run_dir),
                "checkpoint": str(checkpoint_path),
                "archive_dir": str(archive_dir),
                "milestones": milestones,
                "inherited_parent": parent,
                "completed": sorted(completed),
                "history_tail": history[-20:],
                "all_complete": len(completed) == len(milestones),
            },
        )

        if len(completed) == len(milestones):
            log("all milestones archived")
            return 0
        if args.once:
            log("once mode complete")
            return 0
        if not made_progress:
            time.sleep(args.sleep_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
