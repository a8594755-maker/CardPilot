#!/usr/bin/env python3
"""PCV014 adjacent within-cycle matched-pair CUDA timing (reporting only)."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import torch

from v5_hybrid_h17_perf_cal import active_forbidden_processes, deterministic_transitions, sha256, transition_sha256
from v5_hybrid_h18_perf_cal import forced_shape, gpu_event_update
from v5_pcv008_run import TELEMETRY_KEYS, median, numeric_range, telemetry
from v5_pcv009_run import snapshot as resource_snapshot


PREREG_SHA = "8284a18e891409cc8adb9eea92eec9c6e78fc08c5285ec3b645d43865359e4c0"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
SOURCE_ITERATION = 35051
SOURCE_HANDS = 576021901
TRANSITION_SEED = 2026071990
UPDATE_SEED = 2026971990
CONDITIONING_SEED_BASE = 2027971990
BOOTSTRAP_SEED = 2028971990
CYCLES = 8
WARMUP_PAIRS_PER_CYCLE = 2
TIMED_PAIRS_PER_CYCLE = 12
BOOTSTRAP_RESAMPLES = 10_000
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
BLOCK_GATE_MIN_SECONDS = 20.0
BLOCK_GATE_MAX_SECONDS = 60.0


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


def run_cycle_gate(checkpoint: dict[str, Any], transitions: dict[str, Any], cycle_index: int) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    start = time.monotonic()
    next_sample = start
    pair_index = 0
    telemetry_rows: list[dict[str, Any]] = []
    stats_rows: list[dict[str, Any]] = []
    envelope_pass = False
    terminal_window: dict[str, Any] = {"samples": 0}
    while True:
        for mode in ("mse", "smooth_l1"):
            _, stats = gpu_event_update(
                checkpoint, transitions, mode,
                CONDITIONING_SEED_BASE + 1_000_000 + cycle_index * 10_000 + pair_index,
                1024, 4, 1e-12,
            )
            if not forced_shape(stats):
                raise RuntimeError("PCV014 cycle-local conditioning update violated forced shape")
            stats_rows.append(stats)
        pair_index += 1
        now = time.monotonic()
        elapsed = now - start
        if now >= next_sample:
            row = telemetry()
            row["elapsed_seconds"] = elapsed
            telemetry_rows.append(row)
            next_sample = now + TELEMETRY_INTERVAL_SECONDS
            envelope_pass, terminal_window = steady_window(telemetry_rows)
            if elapsed >= BLOCK_GATE_MIN_SECONDS and envelope_pass:
                break
            if elapsed >= BLOCK_GATE_MAX_SECONDS:
                break
    return ({
        "cycle_index": cycle_index,
        "minimum_seconds": BLOCK_GATE_MIN_SECONDS,
        "maximum_seconds": BLOCK_GATE_MAX_SECONDS,
        "telemetry_interval_seconds": TELEMETRY_INTERVAL_SECONDS,
        "steady_samples": STEADY_SAMPLES,
        "steady_limits": STEADY_LIMITS,
        "elapsed_seconds": time.monotonic() - start,
        "full_ppo_mode_pairs": pair_index,
        "telemetry": telemetry_rows,
        "terminal_window": terminal_window,
        "envelope_pass": envelope_pass,
    }, stats_rows)


def cycle_pair_orders(cycle_index: int) -> list[str]:
    first = ("MSE_FIRST", "SMOOTH_L1_FIRST") if cycle_index % 2 == 0 else ("SMOOTH_L1_FIRST", "MSE_FIRST")
    return list(first * 6)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = int(math.floor(position))
    upper = int(math.ceil(position))
    if lower == upper:
        return float(ordered[lower])
    weight = position - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def cluster_bootstrap(cycle_log_ratios: list[list[float]]) -> dict[str, Any]:
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = [cycle_log_ratios[rng.randrange(len(cycle_log_ratios))] for _ in cycle_log_ratios]
        flattened = [value for cycle in sampled for value in cycle]
        estimates.append(math.exp(sum(flattened) / len(flattened)))
    return {
        "unit": "EIGHT_CYCLE_CLUSTERS",
        "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED,
        "confidence": 0.95,
        "lower": percentile(estimates, 0.025),
        "upper": percentile(estimates, 0.975),
        "descriptive_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--path1-pid", type=int, choices=[23720], required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV014 result")
    if sha256(args.preregistration) != PREREG_SHA or sha256(args.source) != SOURCE_SHA:
        raise SystemExit("PCV014 preregistration/source identity mismatch")
    if not torch.cuda.is_available():
        raise SystemExit("PCV014 CUDA unavailable")
    forbidden = active_forbidden_processes()
    if forbidden:
        raise SystemExit(f"PCV014 forbidden process(es): {forbidden}")
    checkpoint = torch.load(args.source, map_location="cpu", weights_only=False)
    if int(checkpoint.get("iteration", -1)) != SOURCE_ITERATION or int(checkpoint.get("total_hands", -1)) != SOURCE_HANDS:
        raise SystemExit("PCV014 source iteration/hands mismatch")
    transitions = deterministic_transitions(checkpoint, "cuda", TRANSITION_SEED, 4096)

    resource_rows: list[dict[str, Any]] = []
    all_stats: list[dict[str, Any]] = []
    conditioning_rows: list[dict[str, Any]] = []
    conditioning_before = resource_snapshot(args.path1_pid, 0)
    resource_rows.append(conditioning_before)
    if not resource_pass(conditioning_before):
        raise RuntimeError("PCV014 phase-aware resource gate failed before conditioning")

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
                raise RuntimeError("PCV014 conditioning update violated forced shape")
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
        "schema_version": "v5.pcv014.result.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": PREREG_SHA,
        "source": {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": SOURCE_ITERATION, "hands": SOURCE_HANDS},
        "workload": {
            "rows": 4096, "mini_batch_size": 1024, "ppo_epochs": 4, "target_kl": 1e-12,
            "old_log_prob_offset": 10.0, "transition_seed": TRANSITION_SEED, "update_seed": UPDATE_SEED,
            "conditioning_seed_base": CONDITIONING_SEED_BASE,
            "timer": "torch.cuda.Event_with_synchronize", "cycles": CYCLES,
            "warmup_pairs_per_cycle": WARMUP_PAIRS_PER_CYCLE, "timed_pairs_per_cycle": TIMED_PAIRS_PER_CYCLE,
            "total_timed_updates_per_mode": CYCLES * TIMED_PAIRS_PER_CYCLE,
            "pair_order_formula": "EVEN_MS_SM_REPEAT6_ODD_SM_MS_REPEAT6",
            "transition_sha256": transition_sha256(transitions),
        },
        "conditioning": conditioning,
        "forbidden_processes": forbidden,
        "path1_mutation": False,
        "gpu_clock_override": False,
        "prior_measurement_data_read_or_reused": False,
        "trainer_started": False,
        "checkpoint_written": False,
        "official_hands": 0,
        "causal_method_behavior_or_strength_inference": "FORBIDDEN",
        "next_authority": "ROUTE_REVIEW026_ONLY",
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
            "classification": "PCV014_FAIL_CLOSED_INITIAL_ENVELOPE_NO_MEASUREMENT",
            "attribution": "NO_MEASUREMENT_CONDITIONING_PREREQUISITE_FAILED",
            "cycles": [],
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

    cycles: list[dict[str, Any]] = []
    cycle_local_gates: list[dict[str, Any]] = []
    for cycle_index in range(CYCLES):
        gate_before = resource_snapshot(args.path1_pid, 2 + cycle_index * 3)
        if not resource_pass(gate_before):
            result = {
                **base, "overall": "FAIL_CLOSED",
                "classification": "PCV014_FAIL_CLOSED_RESOURCE_IDENTITY_NO_LATER_CYCLES",
                "attribution": "NO_COMPLETE_MEASUREMENT_RESOURCE_PREREQUISITE_FAILED",
                "failed_stage": "BEFORE_CYCLE_LOCAL_GATE", "failed_cycle_index": cycle_index,
                "failed_resource_snapshot": gate_before, "cycle_local_gates": cycle_local_gates,
                "cycles": cycles, "summaries": {"completed_cycles_before_abort": len(cycles)},
                "gates": {"source_identity_pass": True, "new_seed_and_output_identity_pass": True,
                          "initial_conditioning_envelope_pass": True, "resource_identity_pass": False,
                          "no_later_cycles_executed_pass": True, "path1_mutation_absent_pass": True,
                          "gpu_clock_override_false_pass": True, "trainer_started_false_pass": True,
                          "checkpoint_written_false_pass": True, "official_hands_zero_pass": True},
            }
            write_result(args.out, result)
            return 2
        resource_rows.append(gate_before)
        cycle_gate, gate_stats = run_cycle_gate(checkpoint, transitions, cycle_index)
        all_stats.extend(gate_stats)
        gate_after = resource_snapshot(args.path1_pid, 3 + cycle_index * 3)
        resource_rows.append(gate_after)
        cycle_gate["resource_before"] = gate_before
        cycle_gate["resource_after"] = gate_after
        cycle_local_gates.append(cycle_gate)
        if not cycle_gate["envelope_pass"] or not resource_pass(gate_after):
            result = {
                **base,
                "overall": "FAIL_CLOSED",
                "classification": "PCV014_FAIL_CLOSED_CYCLE_LOCAL_ENVELOPE_NO_LATER_CYCLES",
                "attribution": "NO_COMPLETE_MEASUREMENT_CYCLE_LOCAL_PREREQUISITE_FAILED",
                "cycle_local_gates": cycle_local_gates,
                "cycles": cycles,
                "summaries": {"completed_cycles_before_abort": len(cycles)},
                "gates": {
                    "source_identity_pass": True,
                    "new_seed_and_output_identity_pass": True,
                    "initial_conditioning_envelope_pass": True,
                    "all_eight_cycle_local_envelopes_pass": False,
                    "failed_cycle_index": cycle_index,
                    "no_later_cycles_executed_pass": True,
                    "path1_mutation_absent_pass": True,
                    "gpu_clock_override_false_pass": True,
                    "trainer_started_false_pass": True,
                    "checkpoint_written_false_pass": True,
                    "official_hands_zero_pass": True,
                },
            }
            write_result(args.out, result)
            print(json.dumps({"overall": result["overall"], "classification": result["classification"], "failed_cycle_index": cycle_index, "cycle_gate": cycle_gate}, indent=2, sort_keys=True))
            return 2
        phase_before = gate_after
        device_before = telemetry()
        pair_orders = cycle_pair_orders(cycle_index)
        for warmup_pair_index, order_name in enumerate(pair_orders[:WARMUP_PAIRS_PER_CYCLE]):
            modes = ("mse", "smooth_l1") if order_name == "MSE_FIRST" else ("smooth_l1", "mse")
            for mode in modes:
                _, stats = gpu_event_update(
                    checkpoint, transitions, mode,
                    UPDATE_SEED + 100000 + cycle_index * 100 + warmup_pair_index,
                    1024, 4, 1e-12,
                )
                if not forced_shape(stats):
                    raise RuntimeError("PCV014 warmup update violated forced shape")
                all_stats.append(stats)
        values: dict[str, list[float]] = {"mse": [], "smooth_l1": []}
        timed_pairs: list[dict[str, Any]] = []
        for timed_pair_index, order_name in enumerate(pair_orders):
            modes = ("mse", "smooth_l1") if order_name == "MSE_FIRST" else ("smooth_l1", "mse")
            pair_values: dict[str, float] = {}
            pair_seed = UPDATE_SEED + 200000 + cycle_index * 100 + timed_pair_index
            for mode in modes:
                elapsed_ms, stats = gpu_event_update(
                    checkpoint, transitions, mode,
                    pair_seed,
                    1024, 4, 1e-12,
                )
                if not forced_shape(stats):
                    raise RuntimeError("PCV014 timed update violated forced shape")
                values[mode].append(elapsed_ms)
                pair_values[mode] = elapsed_ms
                all_stats.append(stats)
            timed_pairs.append({
                "pair_index": timed_pair_index, "order": order_name,
                "mode_sequence": list(modes), "common_update_seed": pair_seed,
                "milliseconds": pair_values,
                "log_mse_over_smooth_l1": math.log(pair_values["mse"] / pair_values["smooth_l1"]),
            })
        device_after = telemetry()
        phase_after = resource_snapshot(args.path1_pid, 4 + cycle_index * 3)
        resource_rows.append(phase_after)
        cycles.append({
            "cycle_index": cycle_index, "pair_orders": pair_orders,
            "resource_before": phase_before, "device_telemetry_before": device_before,
            "timed_pairs": timed_pairs, "raw_milliseconds": values,
            "median_milliseconds": {mode: median(values[mode]) for mode in values},
            "matched_geometric_mean_ratio": math.exp(sum(pair["log_mse_over_smooth_l1"] for pair in timed_pairs) / len(timed_pairs)),
            "device_telemetry_after": device_after, "resource_after": phase_after,
        })
        if not resource_pass(phase_after):
            result = {
                **base, "overall": "FAIL_CLOSED",
                "classification": "PCV014_FAIL_CLOSED_RESOURCE_IDENTITY_NO_LATER_CYCLES",
                "attribution": "NO_COMPLETE_MEASUREMENT_RESOURCE_PREREQUISITE_FAILED",
                "failed_stage": "AFTER_TIMED_CYCLE", "failed_cycle_index": cycle_index,
                "failed_resource_snapshot": phase_after, "cycle_local_gates": cycle_local_gates,
                "cycles": cycles, "summaries": {"completed_cycles_before_abort": len(cycles)},
                "gates": {"source_identity_pass": True, "new_seed_and_output_identity_pass": True,
                          "initial_conditioning_envelope_pass": True, "resource_identity_pass": False,
                          "no_later_cycles_executed_pass": True, "path1_mutation_absent_pass": True,
                          "gpu_clock_override_false_pass": True, "trainer_started_false_pass": True,
                          "checkpoint_written_false_pass": True, "official_hands_zero_pass": True},
            }
            write_result(args.out, result)
            return 2

    cycle_medians = {mode: [float(cycle["median_milliseconds"][mode]) for cycle in cycles] for mode in ("mse", "smooth_l1")}
    all_pairs = [pair for cycle in cycles for pair in cycle["timed_pairs"]]
    all_values = {mode: [float(pair["milliseconds"][mode]) for pair in all_pairs] for mode in ("mse", "smooth_l1")}
    first = {
        "mse": [float(pair["milliseconds"]["mse"]) for pair in all_pairs if pair["order"] == "MSE_FIRST"],
        "smooth_l1": [float(pair["milliseconds"]["smooth_l1"]) for pair in all_pairs if pair["order"] == "SMOOTH_L1_FIRST"],
    }
    second = {
        "mse": [float(pair["milliseconds"]["mse"]) for pair in all_pairs if pair["order"] == "SMOOTH_L1_FIRST"],
        "smooth_l1": [float(pair["milliseconds"]["smooth_l1"]) for pair in all_pairs if pair["order"] == "MSE_FIRST"],
    }
    position_effect = {mode: median(second[mode]) / median(first[mode]) for mode in first}
    log_by_order = {
        order: [float(pair["log_mse_over_smooth_l1"]) for pair in all_pairs if pair["order"] == order]
        for order in ("MSE_FIRST", "SMOOTH_L1_FIRST")
    }
    matched_order_effect = math.exp(median(log_by_order["SMOOTH_L1_FIRST"]) - median(log_by_order["MSE_FIRST"]))
    all_logs = [float(pair["log_mse_over_smooth_l1"]) for pair in all_pairs]
    matched_ratio = math.exp(sum(all_logs) / len(all_logs))
    bootstrap = cluster_bootstrap([[float(pair["log_mse_over_smooth_l1"]) for pair in cycle["timed_pairs"]] for cycle in cycles])
    stability = min(cycle_medians["mse"]) / max(cycle_medians["mse"])
    all_telemetry = [cycle[moment] for cycle in cycles for moment in ("device_telemetry_before", "device_telemetry_after")]
    telemetry_ranges = {key: numeric_range(all_telemetry, key) for key in TELEMETRY_KEYS[2:]}
    order_effects = {**{f"{mode}_position_second_over_first": value for mode, value in position_effect.items()}, "matched_ratio_smooth_first_over_mse_first": matched_order_effect}
    order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in order_effects.values())
    device_excursion = telemetry_ranges["temperature_gpu_c"] >= 5.0 or telemetry_ranges["clocks_sm_mhz"] >= 100.0 or telemetry_ranges["power_draw_w"] >= 30.0
    throughput_pass = matched_ratio >= 0.85
    if not throughput_pass:
        attribution = "MATCHED_PAIR_THROUGHPUT_GATE_FAIL"
    elif stability < 0.95:
        attribution = "MATCHED_PAIR_STABILITY_NOT_RECOVERED"
    elif order_associated:
        attribution = "MATCHED_PAIR_ORDER_ASSOCIATION_PERSISTS"
    elif device_excursion:
        attribution = "MATCHED_PAIR_ASSOCIATION_SUPPORTED_DEVICE_EXCURSION_OBSERVED"
    else:
        attribution = "MATCHED_PAIR_ASSOCIATION_SUPPORTED"

    timing_finite = all(math.isfinite(value) and value > 0 for mode in all_values for value in all_values[mode])
    telemetry_complete = len(all_telemetry) == 16 and all(all(key in row for key in ("sampled_at",) + TELEMETRY_KEYS) for row in all_telemetry)
    cycle_gates_complete = len(cycle_local_gates) == CYCLES and all(gate["envelope_pass"] for gate in cycle_local_gates)
    resource_complete = len(resource_rows) == 26 and all(resource_pass(row) for row in resource_rows)
    exact_orders = all(cycle["pair_orders"] == cycle_pair_orders(index) for index, cycle in enumerate(cycles))
    gates = {
        "source_identity_pass": True,
        "new_seed_and_output_identity_pass": True,
        "conditioning_envelope_pass_before_measurement": True,
        "conditioning_resource_contract_pass": True,
        "all_eight_cycle_local_envelopes_pass": cycle_gates_complete,
        "exact_adjacent_pair_sequence_and_counts_pass": len(cycles) == CYCLES and exact_orders and sum(pair["order"] == "MSE_FIRST" for pair in all_pairs) == 48 and sum(pair["order"] == "SMOOTH_L1_FIRST" for pair in all_pairs) == 48,
        "exact_measurement_shape_pass": len(cycles) == CYCLES and len(all_pairs) == 96 and all(len(cycle["timed_pairs"]) == TIMED_PAIRS_PER_CYCLE and all(len(cycle["raw_milliseconds"][mode]) == TIMED_PAIRS_PER_CYCLE for mode in ("mse", "smooth_l1")) for cycle in cycles),
        "all_updates_forced_shape_pass": all(forced_shape(stats) for stats in all_stats),
        "all_timing_finite_positive_pass": timing_finite,
        "all_device_telemetry_complete_pass": telemetry_complete,
        "all_twenty_six_phase_aware_resource_snapshots_pass": resource_complete,
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
        "classification": "PCV014_PASS_MEASUREMENT_COMPLETE" if passed else "PCV014_FAIL_CLOSED",
        "attribution": attribution,
        "cycle_local_gates": cycle_local_gates,
        "cycles": cycles,
        "summaries": {
            "cycle_median_milliseconds": cycle_medians,
            "aggregate_mode_median_milliseconds": {mode: median(all_values[mode]) for mode in all_values},
            "mse_cycle_median_stability_min_over_max": stability,
            "mse_stability_target": 0.95,
            "position_stratified_first_median_milliseconds": {mode: median(first[mode]) for mode in first},
            "position_stratified_second_median_milliseconds": {mode: median(second[mode]) for mode in second},
            "order_effect_ratios": order_effects,
            "matched_mse_over_smooth_l1_geometric_mean_ratio": matched_ratio,
            "matched_ratio_bootstrap95": bootstrap,
            "throughput_ratio_min": 0.85,
            "throughput_ratio_pass": throughput_pass,
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
