#!/usr/bin/env python3
"""New PCV010 order-balanced CUDA timing with phase-aware Path-1 identity."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import (
    active_forbidden_processes,
    deterministic_transitions,
    sha256,
    transition_sha256,
)
from v5_hybrid_h18_perf_cal import forced_shape, gpu_event_update
from v5_pcv008_run import TELEMETRY_KEYS, median, numeric_range, telemetry
from v5_pcv009_run import snapshot as resource_snapshot


PREREG_SHA = "34de730dc44775e88d7af408abd07d4f7096ffec53573ee28a5c3e70b0de3960"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TRANSITION_SEED = 2026071986
UPDATE_SEED = 2026971986
ORDERS = (
    "MSE_FIRST", "SMOOTH_L1_FIRST", "SMOOTH_L1_FIRST", "MSE_FIRST",
    "SMOOTH_L1_FIRST", "MSE_FIRST", "MSE_FIRST", "SMOOTH_L1_FIRST",
)
COMMAND_SHA = "efaf227352c6620b4f12dd5f06ac67d98d834feb11384b167170618dc1cf9e99"
CREATE_TIME = 1784302339.7041352


def resource_pass(row: dict[str, Any]) -> bool:
    counts = row["role_counts"]
    return (
        row["coordinator_pid"] == 23720
        and math.isclose(row["coordinator_create_time"], CREATE_TIME, rel_tol=0.0, abs_tol=1e-6)
        and row["coordinator_command_sha256"] == COMMAND_SHA
        and row["coordinator_priority"] == 16384
        and counts["unknown"] == 0
        and 1 <= counts["active_work"] <= 6
        and row["node_child_priorities_below_normal"] is True
        and row["descendant_gpu_pid_intersection"] == []
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, choices=[23720], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV010 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV010 preregistration/source identity mismatch")
    if not torch.cuda.is_available():
        raise SystemExit("PCV010 CUDA unavailable")
    forbidden = active_forbidden_processes()
    if forbidden:
        raise SystemExit(f"PCV010 forbidden process(es): {forbidden}")
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
        raise SystemExit("PCV010 source iteration/hands mismatch")
    transitions = deterministic_transitions(checkpoint, "cuda", TRANSITION_SEED, 4096)

    blocks: list[dict[str, Any]] = []
    all_stats: list[dict[str, Any]] = []
    resource_rows: list[dict[str, Any]] = []
    for block_index, order_name in enumerate(ORDERS):
        modes = ("mse", "smooth_l1") if order_name == "MSE_FIRST" else ("smooth_l1", "mse")
        phase_before = resource_snapshot(args.path1_pid, block_index * 2)
        if not resource_pass(phase_before):
            raise RuntimeError(f"PCV010 phase-aware resource gate failed before block {block_index}")
        resource_rows.append(phase_before)
        device_before = telemetry()
        for mode in modes:
            for warmup_index in range(2):
                _, stats = gpu_event_update(
                    checkpoint, transitions, mode,
                    UPDATE_SEED + 100000 + block_index * 100 + warmup_index,
                    1024, 4, 1e-12,
                )
                all_stats.append(stats)
        values: dict[str, list[float]] = {"mse": [], "smooth_l1": []}
        for mode in modes:
            for update_index in range(12):
                elapsed_ms, stats = gpu_event_update(
                    checkpoint, transitions, mode,
                    UPDATE_SEED + 200000 + block_index * 100 + update_index,
                    1024, 4, 1e-12,
                )
                if not forced_shape(stats):
                    raise RuntimeError("PCV010 timed update violated forced shape")
                values[mode].append(elapsed_ms)
                all_stats.append(stats)
        device_after = telemetry()
        phase_after = resource_snapshot(args.path1_pid, block_index * 2 + 1)
        if not resource_pass(phase_after):
            raise RuntimeError(f"PCV010 phase-aware resource gate failed after block {block_index}")
        resource_rows.append(phase_after)
        blocks.append({
            "block_index": block_index,
            "order": order_name,
            "mode_sequence": list(modes),
            "resource_before": phase_before,
            "device_telemetry_before": device_before,
            "raw_milliseconds": values,
            "median_milliseconds": {mode: median(values[mode]) for mode in values},
            "device_telemetry_after": device_after,
            "resource_after": phase_after,
        })

    block_medians = {
        mode: [float(block["median_milliseconds"][mode]) for block in blocks]
        for mode in ("mse", "smooth_l1")
    }
    first = {
        "mse": [float(block["median_milliseconds"]["mse"]) for block in blocks if block["order"] == "MSE_FIRST"],
        "smooth_l1": [float(block["median_milliseconds"]["smooth_l1"]) for block in blocks if block["order"] == "SMOOTH_L1_FIRST"],
    }
    second = {
        "mse": [float(block["median_milliseconds"]["mse"]) for block in blocks if block["order"] == "SMOOTH_L1_FIRST"],
        "smooth_l1": [float(block["median_milliseconds"]["smooth_l1"]) for block in blocks if block["order"] == "MSE_FIRST"],
    }
    order_effect = {mode: median(second[mode]) / median(first[mode]) for mode in first}
    aggregate = {mode: median(block_medians[mode]) for mode in block_medians}
    all_telemetry = [block[moment] for block in blocks for moment in ("device_telemetry_before", "device_telemetry_after")]
    telemetry_ranges = {key: numeric_range(all_telemetry, key) for key in TELEMETRY_KEYS[2:]}
    order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in order_effect.values())
    device_excursion = telemetry_ranges["temperature_gpu_c"] >= 5.0 or telemetry_ranges["clocks_sm_mhz"] >= 100.0 or telemetry_ranges["power_draw_w"] >= 30.0
    if order_associated and device_excursion:
        attribution = "ORDER_ASSOCIATION_AND_DEVICE_STATE_EXCURSION_OBSERVED"
    elif order_associated:
        attribution = "ORDER_ASSOCIATION_OBSERVED"
    elif device_excursion:
        attribution = "DEVICE_STATE_EXCURSION_OBSERVED"
    else:
        attribution = "TIMING_JITTER_UNRESOLVED_WITHIN_FROZEN_SENSITIVITY"

    timing_finite = all(math.isfinite(value) and value > 0 for block in blocks for mode in ("mse", "smooth_l1") for value in block["raw_milliseconds"][mode])
    telemetry_complete = len(all_telemetry) == 16 and all(all(key in row for key in ("sampled_at",) + TELEMETRY_KEYS) for row in all_telemetry)
    resource_complete = len(resource_rows) == 16 and all(resource_pass(row) for row in resource_rows)
    gates = {
        "source_identity_pass": True,
        "new_seed_and_output_identity_pass": True,
        "exact_measurement_shape_pass": len(blocks) == 8 and tuple(block["order"] for block in blocks) == ORDERS and all(len(block["raw_milliseconds"][mode]) == 12 for block in blocks for mode in ("mse", "smooth_l1")),
        "all_updates_forced_shape_pass": all(forced_shape(stats) for stats in all_stats),
        "all_timing_finite_positive_pass": timing_finite,
        "all_device_telemetry_complete_pass": telemetry_complete,
        "all_sixteen_phase_aware_resource_snapshots_pass": resource_complete,
        "path1_mutation_absent_pass": True,
        "trainer_started_false_pass": True,
        "checkpoint_written_false_pass": True,
        "official_hands_zero_pass": True,
    }
    passed = all(gates.values())
    result = {
        "schema_version": "v5.pcv010.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "classification": "PCV010_PASS_MEASUREMENT_COMPLETE" if passed else "PCV010_FAIL_CLOSED",
        "attribution": attribution,
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": SOURCE_ITERATION, "hands": SOURCE_HANDS},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED, "update_seed": UPDATE_SEED,
            "timer": "torch.cuda.Event_with_synchronize", "blocks": 8,
            "warmup_updates_per_mode_per_block": 2, "timed_updates_per_mode_per_block": 12,
            "order_sequence": list(ORDERS), "transition_sha256": transition_sha256(transitions),
            "phase_aware_resource_snapshots": 16,
        },
        "blocks": blocks,
        "summaries": {
            "block_median_milliseconds": block_medians,
            "aggregate_mode_median_milliseconds": aggregate,
            "aggregate_mse_stability_min_over_max": min(block_medians["mse"]) / max(block_medians["mse"]),
            "order_stratified_first_median_milliseconds": {mode: median(first[mode]) for mode in first},
            "order_stratified_second_median_milliseconds": {mode: median(second[mode]) for mode in second},
            "order_effect_ratio_second_over_first": order_effect,
            "aggregate_mse_over_smooth_l1_ratio": aggregate["mse"] / aggregate["smooth_l1"],
            "telemetry_ranges": telemetry_ranges,
            "resource_solve_worker_count_range": [min(row["role_counts"]["solve_worker"] for row in resource_rows), max(row["role_counts"]["solve_worker"] for row in resource_rows)],
            "resource_qa_child_count_range": [min(row["role_counts"]["qa_200bb_board"] for row in resource_rows), max(row["role_counts"]["qa_200bb_board"] for row in resource_rows)],
            "resource_active_work_count_range": [min(row["role_counts"]["active_work"] for row in resource_rows), max(row["role_counts"]["active_work"] for row in resource_rows)],
            "resource_unknown_role_count": sum(row["role_counts"]["unknown"] for row in resource_rows),
            "resource_gpu_pid_match_count": sum(len(row["descendant_gpu_pid_intersection"]) for row in resource_rows),
            "order_associated_threshold_log": math.log(1.01),
            "order_associated": order_associated,
            "device_excursion": device_excursion,
        },
        "gates": gates,
        "forbidden_processes": forbidden,
        "path1_mutation": False,
        "pcv008_data_read_or_reconstructed": False,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "behavior_method_or_strength_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW022_ONLY",
        "dependency_sha256": {
            "pcv008_measurement_helpers": hashlib.sha256(Path(__file__).with_name("v5_pcv008_run.py").read_bytes()).hexdigest(),
            "pcv009_resource_snapshot": hashlib.sha256(Path(__file__).with_name("v5_pcv009_run.py").read_bytes()).hexdigest(),
            "h18_full_update": hashlib.sha256(Path(__file__).with_name("v5_hybrid_h18_perf_cal.py").read_bytes()).hexdigest(),
        },
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "classification": result["classification"], "attribution": attribution, "summaries": result["summaries"], "gates": gates}, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
