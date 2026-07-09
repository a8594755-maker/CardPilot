#!/usr/bin/env python3
"""Freeze the first EXP-003 gate that is both PASS and hand-eligible.

This watcher is reporting-only: it never changes trainer state.  It waits for
the first gate artifact whose ``overall`` is ``PASS`` and whose checkpoint has
at least the registered EXP-003 judgment hand count.  It will archive only
while ``latest.pt`` still has exactly the iteration and hand count recorded by
that gate.  Once a first eligible PASS gate is missed, the FAIL status is
terminal so a later checkpoint cannot silently replace the registered one.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from v5_checkpoint_archive_watch import (
    archive_checkpoint,
    checkpoint_summary,
    load_json,
    now_iso,
    sha256_file,
)


DEFAULT_TARGET_HANDS = 408_064_575
GATE_RE = re.compile(r"^gate_(\d+)_status\.json$")


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _atomic_write_json(path: Path, obj: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(obj, indent=2, sort_keys=True) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    temp_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fp:
            fp.write(payload)
            fp.flush()
            os.fsync(fp.fileno())
        temp_path.replace(path)
    finally:
        temp_path.unlink(missing_ok=True)


def _base_status(
    run_dir: Path,
    checkpoint_path: Path,
    archive_dir: Path,
    target_hands: int,
) -> dict[str, Any]:
    return {
        "checked_at": now_iso(),
        "run_dir": str(run_dir),
        "checkpoint_path": str(checkpoint_path),
        "archive_dir": str(archive_dir),
        "target_hands": int(target_hands),
        "selected_gate": None,
        "archive": None,
    }


def _gate_records(run_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    for path in run_dir.glob("gate_*_status.json"):
        match = GATE_RE.match(path.name)
        if not match:
            continue
        filename_iteration = int(match.group(1))
        data = load_json(path)
        if data.get("_missing") or data.get("_load_error"):
            errors.append(
                {
                    "path": str(path),
                    "target_iteration": filename_iteration,
                    "error": data.get("_load_error") or "missing gate artifact",
                }
            )
            continue
        target_iteration = _as_int(data.get("target_iteration"))
        checkpoint_iteration = _as_int(data.get("checkpoint_iteration"))
        checkpoint_hands = _as_int(data.get("checkpoint_hands"))
        if target_iteration is not None and target_iteration != filename_iteration:
            errors.append(
                {
                    "path": str(path),
                    "target_iteration": filename_iteration,
                    "error": (
                        f"filename target {filename_iteration} disagrees with JSON "
                        f"target_iteration {target_iteration}"
                    ),
                }
            )
            continue
        if checkpoint_iteration is None or checkpoint_hands is None:
            errors.append(
                {
                    "path": str(path),
                    "target_iteration": filename_iteration,
                    "error": "checkpoint_iteration/checkpoint_hands must both be integers",
                }
            )
            continue
        records.append(
            {
                "path": str(path),
                "target_iteration": filename_iteration,
                "iteration": checkpoint_iteration,
                "checkpoint_hands": checkpoint_hands,
                "overall": str(data.get("overall") or "UNKNOWN").upper(),
                "run_id": data.get("run_id"),
            }
        )
    records.sort(key=lambda row: (int(row["target_iteration"]), str(row["path"])))
    errors.sort(key=lambda row: (int(row["target_iteration"]), str(row["path"])))
    return records, errors


def _first_eligible_pass(
    records: list[dict[str, Any]],
    target_hands: int,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Return the first eligible PASS, or an earlier nonterminal blocker.

    FAIL gates are skipped because they are not eligible PASS gates.  A gate
    at/above the hand threshold that is still PENDING/UNKNOWN blocks selection
    of any later PASS gate; otherwise a later checkpoint could be substituted
    before the earlier gate's final verdict exists.
    """

    for record in records:
        hands = record.get("checkpoint_hands")
        if hands is None or int(hands) < int(target_hands):
            continue
        overall = str(record.get("overall") or "UNKNOWN").upper()
        if overall == "FAIL":
            continue
        if overall == "PASS":
            return record, None
        return None, record
    return None, None


def _selected_gate_schema(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "path": str(record["path"]),
        "iteration": int(record["iteration"]),
        "target_iteration": int(record["target_iteration"]),
        "checkpoint_hands": int(record["checkpoint_hands"]),
        "overall": str(record["overall"]),
    }


