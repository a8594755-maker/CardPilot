#!/usr/bin/env python3
"""Independent fail-closed audit for immutable PCV008 timing attribution."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from v5_hybrid_h17_perf_cal import active_forbidden_processes, path1_identity


PREREG_SHA = "3df3d6c12e1b169cc08657d040d0407f03b1e3300754fe6396cb95a4d454dded"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
ORDERS = (
    "MSE_FIRST", "SMOOTH_L1_FIRST", "SMOOTH_L1_FIRST", "MSE_FIRST",
    "SMOOTH_L1_FIRST", "MSE_FIRST", "MSE_FIRST", "SMOOTH_L1_FIRST",
)
NUMERIC_TELEMETRY = (
    "temperature_gpu_c", "clocks_sm_mhz", "clocks_mem_mhz", "power_draw_w",
    "utilization_gpu_pct", "memory_used_mib",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def close(left: float, right: float) -> bool:
    return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12)


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def valid_path1(row: dict[str, Any]) -> bool:
    return (
        row.get("changed") is False and row.get("coordinator_pid") == 23720
        and row.get("priority") == "BelowNormal" and row.get("worker_count") == 6
        and row.get("gpu_use") is False and len(row.get("worker_pids", [])) == 6
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--dependency", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, required=True)
    parser.add_argument("--path1-workers", type=int, choices=[6], default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV008 audit")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    blocks = result["blocks"]
    summaries = result["summaries"]
    block_medians = {
        mode: [median([float(value) for value in block["raw_milliseconds"][mode]]) for block in blocks]
        for mode in ("mse", "smooth_l1")
    }
    first = {
        "mse": [block_medians["mse"][index] for index, order in enumerate(ORDERS) if order == "MSE_FIRST"],
        "smooth_l1": [block_medians["smooth_l1"][index] for index, order in enumerate(ORDERS) if order == "SMOOTH_L1_FIRST"],
    }
    second = {
        "mse": [block_medians["mse"][index] for index, order in enumerate(ORDERS) if order == "SMOOTH_L1_FIRST"],
        "smooth_l1": [block_medians["smooth_l1"][index] for index, order in enumerate(ORDERS) if order == "MSE_FIRST"],
    }
    aggregate = {mode: median(block_medians[mode]) for mode in block_medians}
    effects = {mode: median(second[mode]) / median(first[mode]) for mode in first}
    telemetry_rows = [block[moment] for block in blocks for moment in ("telemetry_before", "telemetry_after")]
    ranges = {
        key: max(float(row[key]) for row in telemetry_rows) - min(float(row[key]) for row in telemetry_rows)
        for key in NUMERIC_TELEMETRY
    }
    order_associated = any(abs(math.log(value)) >= math.log(1.01) for value in effects.values())
    device_excursion = ranges["temperature_gpu_c"] >= 5.0 or ranges["clocks_sm_mhz"] >= 100.0 or ranges["power_draw_w"] >= 30.0
    if order_associated and device_excursion:
        attribution = "ORDER_ASSOCIATION_AND_DEVICE_STATE_EXCURSION_OBSERVED"
    elif order_associated:
        attribution = "ORDER_ASSOCIATION_OBSERVED"
    elif device_excursion:
        attribution = "DEVICE_STATE_EXCURSION_OBSERVED"
    else:
        attribution = "TIMING_JITTER_UNRESOLVED_WITHIN_FROZEN_SENSITIVITY"
    live_path1 = path1_identity(args.path1_pid, args.path1_workers)
    forbidden = active_forbidden_processes()
    workload = result["workload"]
    checks = {
        "preregistration_binding": sha256(args.preregistration) == PREREG_SHA and result["preregistration_sha256"] == PREREG_SHA,
        "source_identity": sha256(args.source) == SOURCE_SHA and result["source"] == {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": 35051, "hands": 576021901},
        "runner_binding": sha256(args.runner) == result["tool_sha256"],
        "dependency_binding": sha256(args.dependency) == result["dependency_sha256"],
        "workload_identity": all((
            workload["rows"] == 4096, workload["mini_batch_size"] == 1024,
            workload["ppo_epochs"] == 4, close(workload["target_kl"], 1e-12),
            close(workload["old_log_prob_offset"], 10.0), workload["transition_seed"] == 2026071984,
            workload["update_seed"] == 2026971984, workload["timer"] == "torch.cuda.Event_with_synchronize",
            workload["blocks"] == 8, workload["warmup_updates_per_mode_per_block"] == 2,
            workload["timed_updates_per_mode_per_block"] == 12, tuple(workload["order_sequence"]) == ORDERS,
        )),
        "block_and_order_dimensions": len(blocks) == 8 and tuple(block["order"] for block in blocks) == ORDERS,
        "timing_dimensions": all(len(block["raw_milliseconds"][mode]) == 12 for block in blocks for mode in ("mse", "smooth_l1")),
        "timing_finite_positive": all(math.isfinite(float(value)) and float(value) > 0 for block in blocks for mode in ("mse", "smooth_l1") for value in block["raw_milliseconds"][mode]),
        "telemetry_dimensions": len(telemetry_rows) == 16,
        "telemetry_complete_finite": all(row.get("uuid") and row.get("pstate") and all(math.isfinite(float(row[key])) for key in NUMERIC_TELEMETRY) for row in telemetry_rows),
        "block_medians_recomputed": all(close(block_medians[mode][index], summaries["block_median_milliseconds"][mode][index]) for mode in block_medians for index in range(8)),
        "aggregate_medians_recomputed": all(close(aggregate[mode], summaries["aggregate_mode_median_milliseconds"][mode]) for mode in aggregate),
        "stability_recomputed": close(min(block_medians["mse"]) / max(block_medians["mse"]), summaries["aggregate_mse_stability_min_over_max"]),
        "order_strata_recomputed": all(close(median(first[mode]), summaries["order_stratified_first_median_milliseconds"][mode]) and close(median(second[mode]), summaries["order_stratified_second_median_milliseconds"][mode]) for mode in first),
        "order_effects_recomputed": all(close(effects[mode], summaries["order_effect_ratio_second_over_first"][mode]) for mode in effects),
        "aggregate_ratio_recomputed": close(aggregate["mse"] / aggregate["smooth_l1"], summaries["aggregate_mse_over_smooth_l1_ratio"]),
        "telemetry_ranges_recomputed": all(close(ranges[key], summaries["telemetry_ranges"][key]) for key in ranges),
        "attribution_rule_recomputed": result["attribution"] == attribution and summaries["order_associated"] is order_associated and summaries["device_excursion"] is device_excursion,
        "registered_completion_gates": all(result["gates"].values()),
        "classification_exact": result["overall"] == "PASS" and result["classification"] == "PCV008_PASS_MEASUREMENT_COMPLETE",
        "path1_unchanged": valid_path1(result["path1_before"]) and valid_path1(result["path1_after"]) and valid_path1(live_path1),
        "trainerless_no_checkpoint": result["trainer_started"] is False and result["checkpoint_written"] is False and forbidden == [],
        "no_official_or_inference": result["official_hands"] == 0 and result["behavior_method_or_strength_inference"] == "FORBIDDEN" and result["next_authority"] == "ROUTE_REVIEW020_ONLY",
    }
    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv008.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.result),
        "runner_sha256": sha256(args.runner),
        "checks": checks,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": result["classification"] if not failed else "PCV008_AUDIT_FAIL_CLOSED",
        "recomputed": {
            "attribution": attribution,
            "aggregate_mse_stability_min_over_max": min(block_medians["mse"]) / max(block_medians["mse"]),
            "order_effect_ratio_second_over_first": effects,
            "aggregate_mse_over_smooth_l1_ratio": aggregate["mse"] / aggregate["smooth_l1"],
            "telemetry_ranges": ranges,
        },
        "official_hands": 0,
        "behavior_launch_authority": "NONE_ROUTE_REVIEW020_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": audit["overall"], "passed": audit["checks_passed"], "total": audit["checks_total"], "failed": failed, "recomputed": audit["recomputed"]}, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
