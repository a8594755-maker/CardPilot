#!/usr/bin/env python3
"""Execute the immutable, trainerless, read-only PCV015 Path-1 closure audit."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


PREREG_SHA256 = "b222d0e9dc5aa99b369d2e4a58e050fb6bc636d2a4b90855d271420b9c99ed1f"
PREREG_AUDIT_SHA256 = "72362297088eab76ffaec00b1b3072abf9b587a5d7439fd2d04f25a61a25bc00"
ROUTE_RESULT_SHA256 = "a27011e2634526963e832cff7935b2cc9c1f116f7e08a80b296c0c3a057d1db6"
ROUTE_AUDIT_SHA256 = "c0ad83750c919c4fc315e6cca4c2f03576dacd5b2921f7ed65b183796a7337b2"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def parse_qa_log(path: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    start_re = re.compile(r"^\[([^\]]+)\]\s+.*[\\/]flop_(\d+)\.jsonl\.gz\s*$")
    illegal_re = re.compile(r"^illegal post-all-in extra-action rows:\s*(\d+)\s*$")
    verdict_re = re.compile(r"^QA:\s*(PASS|FAIL)(?:\s|$)")
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in path.read_text(encoding="utf-8", errors="strict").splitlines():
        start = start_re.match(raw)
        if start:
            if current is not None:
                records.append(current)
            current = {
                "timestamp": start.group(1),
                "board_id": int(start.group(2)),
                "illegal_postallin_rows": None,
                "verdict": None,
            }
            continue
        if current is None:
            continue
        illegal = illegal_re.match(raw)
        if illegal:
            current["illegal_postallin_rows"] = int(illegal.group(1))
        verdict = verdict_re.match(raw)
        if verdict:
            current["verdict"] = verdict.group(1)
    if current is not None:
        records.append(current)
    latest: dict[int, dict[str, Any]] = {}
    for record in records:
        latest[int(record["board_id"])] = record
    return records, latest


def board_ids(directory: Path, pattern: re.Pattern[str]) -> dict[int, Path]:
    output: dict[int, Path] = {}
    for entry in directory.iterdir():
        if not entry.is_file():
            continue
        match = pattern.fullmatch(entry.name)
        if match:
            board_id = int(match.group(1))
            if board_id in output:
                raise ValueError(f"duplicate board identity {board_id} for {pattern.pattern}")
            output[board_id] = entry
    return output


def inventory_digest(
    selected: list[int], gzip_files: dict[int, Path], meta_files: dict[int, Path]
) -> tuple[str, dict[int, dict[str, Any]], list[int]]:
    rows: list[str] = []
    metadata: dict[int, dict[str, Any]] = {}
    malformed: list[int] = []
    for board_id in selected:
        gzip_path = gzip_files.get(board_id)
        meta_path = meta_files.get(board_id)
        if gzip_path is None or meta_path is None:
            continue
        try:
            meta = load_json(meta_path)
            metadata[board_id] = meta
            gzip_stat = gzip_path.stat()
            meta_stat = meta_path.stat()
            meta_sha = sha256_file(meta_path)
            rows.append(
                "|".join(
                    [
                        str(board_id),
                        str(gzip_path.resolve()),
                        str(gzip_stat.st_size),
                        str(gzip_stat.st_mtime_ns),
                        str(meta_path.resolve()),
                        str(meta_stat.st_size),
                        str(meta_stat.st_mtime_ns),
                        meta_sha,
                    ]
                )
            )
        except (OSError, ValueError, json.JSONDecodeError):
            malformed.append(board_id)
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(), metadata, malformed


def command_sha256(command: list[str]) -> str:
    return hashlib.sha256("\0".join(command).encode("utf-8")).hexdigest()


def classify_child(command: list[str]) -> str:
    joined = " ".join(command).lower()
    if "qa-200bb-board" in joined:
        return "QA_200BB_BOARD"
    if "solve-v3" in joined or "cfr-solver" in joined:
        return "SOLVE_WORKER"
    if "conhost" in joined:
        return "CONHOST_IGNORED"
    return "UNKNOWN"


def gpu_pids() -> set[int]:
    proc = subprocess.run(
        [
            "nvidia-smi",
            "--query-compute-apps=pid",
            "--format=csv,noheader,nounits",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )
    if proc.returncode != 0:
        raise RuntimeError("nvidia-smi process query failed")
    result: set[int] = set()
    for line in proc.stdout.splitlines():
        value = line.strip()
        if value.isdigit():
            result.add(int(value))
    return result


def lifecycle_snapshot(contract: dict[str, Any]) -> dict[str, Any]:
    pid = int(contract["registered_coordinator_pid"])
    try:
        process = psutil.Process(pid)
        create_time = process.create_time()
        command = process.cmdline()
    except psutil.NoSuchProcess:
        return {
            "state": "TERMINAL_ABSENT",
            "registered_pid": pid,
            "identity_match": None,
            "priority_match": None,
            "child_roles": [],
            "unknown_roles": 0,
            "descendant_gpu_pid_matches": 0,
            "global_process_enumeration": False,
        }
    expected_create = float(contract["registered_coordinator_create_time"])
    expected_command_sha = str(contract["registered_coordinator_command_sha256"])
    actual_command_sha = command_sha256(command)
    identity_match = abs(create_time - expected_create) <= 1e-3 and actual_command_sha == expected_command_sha
    priority_match = process.nice() == psutil.BELOW_NORMAL_PRIORITY_CLASS
    children = process.children(recursive=True)
    child_roles = [
        {
            "pid": child.pid,
            "role": classify_child(child.cmdline()),
            "priority": str(child.nice()),
        }
        for child in children
        if child.is_running()
    ]
    unknown_roles = sum(row["role"] == "UNKNOWN" for row in child_roles)
    descendant_ids = {child.pid for child in children}
    descendant_gpu_matches = len(descendant_ids & gpu_pids())
    return {
        "state": "ACTIVE_EXACT" if identity_match else "ACTIVE_IDENTITY_MISMATCH",
        "registered_pid": pid,
        "create_time": create_time,
        "command_sha256": actual_command_sha,
        "identity_match": identity_match,
        "priority_match": priority_match,
        "child_roles": child_roles,
        "unknown_roles": unknown_roles,
        "descendant_gpu_pid_matches": descendant_gpu_matches,
        "global_process_enumeration": False,
    }


def execute(prereg_path: Path, prereg_audit_path: Path, output_path: Path) -> dict[str, Any]:
    if output_path.exists():
        raise FileExistsError(f"immutable output already exists: {output_path}")
    prereg = load_json(prereg_path)
    if sha256_file(prereg_path) != PREREG_SHA256:
        raise ValueError("preregistration hash mismatch")
    if sha256_file(prereg_audit_path) != PREREG_AUDIT_SHA256:
        raise ValueError("preregistration audit hash mismatch")
    prereg_audit = load_json(prereg_audit_path)
    if prereg_audit.get("overall") != "PASS" or prereg_audit.get("checks_passed") != 35:
        raise ValueError("preregistration audit is not PASS35/35")

    frozen = prereg["frozen_inputs"]
    observed_hashes: dict[str, str] = {}
    for name in ("asset_lock", "progress_553", "selection_manifest", "solver_status", "qa_log", "parallel_log"):
        item = frozen[name]
        path = Path(item["path"])
        actual = sha256_file(path)
        observed_hashes[name] = actual
        if actual != item["sha256"]:
            raise ValueError(f"frozen input hash mismatch: {name}")

    selection = load_json(Path(frozen["selection_manifest"]["path"]))
    status = load_json(Path(frozen["solver_status"]["path"]))
    asset_lock = load_json(Path(frozen["asset_lock"]["path"]))
    selected = [int(value) for value in selection["selectedBoardIds"]]
    selected_set = set(selected)
    selection_ok = (
        len(selected) == 600
        and len(selected_set) == 600
        and selection.get("targetBoards") == 600
        and selection.get("selectionSeed") == 20260712
        and selection.get("config") == "pipeline_srp_v3_200bb"
        and asset_lock.get("configuration", {}).get("target_boards") == 600
        and asset_lock.get("configuration", {}).get("iterations_per_board") == 80000
    )

    directory = Path(frozen["asset_directory"])
    gzip_files = board_ids(directory, re.compile(r"flop_(\d+)\.jsonl\.gz"))
    meta_files = board_ids(directory, re.compile(r"flop_(\d+)\.meta\.json"))
    gzip_ids = set(gzip_files)
    meta_ids = set(meta_files)
    missing_gzip = sorted(selected_set - gzip_ids)
    missing_meta = sorted(selected_set - meta_ids)
    extra_gzip = sorted(gzip_ids - selected_set)
    extra_meta = sorted(meta_ids - selected_set)
    empty_gzip = sorted(board_id for board_id, path in gzip_files.items() if path.stat().st_size <= 0)
    inventory_sha, metadata, malformed_meta = inventory_digest(selected, gzip_files, meta_files)
    meta_identity_failures = sorted(
        board_id
        for board_id, meta in metadata.items()
        if meta.get("boardId") != board_id
        or meta.get("config") != "pipeline_srp_v3_200bb"
        or meta.get("iterations") != 80000
    )

    qa_records, latest_qa = parse_qa_log(Path(frozen["qa_log"]["path"]))
    qa_missing = sorted(selected_set - set(latest_qa))
    qa_latest_fail = sorted(
        board_id
        for board_id in selected
        if board_id in latest_qa and latest_qa[board_id].get("verdict") != "PASS"
    )
    qa_latest_illegal = sorted(
        board_id
        for board_id in selected
        if board_id in latest_qa and latest_qa[board_id].get("illegal_postallin_rows") != 0
    )
    qa_fail_history = sorted(
        {int(record["board_id"]) for record in qa_records if record.get("verdict") == "FAIL"}
    )
    qa_recovered = sorted(
        board_id
        for board_id in qa_fail_history
        if board_id in latest_qa
        and latest_qa[board_id].get("verdict") == "PASS"
        and latest_qa[board_id].get("illegal_postallin_rows") == 0
    )

    valid_ids: list[int] = []
    for board_id in selected:
        meta = metadata.get(board_id)
        latest = latest_qa.get(board_id)
        if (
            board_id in gzip_ids
            and board_id in meta_ids
            and gzip_files[board_id].stat().st_size > 0
            and meta is not None
            and board_id not in malformed_meta
            and board_id not in meta_identity_failures
            and latest is not None
            and latest.get("verdict") == "PASS"
            and latest.get("illegal_postallin_rows") == 0
        ):
            valid_ids.append(board_id)

    unresolved_errors = sorted(
        set(missing_gzip)
        | set(missing_meta)
        | set(empty_gzip)
        | set(malformed_meta)
        | set(meta_identity_failures)
        | set(qa_missing)
        | set(qa_latest_fail)
        | set(qa_latest_illegal)
    )
    lifecycle = lifecycle_snapshot(prereg["lifecycle_contract"])
    lifecycle_contract_fail = (
        lifecycle["state"] == "ACTIVE_IDENTITY_MISMATCH"
        or lifecycle.get("priority_match") is False
        or lifecycle.get("unknown_roles", 0) != 0
        or lifecycle.get("descendant_gpu_pid_matches", 0) != 0
    )
    input_contract_fail = not selection_ok or bool(extra_gzip or extra_meta)
    status_unresolved = int(status.get("failed", 0)) != 0 or status.get("status") != "COMPLETED"

    if lifecycle_contract_fail or input_contract_fail:
        verdict = "FAIL"
        classification = "PCV015_FAIL_CLOSED_INPUT_OR_RESOURCE_CONTRACT"
    elif lifecycle["state"] == "ACTIVE_EXACT":
        verdict = "INCONCLUSIVE"
        classification = "PCV015_INCONCLUSIVE_PATH1_STILL_ACTIVE_READ_ONLY"
    elif len(valid_ids) == 600 and not unresolved_errors and not status_unresolved:
        verdict = "PASS"
        classification = "PCV015_PASS_PATH1_TERMINAL_COMPLETE_RESOURCE_CONTRACT"
    else:
        verdict = "FAIL"
        classification = "PCV015_FAIL_CLOSED_PATH1_TERMINAL_INCOMPLETE_NO_RESTART"

    result = {
        "schema_version": "v5.pcv015.result.v1",
        "design_id": "PCV015",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "verdict": verdict,
        "classification": classification,
        "preregistration_sha256": PREREG_SHA256,
        "preregistration_audit_sha256": PREREG_AUDIT_SHA256,
        "route_review026_result_sha256": ROUTE_RESULT_SHA256,
        "route_review026_audit_sha256": ROUTE_AUDIT_SHA256,
        "frozen_input_hashes": observed_hashes,
        "selection": {
            "config": selection.get("config"),
            "target_boards": selection.get("targetBoards"),
            "selected_board_count": len(selected),
            "selected_board_ids_unique": len(selected_set) == len(selected),
            "selection_seed": selection.get("selectionSeed"),
            "selection_method": selection.get("method"),
            "identity_contract_pass": selection_ok,
        },
        "asset_closure": {
            "gzip_count": len(gzip_ids),
            "meta_count": len(meta_ids),
            "pair_count": len(gzip_ids & meta_ids & selected_set),
            "valid_pair_count": len(valid_ids),
            "missing_gzip": missing_gzip,
            "missing_meta": missing_meta,
            "extra_gzip": extra_gzip,
            "extra_meta": extra_meta,
            "empty_gzip": empty_gzip,
            "malformed_meta": sorted(malformed_meta),
            "meta_identity_failures": meta_identity_failures,
            "inventory_sha256": inventory_sha,
            "gzip_content_decompressed": False,
        },
        "qa": {
            "records_total": len(qa_records),
            "latest_unique_boards": len(latest_qa),
            "latest_selected_pass_zero_illegal": len(valid_ids),
            "missing_latest": qa_missing,
            "latest_fail": qa_latest_fail,
            "latest_illegal_postallin_nonzero_or_missing": qa_latest_illegal,
            "fail_history": qa_fail_history,
            "fail_recovered_to_latest_pass": qa_recovered,
        },
        "solver_terminal": {
            "status": status.get("status"),
            "registered_pid": status.get("pid"),
            "finished_at": status.get("finishedAt"),
            "selected_complete": status.get("selectedComplete"),
            "target_boards": status.get("targetBoards"),
            "failed": status.get("failed"),
            "unresolved_error": status_unresolved,
            "unresolved_board_ids": unresolved_errors,
        },
        "lifecycle": lifecycle,
        "policy": {
            "path1_write_or_signal": False,
            "path1_restart_repair_replace_or_expand": False,
            "gpu_workload_started": False,
            "trainer_evaluator_mirror_or_slumbot_started": False,
            "checkpoint_written": False,
            "prior_timing_rows_read": False,
            "official_hands": 0,
        },
        "interpretation": {
            "control_plane_only": True,
            "timing_method_behavior_or_strength_inference": "FORBIDDEN",
            "path1_action_authority": "NONE",
            "automatic_h19_or_later_launch": False,
            "next": "SEPARATELY_REGISTERED_ROUTE_REVIEW027",
        },
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(result, handle, indent=2, sort_keys=False)
        handle.write("\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = execute(args.preregistration, args.preregistration_audit, args.output)
    print(json.dumps({"verdict": result["verdict"], "classification": result["classification"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
