#!/usr/bin/env python3
"""Trainerless PCV008 order-balanced CUDA timing jitter attribution."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import (
    active_forbidden_processes,
    deterministic_transitions,
    path1_identity,
    sha256,
    transition_sha256,
)
from v5_hybrid_h18_perf_cal import forced_shape, gpu_event_update


PREREG_SHA = "3df3d6c12e1b169cc08657d040d0407f03b1e3300754fe6396cb95a4d454dded"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TRANSITION_SEED = 2026071984
UPDATE_SEED = 2026971984
ORDERS = (
    "MSE_FIRST", "SMOOTH_L1_FIRST", "SMOOTH_L1_FIRST", "MSE_FIRST",
    "SMOOTH_L1_FIRST", "MSE_FIRST", "MSE_FIRST", "SMOOTH_L1_FIRST",
)
QUERY_FIELDS = (
    "uuid", "pstate", "temperature.gpu", "clocks.sm", "clocks.mem",
    "power.draw", "utilization.gpu", "memory.used",
)
TELEMETRY_KEYS = (
    "uuid", "pstate", "temperature_gpu_c", "clocks_sm_mhz", "clocks_mem_mhz",
    "power_draw_w", "utilization_gpu_pct", "memory_used_mib",
)


def telemetry() -> dict[str, Any]:
    command = [
        "nvidia-smi", f"--query-gpu={','.join(QUERY_FIELDS)}",
        "--format=csv,noheader,nounits",
    ]
    output = subprocess.check_output(command, text=True, encoding="utf-8", errors="strict").strip().splitlines()
    if len(output) != 1:
        raise RuntimeError(f"expected one GPU telemetry row, got {len(output)}")
    values = [value.strip() for value in output[0].split(",")]
    if len(values) != len(TELEMETRY_KEYS):
        raise RuntimeError("GPU telemetry field count mismatch")
    row: dict[str, Any] = {
        "sampled_at": datetime.now(timezone.utc).isoformat(),
        "uuid": values[0],
        "pstate": values[1],
    }
    for key, value in zip(TELEMETRY_KEYS[2:], values[2:]):
        parsed = float(value)
        if not math.isfinite(parsed):
            raise RuntimeError(f"non-finite GPU telemetry {key}")
        row[key] = parsed
    return row


def median(values: list[float]) -> float:
    return float(statistics.median(values))


def numeric_range(rows: list[dict[str, Any]], key: str) -> float:
    values = [float(row[key]) for row in rows]
    return max(values) - min(values)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, required=True)
    parser.add_argument("--path1-workers", type=int, choices=[6], default=6)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV008 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV008 preregistration/source identity mismatch")
    if not torch.cuda.is_available():
        raise SystemExit("PCV008 CUDA unavailable")
    forbidden = active_forbidden_processes()
    if forbidden:
        raise SystemExit(f"PCV008 forbidden process(es): {forbidden}")
    path1_before = path1_identity(args.path1_pid, args.path1_workers)
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
        raise SystemExit("PCV008 source iteration/hands mismatch")
    transitions = deterministic_transitions(checkpoint, "cuda", TRANSITION_SEED, 4096)

    blocks: list[dict[str, Any]] = []
    all_stats: list[dict[str, Any]] = []
    for block_index, order_name in enumerate(ORDERS):
        modes = ("mse", "smooth_l1") if order_name == "MSE_FIRST" else ("smooth_l1", "mse")
        before = telemetry()
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
                    raise RuntimeError("PCV008 timed update violated forced shape")
                values[mode].append(elapsed_ms)
                all_stats.append(stats)
        after = telemetry()
        blocks.append({
            "block_index": block_index,
            "order": order_name,
            "mode_sequence": list(modes),
            "telemetry_before": before,
            "raw_milliseconds": values,
            "median_milliseconds": {mode: median(values[mode]) for mode in values},
            "telemetry_after": after,
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
    all_telemetry = [block[moment] for block in blocks for moment in ("telemetry_before", "telemetry_after")]
    telemetry_ranges = {
        key: numeric_range(all_telemetry, key)
        for key in TELEMETRY_KEYS[2:]
    }
    order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in order_effect.values())
    device_excursion = (
        telemetry_ranges["temperature_gpu_c"] >= 5.0
        or telemetry_ranges["clocks_sm_mhz"] >= 100.0
        or telemetry_ranges["power_draw_w"] >= 30.0
    )
    if order_associated and device_excursion:
        attribution = "ORDER_ASSOCIATION_AND_DEVICE_STATE_EXCURSION_OBSERVED"
    elif order_associated:
        attribution = "ORDER_ASSOCIATION_OBSERVED"
    elif device_excursion:
        attribution = "DEVICE_STATE_EXCURSION_OBSERVED"
    else:
        attribution = "TIMING_JITTER_UNRESOLVED_WITHIN_FROZEN_SENSITIVITY"

    timing_finite = all(
        math.isfinite(value) and value > 0
        for block in blocks for mode in ("mse", "smooth_l1")
        for value in block["raw_milliseconds"][mode]
    )
    telemetry_complete = len(all_telemetry) == 16 and all(
        all(key in row for key in ("sampled_at",) + TELEMETRY_KEYS) for row in all_telemetry
    )
    path1_after = path1_identity(args.path1_pid, args.path1_workers)
    gates = {
        "source_identity_pass": True,
        "exact_dimensions_and_order_pass": len(blocks) == 8 and tuple(block["order"] for block in blocks) == ORDERS
        and all(len(block["raw_milliseconds"][mode]) == 12 for block in blocks for mode in ("mse", "smooth_l1")),
        "all_updates_forced_shape_pass": all(forced_shape(stats) for stats in all_stats),
        "all_timing_finite_positive_pass": timing_finite,
        "all_telemetry_snapshots_complete_pass": telemetry_complete,
        "path1_unchanged_pass": path1_before["changed"] is False and path1_after["changed"] is False,
        "trainer_started_pass": True,
        "checkpoint_written_pass": True,
        "official_hands_zero_pass": True,
    }
    passed = all(gates.values())
    result = {
        "schema_version": "v5.pcv008.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if passed else "FAIL_CLOSED",
        "classification": "PCV008_PASS_MEASUREMENT_COMPLETE" if passed else "PCV008_FAIL_CLOSED",
        "attribution": attribution,
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": SOURCE_ITERATION, "hands": SOURCE_HANDS},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED, "update_seed": UPDATE_SEED,
            "timer": "torch.cuda.Event_with_synchronize", "blocks": 8,
            "warmup_updates_per_mode_per_block": 2, "timed_updates_per_mode_per_block": 12,
            "order_sequence": list(ORDERS), "transition_sha256": transition_sha256(transitions),
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
            "order_associated_threshold_log": math.log(1.01),
            "order_associated": order_associated,
            "device_excursion": device_excursion,
        },
        "gates": gates,
        "path1_before": path1_before,
        "path1_after": path1_after,
        "forbidden_processes": forbidden,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "behavior_method_or_strength_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW020_ONLY",
        "dependency_sha256": hashlib.sha256(Path(__file__).with_name("v5_hybrid_h18_perf_cal.py").read_bytes()).hexdigest(),
        "tool_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": result["overall"], "classification": result["classification"], "attribution": attribution, "summaries": result["summaries"]}, indent=2, sort_keys=True))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
