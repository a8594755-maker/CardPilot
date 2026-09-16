#!/usr/bin/env python3
"""One-time converter from the compact legacy memory into the fixed experiment log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import experiment_log


def fixed_status(value: str) -> str:
    upper = value.upper()
    if "RUNNING" in upper or "ACTIVE" in upper:
        return "RUNNING"
    if "FAILED" in upper or "INVALID" in upper:
        return "FAILED"
    if "STOP" in upper:
        return "STOPPED"
    return "COMPLETED"


def base_record(
    run_id: str,
    title: str,
    status: str,
    timestamp: str,
    source: str,
    summary: str,
    decision: str,
    next_step: str,
) -> dict[str, Any]:
    return {
        "schema": experiment_log.SCHEMA,
        "id": run_id,
        "title": title,
        "status": status,
        "created_at": timestamp,
        "updated_at": timestamp,
        "started_at": None,
        "ended_at": timestamp if status != "RUNNING" else None,
        "benchmark": experiment_log.BENCHMARK,
        "hypothesis": "Imported historical route; consult the named source for the original hypothesis.",
        "material_change": "Historical evidence imported into the fixed experiment-memory format.",
        "baseline": "See source record.",
        "source": source,
        "parent_id": None,
        "command": "",
        "code": {"commit": None, "branch": None, "dirty": None},
        "runtime": {"imported_from": "reports/cardpilot_research_memory_current.json"},
        "accounting": {
            "new_training_hands": None,
            "lineage_training_hands": None,
            "offline_samples": None,
            "evaluation_hands": None,
            "wall_time_seconds": None,
        },
        "metrics": {},
        "artifacts": [source] if source else [],
        "notes": ["Imported summary; unknown fields were not reconstructed."],
        "result": {
            "summary": summary,
            "conclusion": decision,
            "decision": decision,
            "next_step": next_step,
        },
        "tags": ["legacy-import"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parent / "experiments",
    )
    args = parser.parse_args()
    memory = json.loads(args.source.read_text(encoding="utf-8"))
    timestamp = memory["updated_at_utc"].replace("Z", "+00:00")
    root = args.root.resolve()

    with experiment_log.log_lock(root):
        for route in memory.get("terminal_or_bounded_routes", []):
            run_id = "legacy-" + experiment_log.slugify(route["route_id"])
            path = experiment_log.record_path(root, run_id)
            if path.exists():
                continue
            record = base_record(
                run_id=run_id,
                title=route["route_id"],
                status=fixed_status(route["status"]),
                timestamp=timestamp,
                source=route.get("authoritative_record", ""),
                summary=route.get("evidence", ""),
                decision=route.get("status", ""),
                next_step=route.get("materially_new_if", ""),
            )
            record["result"]["conclusion"] = route.get("do_not_repeat_unchanged", "")
            experiment_log.atomic_json(path, record)

        current = memory.get("current_state", {})
        best = current.get("best_mature_external")
        if best:
            run_id = "legacy-best-mature-external-reference"
            path = experiment_log.record_path(root, run_id)
            if not path.exists():
                ci95 = best.get("ci95", [None, None])
                summary = (
                    f"{best.get('policy')}: {best.get('bb_per_100')} bb/100 over "
                    f"{best.get('evaluation_hands')} hands; CI95 {ci95}. {best.get('claim', '')}"
                )
                record = base_record(
                    run_id, "Best mature external reference", "COMPLETED", timestamp,
                    "reports/cardpilot_external_result_inventory_20260824.md", summary,
                    "RETAIN_AS_REFERENCE_NOT_SUCCESS", "Train and freeze a stronger learned policy.",
                )
                record["accounting"]["lineage_training_hands"] = best.get("lineage_training_hands")
                record["accounting"]["evaluation_hands"] = best.get("evaluation_hands")
                record["metrics"] = {
                    "bb_per_100": best.get("bb_per_100"),
                    "ci95_lower": ci95[0],
                    "ci95_upper": ci95[1],
                    "checkpoint_sha256": best.get("checkpoint_sha256"),
                }
                experiment_log.atomic_json(path, record)

        active = current.get("active_route")
        if active:
            run_id = "legacy-active-" + experiment_log.slugify(active["route_id"])
            path = experiment_log.record_path(root, run_id)
            if not path.exists():
                record = base_record(
                    run_id, active["route_id"], "RUNNING", timestamp,
                    active.get("record", ""), active.get("status", "RUNNING"),
                    "MIGRATED_ACTIVE_ROUTE", active.get("next_gate", ""),
                )
                record["accounting"]["new_training_hands"] = active.get("new_training_hands")
                record["accounting"]["lineage_training_hands"] = active.get(
                    "source_lineage_training_hands"
                )
                experiment_log.atomic_json(path, record)

        records = experiment_log.rebuild_index(root)
    print(f"Imported/indexed {len(records)} experiment records")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