def _is_ahead(latest: dict[str, Any], gate: dict[str, Any]) -> bool:
    latest_iteration = _as_int(latest.get("iteration"))
    latest_hands = _as_int(latest.get("total_hands"))
    gate_iteration = _as_int(gate.get("iteration"))
    gate_hands = _as_int(gate.get("checkpoint_hands"))
    if None in (latest_iteration, latest_hands, gate_iteration, gate_hands):
        return False
    return bool(latest_iteration > gate_iteration or latest_hands > gate_hands)


def _terminal_status(status_path: Path) -> dict[str, Any] | None:
    if not status_path.exists():
        return None
    previous = load_json(status_path)
    if previous.get("_missing"):
        return None
    if previous.get("_load_error"):
        return {
            "checked_at": now_iso(),
            "overall": "FAIL",
            "state": "STATUS_CORRUPT",
            "reason": f"existing status could not be loaded: {previous['_load_error']}",
            "status_path": str(status_path),
            "terminal": True,
        }
    overall = str(previous.get("overall") or "").upper()
    if overall == "FAIL":
        return previous
    if overall != "PASS":
        return None

    archive = previous.get("archive") if isinstance(previous.get("archive"), dict) else {}
    archive_path = Path(str(archive.get("path") or ""))
    expected_sha = str(archive.get("sha256") or "")
    if not archive_path.is_file() or not expected_sha:
        failed = dict(previous)
        failed.update(
            {
                "checked_at": now_iso(),
                "overall": "FAIL",
                "state": "FROZEN_ARCHIVE_INTEGRITY_FAIL",
                "reason": "terminal PASS status is missing its archive file or SHA256",
                "terminal": True,
            }
        )
        return failed
    actual_sha = sha256_file(archive_path)
    if actual_sha != expected_sha:
        failed = dict(previous)
        failed.update(
            {
                "checked_at": now_iso(),
                "overall": "FAIL",
                "state": "FROZEN_ARCHIVE_INTEGRITY_FAIL",
                "reason": f"archive SHA256 changed: actual={actual_sha}, expected={expected_sha}",
                "terminal": True,
            }
        )
        return failed
    return previous


def _archive_schema(result: dict[str, Any]) -> dict[str, Any] | None:
    if result.get("overall") == "PASS":
        copied = result.get("copied") if isinstance(result.get("copied"), dict) else {}
        sha256 = result.get("sha256")
    elif result.get("overall") == "SKIPPED_EXISTS":
        manifest = result.get("existing_manifest") if isinstance(result.get("existing_manifest"), dict) else {}
        copied = manifest.get("copied") if isinstance(manifest.get("copied"), dict) else {}
        sha256 = manifest.get("sha256")
    else:
        return None
    return {
        "path": str(result.get("archive_path") or ""),
        "manifest_path": str(result.get("manifest_path") or ""),
        "sha256": str(sha256 or ""),
        "checkpoint": {
            "iteration": _as_int(copied.get("iteration")),
            "total_hands": _as_int(copied.get("total_hands")),
            "run_id": copied.get("run_id"),
        },
    }


