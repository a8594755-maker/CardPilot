#!/usr/bin/env python3
"""Read-only fail-closed progress audit for the legal-all-in Path-1 asset job."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

import psutil


EXPECTED_ASSET_LOCK_SHA = "ddc57ea13d9bd02cdc41f40832aa08b07b82b03267d1540b4745abb3b60174d4"
BOARD_RE = re.compile(r"flop_(\d+)\.(?:jsonl\.gz|meta\.json)$")
QA_EVENT_RE = re.compile(r"^\[[^\]]+\]\s+.*flop_(\d+)\.jsonl\.gz\s*$", re.MULTILINE)
ACTIVE_RE = re.compile(r"W(\d+) starting board=(\d+)")


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def board_ids(paths: list[Path]) -> set[int]:
    result = set()
    for path in paths:
        match = BOARD_RE.fullmatch(path.name)
        if match:
            result.add(int(match.group(1)))
    return result


def latest_qa(path: Path) -> tuple[dict[int, dict], list[int], int]:
    text = path.read_text(encoding="utf-8", errors="replace")
    matches = list(QA_EVENT_RE.finditer(text))
    latest: dict[int, dict] = {}
    failures: list[int] = []
    records = 0
    for index, match in enumerate(matches):
        block = text[match.start() : matches[index + 1].start() if index + 1 < len(matches) else len(text)]
        verdict = re.search(r"^QA:\s+(PASS|FAIL)", block, re.MULTILINE)
        if not verdict:
            continue
        illegal = re.search(r"^illegal post-all-in extra-action rows:\s+(\d+)", block, re.MULTILINE)
        board = int(match.group(1))
        value = {
            "status": verdict.group(1),
            "illegal_postallin_rows": int(illegal.group(1)) if illegal else None,
        }
        latest[board] = value
        records += 1
        if value["status"] == "FAIL":
            failures.append(board)
    return latest, sorted(set(failures)), records


def active_boards(path: Path) -> list[dict]:
    latest: dict[int, int] = {}
    for worker, board in ACTIVE_RE.findall(path.read_text(encoding="utf-8", errors="replace")):
        latest[int(worker)] = int(board)
    return [{"worker": worker, "board": latest[worker]} for worker in sorted(latest)]


def find_job(asset_dir: Path) -> tuple[psutil.Process | None, list[psutil.Process]]:
    coordinators = []
    for process in psutil.process_iter(["pid", "cmdline"]):
        try:
            command = " ".join(process.info.get("cmdline") or [])
            normalized = command.replace("\\", "/").lower()
            if "solve-v3-parallel.ts" in normalized and str(asset_dir).replace("\\", "/").lower() in normalized:
                coordinators.append(process)
        except (psutil.Error, OSError):
            pass
    if len(coordinators) != 1:
        return None, []
    workers = []
    for child in coordinators[0].children(recursive=False):
        try:
            command = " ".join(child.cmdline()).replace("\\", "/").lower()
            if "solve-worker.ts" in command:
                workers.append(child)
        except psutil.Error:
            pass
    return coordinators[0], workers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--asset-dir", type=Path, required=True)
    parser.add_argument("--asset-lock", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    asset_dir = args.asset_dir.resolve()
    asset_lock = args.asset_lock.resolve()
    errors: list[str] = []
    if args.out.exists():
        raise FileExistsError(args.out)
    lock = load(asset_lock)
    if sha(asset_lock) != EXPECTED_ASSET_LOCK_SHA:
        errors.append("asset lock hash")
    config = lock.get("configuration", {})
    if config.get("output_dir") != str(asset_dir) or config.get("target_boards") != 600:
        errors.append("asset lock configuration")
    gzip_paths = sorted(asset_dir.glob("flop_*.jsonl.gz"))
    meta_paths = sorted(asset_dir.glob("flop_*.meta.json"))
    gzip_ids, meta_ids = board_ids(gzip_paths), board_ids(meta_paths)
    if gzip_ids != meta_ids:
        errors.append("gzip/meta identity sets")
    bad_meta = []
    for path in meta_paths:
        value = load(path)
        board = int(BOARD_RE.fullmatch(path.name).group(1))
        if (
            value.get("boardId") != board
            or value.get("config") != "pipeline_srp_v3_200bb"
            or value.get("iterations") != 80000
            or value.get("stack") != "200bb"
        ):
            bad_meta.append(board)
    if bad_meta:
        errors.append("metadata contract")
    qa_log = asset_dir / "path1-qa.log"
    latest, failure_history, qa_records = latest_qa(qa_log)
    missing_qa = sorted(gzip_ids - set(latest))
    bad_latest = sorted(
        board for board in gzip_ids if board in latest and (
            latest[board]["status"] != "PASS" or latest[board]["illegal_postallin_rows"] != 0
        )
    )
    if missing_qa:
        errors.append("missing latest QA")
    if bad_latest:
        errors.append("bad latest QA")
    code_mismatches = []
    for item in lock.get("code_identity", []):
        path = Path(item["path"])
        if not path.is_file() or sha(path) != item["sha256"]:
            code_mismatches.append(str(path))
    if code_mismatches:
        errors.append("code identity")
    coordinator, workers = find_job(asset_dir)
    if coordinator is None or len(workers) != 6:
        errors.append("live six-worker job")
    priority = None
    if coordinator is not None:
        try:
            priority = "BelowNormal" if int(coordinator.nice()) == 0x4000 else str(coordinator.nice())
        except psutil.Error:
            errors.append("coordinator priority")
    if priority != "BelowNormal":
        errors.append("coordinator priority")
    selection_manifest = asset_dir / "path1-selection-manifest.json"
    solver_status = asset_dir / "path1-solver-status.json"
    parallel_log = asset_dir / "parallel-solver.log"
    result = {
        "schema_version": "v5.path1.legalallin_v2.progress.v2",
        "classification": "PATH1_DIAGNOSTIC_ASSET_PROGRESS_QA_PASS" if not errors else "FAIL_CLOSED",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not errors else "FAIL_CLOSED",
        "errors": errors,
        "asset_dir": str(asset_dir),
        "config": "pipeline_srp_v3_200bb",
        "iterations": 80000,
        "target_boards": 600,
        "selection_seed": 20260712,
        "samples_per_bucket": 1,
        "no_overwrite": True,
        "coordinator_pid": coordinator.pid if coordinator else None,
        "coordinator_alive": coordinator is not None,
        "priority": priority,
        "solver_worker_count": len(workers),
        "solver_worker_pids": sorted(worker.pid for worker in workers),
        "complete_gzip_meta_pairs": len(gzip_ids & meta_ids),
        "complete_total_gzip_bytes": sum(path.stat().st_size for path in gzip_paths),
        "qa_records_total": qa_records,
        "qa_pass_unique": sum(value["status"] == "PASS" for value in latest.values()),
        "qa_pass_zero_illegal_postallin_latest_unique": sum(
            value["status"] == "PASS" and value["illegal_postallin_rows"] == 0 for value in latest.values()
        ),
        "qa_fail_history": failure_history,
        "qa_fail_recovered_to_pass": sorted(board for board in failure_history if latest.get(board, {}).get("status") == "PASS"),
        "qa_missing_for_complete": missing_qa,
        "qa_bad_latest_for_complete": bad_latest,
        "bad_metadata_boards": bad_meta,
        "active_boards": active_boards(parallel_log),
        "completed_board_ids": sorted(gzip_ids & meta_ids),
        "selection_manifest_sha256": sha(selection_manifest),
        "asset_lock_sha256": sha(asset_lock),
        "solver_status_sha256": sha(solver_status),
        "parallel_log_sha256_at_check": sha(parallel_log),
        "qa_log_sha256_at_check": sha(qa_log),
        "code_identity_current_match": not code_mismatches,
        "code_identity_mismatches": code_mismatches,
        "validation": {
            "gzip_meta_identity_sets_equal": gzip_ids == meta_ids,
            "qa_pass_identity_set_equals_complete_pair_set": not missing_qa and not bad_latest,
            "latest_qa_record_per_completed_board_passes": not missing_qa and not bad_latest,
            "latest_qa_record_per_completed_board_illegal_postallin_rows_zero": not missing_qa and not bad_latest,
        },
        "behavior_effect": "NONE",
        "gpu_use": "FORBIDDEN_AND_NOT_REQUESTED",
        "v55_training_eligibility": "FORBIDDEN_DIAGNOSTIC_ONLY",
        "official_hands": 0,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
