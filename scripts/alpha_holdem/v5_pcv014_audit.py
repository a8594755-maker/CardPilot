#!/usr/bin/env python3
"""Independent fail-closed audit for immutable PCV014 result."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREREG_SHA = "8284a18e891409cc8adb9eea92eec9c6e78fc08c5285ec3b645d43865359e4c0"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
TRANSITION_SEED = 2026071990
UPDATE_SEED = 2026971990
CONDITIONING_SEED_BASE = 2027971990
BOOTSTRAP_SEED = 2028971990
BOOTSTRAP_RESAMPLES = 10_000
CYCLES = 8
TIMED_PAIRS = 12
NUMERIC_TELEMETRY = (
    "temperature_gpu_c", "clocks_sm_mhz", "clocks_mem_mhz", "power_draw_w",
    "utilization_gpu_pct", "memory_used_mib",
)
STEADY_LIMITS = {"temperature_gpu_c": 3.0, "clocks_sm_mhz": 100.0, "clocks_mem_mhz": 100.0, "power_draw_w": 30.0}
COMMAND_SHA = "efaf227352c6620b4f12dd5f06ac67d98d834feb11384b167170618dc1cf9e99"
CREATE_TIME = 1784302339.7041352


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


def ranges(rows: list[dict[str, Any]], keys: tuple[str, ...] | list[str]) -> dict[str, float]:
    return {key: max(float(row[key]) for row in rows) - min(float(row[key]) for row in rows) for key in keys}


def resource_pass(row: dict[str, Any]) -> bool:
    counts = row["role_counts"]
    return (
        row["coordinator_pid"] == 23720
        and math.isclose(row["coordinator_create_time"], CREATE_TIME, rel_tol=0.0, abs_tol=1e-6)
        and row["coordinator_command_sha256"] == COMMAND_SHA
        and row["coordinator_priority"] == 16384
        and counts["unknown"] == 0 and 1 <= counts["active_work"] <= 6
        and row["node_child_priorities_below_normal"] is True
        and row["descendant_gpu_pid_intersection"] == []
    )


def envelope(rows: list[dict[str, Any]]) -> tuple[bool, dict[str, float]]:
    terminal = rows[-4:] if len(rows) >= 4 else []
    terminal_ranges = ranges(terminal, list(STEADY_LIMITS)) if terminal else {}
    passed = bool(terminal) and all(terminal_ranges[key] <= limit for key, limit in STEADY_LIMITS.items()) and len({row["pstate"] for row in terminal}) == 1 and len({row["uuid"] for row in terminal}) == 1
    return passed, terminal_ranges


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


def bootstrap(cycle_logs: list[list[float]]) -> dict[str, Any]:
    rng = random.Random(BOOTSTRAP_SEED)
    estimates: list[float] = []
    for _ in range(BOOTSTRAP_RESAMPLES):
        sampled = [cycle_logs[rng.randrange(len(cycle_logs))] for _ in cycle_logs]
        flattened = [value for cycle in sampled for value in cycle]
        estimates.append(math.exp(sum(flattened) / len(flattened)))
    return {
        "unit": "EIGHT_CYCLE_CLUSTERS", "resamples": BOOTSTRAP_RESAMPLES,
        "seed": BOOTSTRAP_SEED, "confidence": 0.95,
        "lower": percentile(estimates, 0.025), "upper": percentile(estimates, 0.975),
        "descriptive_only": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--preregistration", type=Path, required=True)
    parser.add_argument("--runner", type=Path, required=True)
    parser.add_argument("--pcv008-helper", type=Path, required=True)
    parser.add_argument("--pcv009-helper", type=Path, required=True)
    parser.add_argument("--h18-helper", type=Path, required=True)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    if args.out.exists():
        raise SystemExit("refusing to overwrite immutable PCV014 audit")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    workload = result["workload"]
    conditioning = result["conditioning"]
    conditioning_pass, conditioning_ranges = envelope(conditioning["telemetry"])
    expected_dependencies = {
        "pcv008_measurement_helpers": sha256(args.pcv008_helper),
        "pcv009_resource_snapshot": sha256(args.pcv009_helper),
        "h18_full_update": sha256(args.h18_helper),
    }
    checks: dict[str, bool] = {
        "preregistration_binding": sha256(args.preregistration) == PREREG_SHA and result["preregistration_sha256"] == PREREG_SHA,
        "source_identity": sha256(args.source) == SOURCE_SHA and result["source"] == {"path": str(args.source.resolve()), "sha256": SOURCE_SHA, "iteration": 35051, "hands": 576021901},
        "runner_binding": sha256(args.runner) == result["tool_sha256"],
        "dependency_bindings": result["dependency_sha256"] == expected_dependencies,
        "new_seed_and_workload_identity": all((workload["transition_seed"] == TRANSITION_SEED, workload["update_seed"] == UPDATE_SEED, workload["conditioning_seed_base"] == CONDITIONING_SEED_BASE, workload["rows"] == 4096, workload["mini_batch_size"] == 1024, workload["ppo_epochs"] == 4, close(workload["target_kl"], 1e-12), close(workload["old_log_prob_offset"], 10.0), workload["timer"] == "torch.cuda.Event_with_synchronize", workload["cycles"] == CYCLES, workload["warmup_pairs_per_cycle"] == 2, workload["timed_pairs_per_cycle"] == TIMED_PAIRS, workload["total_timed_updates_per_mode"] == 96, workload["pair_order_formula"] == "EVEN_MS_SM_REPEAT6_ODD_SM_MS_REPEAT6")),
        "conditioning_contract_identity": conditioning["minimum_seconds"] == 60.0 and conditioning["maximum_seconds"] == 180.0 and conditioning["telemetry_interval_seconds"] == 5.0 and conditioning["steady_samples"] == 4 and conditioning["steady_limits"] == STEADY_LIMITS,
        "conditioning_duration_bounded": conditioning["elapsed_seconds"] >= 60.0 and conditioning["elapsed_seconds"] <= 190.0,
        "conditioning_updates_present": conditioning["full_ppo_mode_pairs"] > 0,
        "conditioning_telemetry_complete": len(conditioning["telemetry"]) >= 4 and all(row.get("uuid") and row.get("pstate") and all(math.isfinite(float(row[key])) for key in NUMERIC_TELEMETRY) for row in conditioning["telemetry"]),
        "conditioning_terminal_window_recomputed": conditioning["terminal_window"].get("samples") == 4 and all(close(conditioning_ranges[key], conditioning["terminal_window"]["ranges"][key]) for key in conditioning_ranges),
        "conditioning_envelope_recomputed": conditioning["envelope_pass"] is conditioning_pass,
        "conditioning_resource_contract": resource_pass(conditioning["resource_before"]) and resource_pass(conditioning["resource_after"]),
        "no_clock_override_or_path1_mutation": result["gpu_clock_override"] is False and result["path1_mutation"] is False,
        "prior_measurement_not_used": result["prior_measurement_data_read_or_reused"] is False,
        "trainer_checkpoint_official_absent": result["trainer_started"] is False and result["checkpoint_written"] is False and result["official_hands"] == 0,
        "inference_and_authority_frozen": result["causal_method_behavior_or_strength_inference"] == "FORBIDDEN" and result["next_authority"] == "ROUTE_REVIEW026_ONLY",
    }
    recomputed: dict[str, Any] = {"conditioning_envelope_pass": conditioning_pass, "conditioning_terminal_ranges": conditioning_ranges}

    if result["classification"] == "PCV014_FAIL_CLOSED_INITIAL_ENVELOPE_NO_MEASUREMENT":
        checks.update({
            "initial_fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and (not conditioning_pass or not resource_pass(conditioning["resource_after"])),
            "measurement_absent_on_conditioning_fail": result["cycles"] == [] and result["summaries"] == {},
            "failure_attribution_exact": result["attribution"] == "NO_MEASUREMENT_CONDITIONING_PREREQUISITE_FAILED",
            "failure_gates_consistent": result["gates"]["measurement_not_started_pass"] is True,
        })
    elif result["classification"] == "PCV014_FAIL_CLOSED_CYCLE_LOCAL_ENVELOPE_NO_LATER_CYCLES":
        cycle_gates = result["cycle_local_gates"]
        cycles = result["cycles"]
        failed_index = int(result["gates"]["failed_cycle_index"])
        last_gate = cycle_gates[-1]
        last_pass, last_ranges = envelope(last_gate["telemetry"])
        checks.update({
            "local_fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and result["attribution"] == "NO_COMPLETE_MEASUREMENT_CYCLE_LOCAL_PREREQUISITE_FAILED",
            "failed_cycle_identity_exact": failed_index == len(cycles) and len(cycle_gates) == failed_index + 1,
            "failed_gate_contract_exact": last_gate["minimum_seconds"] == 20.0 and last_gate["maximum_seconds"] == 60.0 and last_gate["telemetry_interval_seconds"] == 5.0 and last_gate["steady_samples"] == 4 and last_gate["steady_limits"] == STEADY_LIMITS,
            "failed_gate_recomputed": last_gate["envelope_pass"] is last_pass and (not last_pass or not resource_pass(last_gate["resource_after"])),
            "prior_gates_pass": all(gate["envelope_pass"] and resource_pass(gate["resource_before"]) and resource_pass(gate["resource_after"]) for gate in cycle_gates[:-1]),
            "no_later_cycles_executed": result["gates"]["no_later_cycles_executed_pass"] is True and result["summaries"]["completed_cycles_before_abort"] == len(cycles),
        })
        recomputed.update({"failed_cycle_index": failed_index, "failed_gate_envelope_pass": last_pass, "failed_gate_terminal_ranges": last_ranges})
    elif result["classification"] == "PCV014_FAIL_CLOSED_RESOURCE_IDENTITY_NO_LATER_CYCLES":
        checks.update({
            "resource_fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and result["attribution"] == "NO_COMPLETE_MEASUREMENT_RESOURCE_PREREQUISITE_FAILED",
            "failed_resource_snapshot_recomputed": not resource_pass(result["failed_resource_snapshot"]),
            "failed_cycle_index_bounded": 0 <= int(result["failed_cycle_index"]) < CYCLES,
            "no_later_cycles_executed": result["gates"]["no_later_cycles_executed_pass"] is True and result["summaries"]["completed_cycles_before_abort"] == len(result["cycles"]),
        })
    else:
        cycles = result["cycles"]
        cycle_gates = result["cycle_local_gates"]
        summaries = result["summaries"]
        all_pairs = [pair for cycle in cycles for pair in cycle["timed_pairs"]]
        all_values = {mode: [float(pair["milliseconds"][mode]) for pair in all_pairs] for mode in ("mse", "smooth_l1")}
        cycle_medians = {mode: [median([float(value) for value in cycle["raw_milliseconds"][mode]]) for cycle in cycles] for mode in ("mse", "smooth_l1")}
        first = {
            "mse": [float(pair["milliseconds"]["mse"]) for pair in all_pairs if pair["order"] == "MSE_FIRST"],
            "smooth_l1": [float(pair["milliseconds"]["smooth_l1"]) for pair in all_pairs if pair["order"] == "SMOOTH_L1_FIRST"],
        }
        second = {
            "mse": [float(pair["milliseconds"]["mse"]) for pair in all_pairs if pair["order"] == "SMOOTH_L1_FIRST"],
            "smooth_l1": [float(pair["milliseconds"]["smooth_l1"]) for pair in all_pairs if pair["order"] == "MSE_FIRST"],
        }
        position_effect = {mode: median(second[mode]) / median(first[mode]) for mode in first}
        logs_by_order = {order: [float(pair["log_mse_over_smooth_l1"]) for pair in all_pairs if pair["order"] == order] for order in ("MSE_FIRST", "SMOOTH_L1_FIRST")}
        matched_order_effect = math.exp(median(logs_by_order["SMOOTH_L1_FIRST"]) - median(logs_by_order["MSE_FIRST"]))
        order_effects = {**{f"{mode}_position_second_over_first": value for mode, value in position_effect.items()}, "matched_ratio_smooth_first_over_mse_first": matched_order_effect}
        all_logs = [math.log(float(pair["milliseconds"]["mse"]) / float(pair["milliseconds"]["smooth_l1"])) for pair in all_pairs]
        matched_ratio = math.exp(sum(all_logs) / len(all_logs))
        bootstrap_result = bootstrap([[math.log(float(pair["milliseconds"]["mse"]) / float(pair["milliseconds"]["smooth_l1"])) for pair in cycle["timed_pairs"]] for cycle in cycles])
        stability = min(cycle_medians["mse"]) / max(cycle_medians["mse"])
        telemetry_rows = [cycle[moment] for cycle in cycles for moment in ("device_telemetry_before", "device_telemetry_after")]
        measurement_ranges = ranges(telemetry_rows, list(NUMERIC_TELEMETRY))
        order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in order_effects.values())
        device_excursion = measurement_ranges["temperature_gpu_c"] >= 5.0 or measurement_ranges["clocks_sm_mhz"] >= 100.0 or measurement_ranges["power_draw_w"] >= 30.0
        throughput_pass = matched_ratio >= 0.85
        expected_attribution = "MATCHED_PAIR_THROUGHPUT_GATE_FAIL" if not throughput_pass else ("MATCHED_PAIR_STABILITY_NOT_RECOVERED" if stability < 0.95 else ("MATCHED_PAIR_ORDER_ASSOCIATION_PERSISTS" if order_associated else ("MATCHED_PAIR_ASSOCIATION_SUPPORTED_DEVICE_EXCURSION_OBSERVED" if device_excursion else "MATCHED_PAIR_ASSOCIATION_SUPPORTED")))
        resource_rows = [conditioning["resource_before"], conditioning["resource_after"]] + [row for index in range(CYCLES) for row in (cycle_gates[index]["resource_before"], cycle_gates[index]["resource_after"], cycles[index]["resource_after"])]
        gate_envelopes = [envelope(gate["telemetry"]) for gate in cycle_gates]
        checks.update({
            "pass_classification_exact": result["overall"] == "PASS" and result["classification"] == "PCV014_PASS_MEASUREMENT_COMPLETE" and conditioning_pass,
            "cycle_dimensions": len(cycles) == CYCLES and all(cycle["cycle_index"] == index for index, cycle in enumerate(cycles)),
            "pair_orders_exact": all(cycle["pair_orders"] == cycle_pair_orders(index) for index, cycle in enumerate(cycles)),
            "pair_counts_balanced": len(all_pairs) == 96 and sum(pair["order"] == "MSE_FIRST" for pair in all_pairs) == 48 and sum(pair["order"] == "SMOOTH_L1_FIRST" for pair in all_pairs) == 48,
            "common_pair_seeds_exact": all(pair["common_update_seed"] == UPDATE_SEED + 200000 + cycle_index * 100 + pair_index for cycle_index, cycle in enumerate(cycles) for pair_index, pair in enumerate(cycle["timed_pairs"])),
            "pair_logs_recomputed": all(close(pair["log_mse_over_smooth_l1"], math.log(float(pair["milliseconds"]["mse"]) / float(pair["milliseconds"]["smooth_l1"]))) for pair in all_pairs),
            "timing_finite_positive": all(math.isfinite(value) and value > 0 for mode in all_values for value in all_values[mode]),
            "measurement_telemetry_complete": len(telemetry_rows) == 16 and all(row.get("uuid") and row.get("pstate") and all(math.isfinite(float(row[key])) for key in NUMERIC_TELEMETRY) for row in telemetry_rows),
            "all_cycle_gate_dimensions_and_envelopes": len(cycle_gates) == CYCLES and all(gate["minimum_seconds"] == 20.0 and gate["maximum_seconds"] == 60.0 and gate["telemetry_interval_seconds"] == 5.0 and gate["steady_samples"] == 4 and gate["steady_limits"] == STEADY_LIMITS and gate["envelope_pass"] is gate_envelopes[index][0] for index, gate in enumerate(cycle_gates)),
            "gate_after_is_cycle_before": all(cycles[index]["resource_before"] == cycle_gates[index]["resource_after"] for index in range(CYCLES)),
            "all_twenty_six_resource_snapshots_pass": len(resource_rows) == 26 and all(resource_pass(row) for row in resource_rows),
            "cycle_medians_recomputed": all(close(cycle_medians[mode][index], summaries["cycle_median_milliseconds"][mode][index]) for mode in cycle_medians for index in range(CYCLES)),
            "stability_recomputed": close(stability, summaries["mse_cycle_median_stability_min_over_max"]),
            "order_effects_recomputed": all(close(value, summaries["order_effect_ratios"][name]) for name, value in order_effects.items()),
            "matched_ratio_recomputed": close(matched_ratio, summaries["matched_mse_over_smooth_l1_geometric_mean_ratio"]),
            "cluster_bootstrap_recomputed": all((summaries["matched_ratio_bootstrap95"][key] == value if isinstance(value, (str, int, bool)) else close(summaries["matched_ratio_bootstrap95"][key], value)) for key, value in bootstrap_result.items()),
            "telemetry_ranges_recomputed": all(close(measurement_ranges[key], summaries["telemetry_ranges"][key]) for key in measurement_ranges),
            "registered_metric_gates_recomputed": summaries["throughput_ratio_pass"] is throughput_pass and summaries["order_associated"] is order_associated and close(summaries["mse_stability_target"], 0.95),
            "attribution_rule_recomputed": result["attribution"] == expected_attribution and summaries["device_excursion"] is device_excursion,
            "registered_completion_gates": all(result["gates"].values()),
        })
        recomputed.update({
            "attribution": expected_attribution, "matched_ratio": matched_ratio,
            "bootstrap95": bootstrap_result, "mse_cycle_stability": stability,
            "order_effect_ratios": order_effects, "measurement_telemetry_ranges": measurement_ranges,
        })

    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv014.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.result), "runner_sha256": sha256(args.runner),
        "checks": checks, "checks_passed": len(checks) - len(failed), "checks_total": len(checks),
        "failed": failed, "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": result["classification"] if not failed else "PCV014_AUDIT_FAIL_CLOSED",
        "recomputed": recomputed, "official_hands": 0,
        "behavior_launch_authority": "NONE_ROUTE_REVIEW026_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": audit["overall"], "passed": audit["checks_passed"], "total": audit["checks_total"], "failed": failed, "classification": audit["classification"], "recomputed": recomputed}, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
