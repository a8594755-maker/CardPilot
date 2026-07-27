#!/usr/bin/env python3
"""PCV011 thermal-steady-state CUDA timing replication (reporting only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import active_forbidden_processes, deterministic_transitions, sha256, transition_sha256
from v5_hybrid_h18_perf_cal import forced_shape, gpu_event_update
from v5_pcv008_run import TELEMETRY_KEYS, median, numeric_range, telemetry
from v5_pcv009_run import snapshot as resource_snapshot


PREREG_SHA = "81e7f9b97422ec776ee63b540ac7cbda7948b2a23fc9504b733427524df9730b"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TRANSITION_SEED = 2026071987
UPDATE_SEED = 2026971987
CONDITIONING_SEED_BASE = 2027971987
ORDERS = (
    "MSE_FIRST", "SMOOTH_L1_FIRST", "SMOOTH_L1_FIRST", "MSE_FIRST",
    "SMOOTH_L1_FIRST", "MSE_FIRST", "MSE_FIRST", "SMOOTH_L1_FIRST",
)
COMMAND_SHA = "efaf227352c6620b4f12dd5f06ac67d98d834feb11384b167170618dc1cf9e99"
CREATE_TIME = 1784302339.7041352
CONDITIONING_MIN_SECONDS = 60.0
CONDITIONING_MAX_SECONDS = 180.0
TELEMETRY_INTERVAL_SECONDS = 5.0
STEADY_SAMPLES = 4
STEADY_LIMITS = {
    "temperature_gpu_c": 3.0,
    "clocks_sm_mhz": 100.0,
    "clocks_mem_mhz": 100.0,
    "power_draw_w": 30.0,
}


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


def steady_window(rows: list[dict[str, Any]]) -> tuple[bool, dict[str, Any]]:
    if len(rows) < STEADY_SAMPLES:
        return False, {"samples": len(rows)}
    window = rows[-STEADY_SAMPLES:]
    ranges = {key: numeric_range(window, key) for key in STEADY_LIMITS}
    pstates = sorted({str(row["pstate"]) for row in window})
    uuids = sorted({str(row["uuid"]) for row in window})
    passed = (
        all(ranges[key] <= limit for key, limit in STEADY_LIMITS.items())
        and len(pstates) == 1
        and len(uuids) == 1
    )
    return passed, {"samples": STEADY_SAMPLES, "ranges": ranges, "pstates": pstates, "uuids": uuids}


def write_result(path: Path, result: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, choices=[23720], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV011 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV011 preregistration/source identity mismatch")
    if not torch.cuda.is_available():
        raise SystemExit("PCV011 CUDA unavailable")
    forbidden = active_forbidden_processes()
    if forbidden:
        raise SystemExit(f"PCV011 forbidden process(es): {forbidden}")
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
        raise SystemExit("PCV011 source iteration/hands mismatch")
    transitions = deterministic_transitions(checkpoint, "cuda", TRANSITION_SEED, 4096)

    resource_rows: list[dict[str, Any]] = []
    all_stats: list[dict[str, Any]] = []
    conditioning_rows: list[dict[str, Any]] = []
    conditioning_before = resource_snapshot(args.path1_pid, 0)
    resource_rows.append(conditioning_before)
    if not resource_pass(conditioning_before):
        raise RuntimeError("PCV011 phase-aware resource gate failed before conditioning")

    start = time.monotonic()
    next_sample = start
    pair_index = 0
    conditioning_pass = False
    conditioning_window: dict[str, Any] = {"samples": 0}
    while True:
        for mode in ("mse", "smooth_l1"):
            _, stats = gpu_event_update(
                checkpoint, transitions, mode, CONDITIONING_SEED_BASE + pair_index,
                1024, 4, 1e-12,
            )
            if not forced_shape(stats):
                raise RuntimeError("PCV011 conditioning update violated forced shape")
            all_stats.append(stats)
        pair_index += 1
        now = time.monotonic()
        elapsed = now - start
        if now >= next_sample:
            row = telemetry()
            row["elapsed_seconds"] = elapsed
            conditioning_rows.append(row)
            next_sample = now + TELEMETRY_INTERVAL_SECONDS
            conditioning_pass, conditioning_window = steady_window(conditioning_rows)
            if elapsed >= CONDITIONING_MIN_SECONDS and conditioning_pass:
                break
            if elapsed >= CONDITIONING_MAX_SECONDS:
                break

    conditioning_after = resource_snapshot(args.path1_pid, 1)
    resource_rows.append(conditioning_after)
    conditioning_resource_pass = resource_pass(conditioning_after)
    conditioning_elapsed = time.monotonic() - start
    conditioning = {
        "minimum_seconds": CONDITIONING_MIN_SECONDS,
        "maximum_seconds": CONDITIONING_MAX_SECONDS,
        "telemetry_interval_seconds": TELEMETRY_INTERVAL_SECONDS,
        "steady_samples": STEADY_SAMPLES,
        "steady_limits": STEADY_LIMITS,
        "elapsed_seconds": conditioning_elapsed,
        "full_ppo_mode_pairs": pair_index,
        "telemetry": conditioning_rows,
        "terminal_window": conditioning_window,
        "envelope_pass": conditioning_pass,
        "resource_before": conditioning_before,
        "resource_after": conditioning_after,
    }

    base = {
        "schema_version": "v5.pcv011.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": SOURCE_ITERATION, "hands": SOURCE_HANDS},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED, "update_seed": UPDATE_SEED,
            "conditioning_seed_base": CONDITIONING_SEED_BASE,
            "timer": "torch.cuda.Event_with_synchronize", "blocks": 8,
            "warmup_updates_per_mode_per_block": 2, "timed_updates_per_mode_per_block": 12,
            "order_sequence": list(ORDERS), "transition_sha256": transition_sha256(transitions),
        },
        "conditioning": conditioning,
        "forbidden_processes": forbidden,
        "path1_mutation": False,
        "gpu_clock_override": False,
        "pcv010_measurement_data_read_or_reused": False,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "causal_method_behavior_or_strength_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW023_ONLY",
        "dependency_sha256": {
            "pcv008_measurement_helpers": hashlib.sha256(Path(__file__).with_name("v5_pcv008_run.py").read_bytes()).hexdigest(),
            "pcv009_resource_snapshot": hashlib.sha256(Path(__file__).with_name("v5_pcv009_run.py").read_bytes()).hexdigest(),
            "h18_full_update": hashlib.sha256(Path(__file__).with_name("v5_hybrid_h18_perf_cal.py").read_bytes()).hexdigest(),
        },
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    if not conditioning_pass or not conditioning_resource_pass:
        result = {
            **base,
            "overall": "FAIL_CLOSED",
            "classification": "PCV011_FAIL_CLOSED_STEADY_STATE_ENVELOPE_NO_MEASUREMENT",
            "attribution": "NO_MEASUREMENT_CONDITIONING_PREREQUISITE_FAILED",
            "blocks": [],
            "summaries": {},
            "gates": {
                "source_identity_pass": True,
                "new_seed_and_output_identity_pass": True,
                "conditioning_envelope_pass_before_measurement": conditioning_pass,
                "conditioning_resource_contract_pass": conditioning_resource_pass,
                "measurement_not_started_pass": True,
                "path1_mutation_absent_pass": True,
                "gpu_clock_override_false_pass": True,
                "trainer_started_false_pass": True,
                "checkpoint_written_false_pass": True,
                "official_hands_zero_pass": True,
            },
        }
        write_result(args.out, result)
        print(json.dumps({"overall": result["overall"], "classification": result["classification"], "conditioning": conditioning}, indent=2, sort_keys=True))
        return 2

    blocks: list[dict[str, Any]] = []
    for block_index, order_name in enumerate(ORDERS):
        modes = ("mse", "smooth_l1") if order_name == "MSE_FIRST" else ("smooth_l1", "mse")
        phase_before = resource_snapshot(args.path1_pid, 2 + block_index * 2)
        if not resource_pass(phase_before):
            raise RuntimeError(f"PCV011 phase-aware resource gate failed before block {block_index}")
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
                    raise RuntimeError("PCV011 timed update violated forced shape")
                values[mode].append(elapsed_ms)
                all_stats.append(stats)
        device_after = telemetry()
        phase_after = resource_snapshot(args.path1_pid, 3 + block_index * 2)
        if not resource_pass(phase_after):
            raise RuntimeError(f"PCV011 phase-aware resource gate failed after block {block_index}")
        resource_rows.append(phase_after)
        blocks.append({
            "block_index": block_index, "order": order_name, "mode_sequence": list(modes),
            "resource_before": phase_before, "device_telemetry_before": device_before,
            "raw_milliseconds": values,
            "median_milliseconds": {mode: median(values[mode]) for mode in values},
            "device_telemetry_after": device_after, "resource_after": phase_after,
        })

    block_medians = {mode: [float(block["median_milliseconds"][mode]) for block in blocks] for mode in ("mse", "smooth_l1")}
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
    stability = min(block_medians["mse"]) / max(block_medians["mse"])
    all_telemetry = [block[moment] for block in blocks for moment in ("device_telemetry_before", "device_telemetry_after")]
    telemetry_ranges = {key: numeric_range(all_telemetry, key) for key in TELEMETRY_KEYS[2:]}
    order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in order_effect.values())
    device_excursion = telemetry_ranges["temperature_gpu_c"] >= 5.0 or telemetry_ranges["clocks_sm_mhz"] >= 100.0 or telemetry_ranges["power_draw_w"] >= 30.0
    if device_excursion:
        attribution = "IN_MEASUREMENT_DEVICE_EXCURSION_PERSISTS"
    elif stability >= 0.95:
        attribution = "STEADY_STATE_ASSOCIATION_SUPPORTED"
    else:
        attribution = "STEADY_STATE_DID_NOT_RECOVER_STABILITY"

    timing_finite = all(math.isfinite(value) and value > 0 for block in blocks for mode in ("mse", "smooth_l1") for value in block["raw_milliseconds"][mode])
    telemetry_complete = len(all_telemetry) == 16 and all(all(key in row for key in ("sampled_at",) + TELEMETRY_KEYS) for row in all_telemetry)
    resource_complete = len(resource_rows) == 18 and all(resource_pass(row) for row in resource_rows)
    gates = {
        "source_identity_pass": True,
        "new_seed_and_output_identity_pass": True,
        "conditioning_envelope_pass_before_measurement": True,
        "conditioning_resource_contract_pass": True,
        "exact_measurement_shape_pass": len(blocks) == 8 and tuple(block["order"] for block in blocks) == ORDERS and all(len(block["raw_milliseconds"][mode]) == 12 for block in blocks for mode in ("mse", "smooth_l1")),
        "all_updates_forced_shape_pass": all(forced_shape(stats) for stats in all_stats),
        "all_timing_finite_positive_pass": timing_finite,
        "all_device_telemetry_complete_pass": telemetry_complete,
        "all_eighteen_phase_aware_resource_snapshots_pass": resource_complete,
        "path1_mutation_absent_pass": True,
        "gpu_clock_override_false_pass": True,
        "trainer_started_false_pass": True,
        "checkpoint_written_false_pass": True,
        "official_hands_zero_pass": True,
    }
    passed = all(gates.values())
    result = {
        **base,
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "classification": "PCV011_PASS_MEASUREMENT_COMPLETE" if passed else "PCV011_FAIL_CLOSED",
        "attribution": attribution,
        "blocks": blocks,
        "summaries": {
            "block_median_milliseconds": block_medians,
            "aggregate_mode_median_milliseconds": aggregate,
            "aggregate_mse_stability_min_over_max": stability,
            "pcv010_mse_stability_reference": 0.9443019963767163,
            "mse_stability_target": 0.95,
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
    }
    write_result(args.out, result)
    print(json.dumps({"overall": result["overall"], "classification": result["classification"], "attribution": attribution, "conditioning": {"elapsed_seconds": conditioning_elapsed, "pairs": pair_index, "terminal_window": conditioning_window}, "summaries": result["summaries"], "gates": gates}, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
