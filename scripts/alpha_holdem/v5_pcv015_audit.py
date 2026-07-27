#!/usr/bin/env python3
"""Independently recompute and audit the immutable PCV015 result."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import psutil


PREREG_SHA256 = "b222d0e9dc5aa99b369d2e4a58e050fb6bc636d2a4b90855d271420b9c99ed1f"
PREREG_AUDIT_SHA256 = "72362297088eab76ffaec00b1b3072abf9b587a5d7439fd2d04f25a61a25bc00"


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


def collect(directory: Path, expression: str) -> dict[int, Path]:
    pattern = re.compile(expression)
    output: dict[int, Path] = {}
    for path in directory.iterdir():
        if path.is_file():
            match = pattern.fullmatch(path.name)
            if match:
                board_id = int(match.group(1))
                if board_id in output:
                    raise ValueError(f"duplicate board id {board_id}")
                output[board_id] = path
    return output


def parse_latest_qa(path: Path) -> tuple[list[dict[str, Any]], dict[int, dict[str, Any]]]:
    start = re.compile(r"^\[([^\]]+)\]\s+.*[\\/]flop_(\d+)\.jsonl\.gz\s*$")
    illegal = re.compile(r"^illegal post-all-in extra-action rows:\s*(\d+)\s*$")
    verdict = re.compile(r"^QA:\s*(PASS|FAIL)(?:\s|$)")
    records: list[dict[str, Any]] = []
    row: dict[str, Any] | None = None
    for line in path.read_text(encoding="utf-8").splitlines():
        match = start.match(line)
        if match:
            if row is not None:
                records.append(row)
            row = {"board_id": int(match.group(2)), "illegal": None, "verdict": None}
            continue
        if row is None:
            continue
        match = illegal.match(line)
        if match:
            row["illegal"] = int(match.group(1))
        match = verdict.match(line)
        if match:
            row["verdict"] = match.group(1)
    if row is not None:
        records.append(row)
    latest: dict[int, dict[str, Any]] = {}
    for record in records:
        latest[int(record["board_id"])] = record
    return records, latest


def recompute_inventory(
    selected: list[int], gzip_files: dict[int, Path], meta_files: dict[int, Path]
) -> tuple[str, dict[int, dict[str, Any]], list[int]]:
    lines: list[str] = []
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
            lines.append(
                "|".join(
                    [
                        str(board_id),
                        str(gzip_path.resolve()),
                        str(gzip_stat.st_size),
                        str(gzip_stat.st_mtime_ns),
                        str(meta_path.resolve()),
                        str(meta_stat.st_size),
                        str(meta_stat.st_mtime_ns),
                        sha256_file(meta_path),
                    ]
                )
            )
        except (OSError, ValueError, json.JSONDecodeError):
            malformed.append(board_id)
    return hashlib.sha256("\n".join(lines).encode("utf-8")).hexdigest(), metadata, malformed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--preregistration-audit", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--expected-result-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise FileExistsError(f"immutable output already exists: {args.output}")

    prereg = load_json(args.preregistration)
    prereg_audit = load_json(args.preregistration_audit)
    result = load_json(args.result)
    frozen = prereg["frozen_inputs"]
    selected_doc = load_json(Path(frozen["selection_manifest"]["path"]))
    status = load_json(Path(frozen["solver_status"]["path"]))
    selected = [int(value) for value in selected_doc["selectedBoardIds"]]
    selected_set = set(selected)
    directory = Path(frozen["asset_directory"])
    gzip_files = collect(directory, r"flop_(\d+)\.jsonl\.gz")
    meta_files = collect(directory, r"flop_(\d+)\.meta\.json")
    gzip_ids = set(gzip_files)
    meta_ids = set(meta_files)
    inventory_sha, metadata, malformed = recompute_inventory(selected, gzip_files, meta_files)
    qa_records, latest = parse_latest_qa(Path(frozen["qa_log"]["path"]))

    meta_bad = sorted(
        board_id
        for board_id, meta in metadata.items()
        if meta.get("boardId") != board_id
        or meta.get("config") != "pipeline_srp_v3_200bb"
        or meta.get("iterations") != 80000
    )
    valid: list[int] = []
    for board_id in selected:
        qa = latest.get(board_id)
        if (
            board_id in gzip_ids
            and board_id in meta_ids
            and gzip_files[board_id].stat().st_size > 0
            and board_id in metadata
            and board_id not in malformed
            and board_id not in meta_bad
            and qa is not None
            and qa.get("verdict") == "PASS"
            and qa.get("illegal") == 0
        ):
            valid.append(board_id)

    missing_gzip = sorted(selected_set - gzip_ids)
    missing_meta = sorted(selected_set - meta_ids)
    latest_fail = sorted(
        board_id for board_id in selected if board_id in latest and latest[board_id].get("verdict") != "PASS"
    )
    latest_illegal = sorted(
        board_id for board_id in selected if board_id in latest and latest[board_id].get("illegal") != 0
    )
    unresolved = sorted(
        set(missing_gzip)
        | set(missing_meta)
        | set(malformed)
        | set(meta_bad)
        | set(selected_set - set(latest))
        | set(latest_fail)
        | set(latest_illegal)
    )
    try:
        process = psutil.Process(int(prereg["lifecycle_contract"]["registered_coordinator_pid"]))
        process.create_time()
        coordinator_absent = False
    except psutil.NoSuchProcess:
        coordinator_absent = True

    checks = {
        "result_hash": sha256_file(args.result) == args.expected_result_sha256,
        "preregistration_hash": sha256_file(args.preregistration) == PREREG_SHA256,
        "preregistration_audit_hash": sha256_file(args.preregistration_audit) == PREREG_AUDIT_SHA256,
        "preregistration_audit_pass_35_of_35": prereg_audit.get("overall") == "PASS"
        and prereg_audit.get("checks_passed") == 35
        and prereg_audit.get("checks_total") == 35,
        "all_frozen_input_hashes": all(
            sha256_file(Path(frozen[name]["path"])) == frozen[name]["sha256"]
            for name in ("asset_lock", "progress_553", "selection_manifest", "solver_status", "qa_log", "parallel_log")
        ),
        "selection_target_600": selected_doc.get("targetBoards") == 600 and len(selected) == 600,
        "selection_ids_unique": len(selected_set) == 600,
        "selection_config_seed_method_exact": selected_doc.get("config") == "pipeline_srp_v3_200bb"
        and selected_doc.get("selectionSeed") == 20260712
        and selected_doc.get("method") == "isomorphism_multiplicity_weighted_texture_stratified_v1",
        "gzip_count_599": len(gzip_ids) == 599,
        "meta_count_599": len(meta_ids) == 599,
        "pair_identity_sets_equal": gzip_ids == meta_ids,
        "missing_board_exactly_1747": missing_gzip == [1747] and missing_meta == [1747],
        "no_unselected_gzip_or_meta": not (gzip_ids - selected_set) and not (meta_ids - selected_set),
        "all_present_gzip_nonempty": all(path.stat().st_size > 0 for path in gzip_files.values()),
        "all_present_meta_parse": not malformed,
        "all_present_meta_identity_pass": not meta_bad,
        "inventory_digest_recomputed": inventory_sha == result["asset_closure"]["inventory_sha256"],
        "qa_record_count_605": len(qa_records) == 605,
        "qa_latest_unique_count_600": len(latest) == 600,
        "latest_valid_pair_count_599": len(valid) == 599,
        "unresolved_board_exactly_1747": unresolved == [1747],
        "latest_qa_fail_exactly_1747": latest_fail == [1747],
        "latest_qa_illegal_rows_all_zero": latest_illegal == [],
        "solver_terminal_status_exact": status.get("status") == "COMPLETED_WITH_QA_FAILURES",
        "solver_selected_complete_599_of_600": status.get("selectedComplete") == 599
        and status.get("targetBoards") == 600,
        "solver_failed_one": status.get("failed") == 1,
        "registered_coordinator_absent": coordinator_absent,
        "terminal_incomplete_rule_applied": result.get("verdict") == "FAIL"
        and result.get("classification") == "PCV015_FAIL_CLOSED_PATH1_TERMINAL_INCOMPLETE_NO_RESTART",
        "result_selection_matches": result["selection"]["selected_board_count"] == 600
        and result["selection"]["identity_contract_pass"] is True,
        "result_asset_counts_match": result["asset_closure"]["gzip_count"] == 599
        and result["asset_closure"]["meta_count"] == 599
        and result["asset_closure"]["valid_pair_count"] == 599,
        "result_missing_identity_matches": result["asset_closure"]["missing_gzip"] == [1747]
        and result["asset_closure"]["missing_meta"] == [1747],
        "result_lifecycle_terminal_absent": result["lifecycle"]["state"] == "TERMINAL_ABSENT",
        "no_gzip_decompression": result["asset_closure"]["gzip_content_decompressed"] is False,
        "no_path1_mutation_restart_or_repair": result["policy"]["path1_write_or_signal"] is False
        and result["policy"]["path1_restart_repair_replace_or_expand"] is False,
        "no_gpu_trainer_evaluator_checkpoint_or_prior_rows": result["policy"]["gpu_workload_started"] is False
        and result["policy"]["trainer_evaluator_mirror_or_slumbot_started"] is False
        and result["policy"]["checkpoint_written"] is False
        and result["policy"]["prior_timing_rows_read"] is False,
        "no_h19_official_hands_or_strength_authority": result["interpretation"]["automatic_h19_or_later_launch"] is False
        and result["official_hands"] == 0
        and result["behavior_launch_authority"] == "NONE"
        and result["interpretation"]["timing_method_behavior_or_strength_inference"] == "FORBIDDEN",
        "route_review027_required": result["interpretation"]["next"] == "SEPARATELY_REGISTERED_ROUTE_REVIEW027",
    }
    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv015.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "result_sha256": args.expected_result_sha256,
        "classification": result.get("classification"),
        "checks": checks,
        "checks_passed": sum(bool(value) for value in checks.values()),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "path1_action_authority": "NONE",
        "behavior_launch_authority": "NONE",
        "official_hands": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8", newline="\n") as handle:
        json.dump(audit, handle, indent=2)
        handle.write("\n")
    print(json.dumps({"overall": audit["overall"], "checks": f"{audit['checks_passed']}/{audit['checks_total']}"}))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