def freeze_once(
    run_dir: Path,
    *,
    checkpoint_path: Path | None = None,
    archive_dir: Path | None = None,
    status_path: Path | None = None,
    target_hands: int = DEFAULT_TARGET_HANDS,
    retries: int = 3,
) -> dict[str, Any]:
    run_dir = Path(run_dir)
    checkpoint_path = Path(checkpoint_path) if checkpoint_path else run_dir / "latest.pt"
    archive_dir = Path(archive_dir) if archive_dir else run_dir / "exp003_judgment_archives"
    status_path = Path(status_path) if status_path else run_dir / "exp003_judgment_freeze_status.json"

    terminal = _terminal_status(status_path)
    if terminal is not None:
        _atomic_write_json(status_path, terminal)
        return terminal

    status = _base_status(run_dir, checkpoint_path, archive_dir, target_hands)
    records, gate_errors = _gate_records(run_dir)
    selected, blocking = _first_eligible_pass(records, target_hands)
    status["gate_artifact_count"] = len(records)
    status["gate_artifact_errors"] = gate_errors

    if blocking is not None:
        status.update(
            {
                "overall": "WAITING",
                "state": "WAITING_FOR_GATE_FINAL_VERDICT",
                "reason": (
                    f"gate {blocking['target_iteration']} has checkpoint_hands={blocking['checkpoint_hands']} "
                    f"but overall={blocking['overall']}"
                ),
                "blocking_gate": blocking,
                "terminal": False,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    if selected is not None:
        earlier_errors = [
            row for row in gate_errors if int(row["target_iteration"]) <= int(selected["target_iteration"])
        ]
        if earlier_errors:
            status.update(
                {
                    "overall": "WAITING",
                    "state": "WAITING_FOR_GATE_ARTIFACT_REPAIR",
                    "reason": "an unreadable earlier gate artifact prevents proof that this is the first eligible PASS",
                    "terminal": False,
                }
            )
            _atomic_write_json(status_path, status)
            return status

    latest = checkpoint_summary(checkpoint_path)
    status["latest_checkpoint"] = latest

    if selected is None:
        status.update(
            {
                "overall": "WAITING",
                "state": "WAITING_FOR_FIRST_ELIGIBLE_PASS",
                "reason": f"no gate is PASS with checkpoint_hands >= {target_hands}",
                "terminal": False,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    status["selected_gate"] = _selected_gate_schema(selected)
    gate_iteration = _as_int(selected.get("iteration"))
    gate_target_iteration = _as_int(selected.get("target_iteration"))
    gate_hands = _as_int(selected.get("checkpoint_hands"))
    if None in (gate_iteration, gate_target_iteration, gate_hands):
        status.update(
            {
                "overall": "FAIL",
                "state": "INVALID_FIRST_ELIGIBLE_GATE",
                "reason": "first eligible PASS gate lacks checkpoint iteration or hands",
                "terminal": True,
            }
        )
        _atomic_write_json(status_path, status)
        return status
    if gate_iteration != gate_target_iteration:
        status.update(
            {
                "overall": "FAIL",
                "state": "MISSED_FIRST_ELIGIBLE_PASS",
                "reason": (
                    f"gate target {gate_target_iteration} was recorded from later checkpoint iteration "
                    f"{gate_iteration}; refusing to substitute it"
                ),
                "terminal": True,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    if latest.get("_missing") or latest.get("_load_error"):
        status.update(
            {
                "overall": "WAITING",
                "state": "WAITING_FOR_CHECKPOINT_READ",
                "reason": str(latest.get("_load_error") or "latest.pt is missing"),
                "terminal": False,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    latest_iteration = _as_int(latest.get("iteration"))
    latest_hands = _as_int(latest.get("total_hands"))
    if latest_iteration != gate_iteration or latest_hands != gate_hands:
        missed = _is_ahead(latest, selected)
        status.update(
            {
                "overall": "FAIL",
                "state": "MISSED_FIRST_ELIGIBLE_PASS" if missed else "CHECKPOINT_GATE_MISMATCH",
                "reason": (
                    f"latest.pt is {latest_iteration}/{latest_hands}, first eligible PASS is "
                    f"{gate_iteration}/{gate_hands}; exact match required"
                ),
                "terminal": True,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    gate_run_id = selected.get("run_id")
    if gate_run_id and latest.get("run_id") != gate_run_id:
        status.update(
            {
                "overall": "FAIL",
                "state": "CHECKPOINT_GATE_MISMATCH",
                "reason": f"latest.pt run_id={latest.get('run_id')!r}, gate run_id={gate_run_id!r}",
                "terminal": True,
            }
        )
        _atomic_write_json(status_path, status)
        return status

    archive_dir.mkdir(parents=True, exist_ok=True)
    fd, staging_name = tempfile.mkstemp(
        prefix=f".exp003_iter{gate_iteration}_", suffix=".pt", dir=str(archive_dir)
    )
    os.close(fd)
    staging_path = Path(staging_name)
    try:
        shutil.copy2(checkpoint_path, staging_path)
        staged = checkpoint_summary(staging_path)
        status["staged_checkpoint"] = staged
        if staged.get("_missing") or staged.get("_load_error"):
            current = checkpoint_summary(checkpoint_path)
            status["latest_checkpoint_after_stage_failure"] = current
            status.update(
                {
                    "overall": "FAIL" if _is_ahead(current, selected) else "WAITING",
                    "state": (
                        "MISSED_FIRST_ELIGIBLE_PASS"
                        if _is_ahead(current, selected)
                        else "WAITING_FOR_STABLE_CHECKPOINT_COPY"
                    ),
                    "reason": str(staged.get("_load_error") or "staged checkpoint is missing"),
                    "terminal": bool(_is_ahead(current, selected)),
                }
            )
            _atomic_write_json(status_path, status)
            return status
        staged_iteration = _as_int(staged.get("iteration"))
        staged_hands = _as_int(staged.get("total_hands"))
        if staged_iteration != gate_iteration or staged_hands != gate_hands:
            status.update(
                {
                    "overall": "FAIL",
                    "state": "MISSED_FIRST_ELIGIBLE_PASS",
                    "reason": (
                        f"checkpoint changed during staging: staged={staged_iteration}/{staged_hands}, "
                        f"gate={gate_iteration}/{gate_hands}"
                    ),
                    "terminal": True,
                }
            )
            _atomic_write_json(status_path, status)
            return status

        staged_sha = sha256_file(staging_path)
        archive_result = archive_checkpoint(
            staging_path,
            archive_dir,
            target_hands,
            compute_sha256=True,
            force=False,
            retries=max(1, int(retries)),
        )
        status["archive_result"] = archive_result
        archive = _archive_schema(archive_result)
        if archive is None:
            status.update(
                {
                    "overall": "FAIL" if archive_result.get("overall") == "FAIL" else "WAITING",
                    "state": "ARCHIVE_FAIL" if archive_result.get("overall") == "FAIL" else "ARCHIVE_NOT_READY",
                    "reason": f"archive_checkpoint returned {archive_result.get('overall')}",
                    "terminal": archive_result.get("overall") == "FAIL",
                }
            )
            _atomic_write_json(status_path, status)
            return status

        archived_checkpoint = archive["checkpoint"]
        archive_path = Path(archive["path"])
        exact_archive = (
            archived_checkpoint.get("iteration") == gate_iteration
            and archived_checkpoint.get("total_hands") == gate_hands
            and archived_checkpoint.get("run_id") == latest.get("run_id")
        )
        actual_archive_sha = sha256_file(archive_path) if archive_path.is_file() else ""
        exact_sha = bool(archive.get("sha256")) and archive["sha256"] == actual_archive_sha == staged_sha
        if not exact_archive or not exact_sha:
            status["archive"] = archive
            status.update(
                {
                    "overall": "FAIL",
                    "state": "ARCHIVE_VERIFICATION_FAIL",
                    "reason": (
                        f"archive exact={exact_archive}, sha exact={exact_sha}; refusing an unverified freeze"
                    ),
                    "terminal": True,
                }
            )
            _atomic_write_json(status_path, status)
            return status

        status["archive"] = archive
        status.update(
            {
                "overall": "PASS",
                "state": "FROZEN_FIRST_ELIGIBLE_PASS",
                "reason": (
                    f"froze first eligible PASS checkpoint {gate_iteration}/{gate_hands} with verified SHA256"
                ),
                "terminal": True,
            }
        )
        _atomic_write_json(status_path, status)
        return status
    finally:
        staging_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Freeze EXP-003's first hand-eligible PASS checkpoint.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--checkpoint", default="", help="Defaults to <run-dir>/latest.pt")
    parser.add_argument(
        "--archive-dir", default="", help="Defaults to <run-dir>/exp003_judgment_archives"
    )
    parser.add_argument(
        "--status-json", default="", help="Defaults to <run-dir>/exp003_judgment_freeze_status.json"
    )
    parser.add_argument("--target-hands", type=int, default=DEFAULT_TARGET_HANDS)
    parser.add_argument("--poll-seconds", type=float, default=10.0)
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()

    run_dir = Path(args.run_dir)
    checkpoint_path = Path(args.checkpoint) if args.checkpoint else run_dir / "latest.pt"
    archive_dir = Path(args.archive_dir) if args.archive_dir else run_dir / "exp003_judgment_archives"
    status_path = Path(args.status_json) if args.status_json else run_dir / "exp003_judgment_freeze_status.json"

    while True:
        result = freeze_once(
            run_dir,
            checkpoint_path=checkpoint_path,
            archive_dir=archive_dir,
            status_path=status_path,
            target_hands=args.target_hands,
            retries=args.retries,
        )
        selected = result.get("selected_gate") or {}
        print(
            f"{result.get('checked_at')} overall={result.get('overall')} state={result.get('state')} "
            f"gate={selected.get('iteration')} hands={selected.get('checkpoint_hands')}",
            flush=True,
        )
        if result.get("overall") == "PASS":
            return 0
        if result.get("overall") == "FAIL":
            return 1
        if args.once:
            return 0
        time.sleep(max(0.1, float(args.poll_seconds)))


if __name__ == "__main__":
    raise SystemExit(main())
