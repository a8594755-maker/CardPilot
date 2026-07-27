#!/usr/bin/env python3
"""Independent fail-closed audit for immutable PCV013 result."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PREREG_SHA = "ca79c9219e605369ac188e4ece039bea7019be2c0e2dce1a6d32936d4b84fb19"
SOURCE_SHA = "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
ORDERS = (
    "MSE_FIRST", "SMOOTH_L1_FIRST", "SMOOTH_L1_FIRST", "MSE_FIRST",
    "SMOOTH_L1_FIRST", "MSE_FIRST", "MSE_FIRST", "SMOOTH_L1_FIRST",
)
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
        raise SystemExit("refusing to overwrite immutable PCV013 audit")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    workload = result["workload"]
    conditioning = result["conditioning"]
    conditioning_rows = conditioning["telemetry"]
    terminal_rows = conditioning_rows[-4:] if len(conditioning_rows) >= 4 else []
    terminal_ranges = ranges(terminal_rows, list(STEADY_LIMITS)) if terminal_rows else {}
    envelope_recomputed = bool(terminal_rows) and all(terminal_ranges[key] <= limit for key, limit in STEADY_LIMITS.items()) and len({row["pstate"] for row in terminal_rows}) == 1 and len({row["uuid"] for row in terminal_rows}) == 1
    expected_anchor = ({
        "temperature_target_c": max(float(row["temperature_gpu_c"]) for row in terminal_rows) + 2.0,
        "sm_clock_target_mhz": median([float(row["clocks_sm_mhz"]) for row in terminal_rows]),
        "memory_clock_target_mhz": median([float(row["clocks_mem_mhz"]) for row in terminal_rows]),
        "pstate_target": terminal_rows[0]["pstate"],
        "gpu_uuid_target": terminal_rows[0]["uuid"],
        "derivation": "NEW_INITIAL_FINAL_FOUR_ONLY_MAX_TEMP_PLUS_2_AND_MEDIAN_CLOCKS",
    } if envelope_recomputed else {})
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
        "new_seed_and_workload_identity": all((workload["transition_seed"] == 2026071989, workload["update_seed"] == 2026971989, workload["conditioning_seed_base"] == 2027971989, workload["rows"] == 4096, workload["mini_batch_size"] == 1024, workload["ppo_epochs"] == 4, close(workload["target_kl"], 1e-12), close(workload["old_log_prob_offset"], 10.0), workload["timer"] == "torch.cuda.Event_with_synchronize", workload["blocks"] == 8, workload["warmup_updates_per_mode_per_block"] == 2, workload["timed_updates_per_mode_per_block"] == 12, tuple(workload["order_sequence"]) == ORDERS)),
        "conditioning_contract_identity": conditioning["minimum_seconds"] == 60.0 and conditioning["maximum_seconds"] == 180.0 and conditioning["telemetry_interval_seconds"] == 5.0 and conditioning["steady_samples"] == 4 and conditioning["steady_limits"] == STEADY_LIMITS,
        "conditioning_duration_bounded": conditioning["elapsed_seconds"] >= 60.0 and conditioning["elapsed_seconds"] <= 190.0,
        "conditioning_updates_present": conditioning["full_ppo_mode_pairs"] > 0,
        "conditioning_telemetry_complete": len(conditioning_rows) >= 4 and all(row.get("uuid") and row.get("pstate") and all(math.isfinite(float(row[key])) for key in NUMERIC_TELEMETRY) for row in conditioning_rows),
        "conditioning_terminal_window_recomputed": conditioning["terminal_window"].get("samples") == 4 and all(close(terminal_ranges[key], conditioning["terminal_window"]["ranges"][key]) for key in terminal_ranges),
        "conditioning_envelope_recomputed": conditioning["envelope_pass"] is envelope_recomputed,
        "absolute_anchor_recomputed": result["absolute_anchor"] == expected_anchor,
        "conditioning_resource_contract": resource_pass(conditioning["resource_before"]) and resource_pass(conditioning["resource_after"]),
        "no_clock_override_or_path1_mutation": result["gpu_clock_override"] is False and result["path1_mutation"] is False,
        "prior_measurement_not_used": result["prior_measurement_data_read_or_reused"] is False,
        "trainer_checkpoint_official_absent": result["trainer_started"] is False and result["checkpoint_written"] is False and result["official_hands"] == 0,
        "inference_and_authority_frozen": result["causal_method_behavior_or_strength_inference"] == "FORBIDDEN" and result["next_authority"] == "ROUTE_REVIEW025_ONLY",
    }

    recomputed: dict[str, Any] = {"conditioning_envelope_pass": envelope_recomputed, "conditioning_terminal_ranges": terminal_ranges}
    if result["classification"] == "PCV013_FAIL_CLOSED_CONDITIONING_OR_LOCAL_GATE_NO_LATER_BLOCKS" and result["blocks"] == [] and "block_local_gates" not in result:
        checks.update({
            "fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and not envelope_recomputed,
            "measurement_absent_on_conditioning_fail": result["blocks"] == [] and result["summaries"] == {},
            "failure_attribution_exact": result["attribution"] == "NO_MEASUREMENT_CONDITIONING_PREREQUISITE_FAILED",
            "failure_gates_consistent": result["gates"]["conditioning_envelope_pass_before_measurement"] is False and result["gates"]["measurement_not_started_pass"] is True,
        })
    elif result["classification"] == "PCV013_FAIL_CLOSED_CONDITIONING_OR_LOCAL_GATE_NO_LATER_BLOCKS":
        block_gates = result["block_local_gates"]
        blocks = result["blocks"]
        failed_index = int(result["gates"]["failed_block_index"])
        last_gate = block_gates[-1]
        last_rows = last_gate["telemetry"][-4:] if len(last_gate["telemetry"]) >= 4 else []
        last_ranges = ranges(last_rows, list(STEADY_LIMITS)) if last_rows else {}
        last_envelope = bool(last_rows) and all(last_ranges[key] <= limit for key, limit in STEADY_LIMITS.items()) and len({row["pstate"] for row in last_rows}) == 1 and len({row["uuid"] for row in last_rows}) == 1
        checks.update({
            "block_fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and result["attribution"] == "NO_COMPLETE_MEASUREMENT_BLOCK_LOCAL_PREREQUISITE_FAILED",
            "failed_block_identity_exact": failed_index == len(blocks) and len(block_gates) == failed_index + 1,
            "failed_gate_contract_exact": last_gate["minimum_seconds"] == 20.0 and last_gate["maximum_seconds"] == 60.0 and last_gate["telemetry_interval_seconds"] == 5.0 and last_gate["steady_samples"] == 4 and last_gate["steady_limits"] == STEADY_LIMITS,
            "failed_gate_recomputed": last_gate["envelope_pass"] is last_envelope and (not last_envelope or not resource_pass(last_gate["resource_after"])),
            "prior_gates_pass": all(gate["envelope_pass"] and resource_pass(gate["resource_before"]) and resource_pass(gate["resource_after"]) for gate in block_gates[:-1]),
            "no_later_blocks_executed": result["gates"]["no_later_blocks_executed_pass"] is True and result["summaries"]["completed_blocks_before_abort"] == len(blocks),
        })
        recomputed.update({"failed_block_index": failed_index, "failed_gate_envelope_pass": last_envelope, "failed_gate_terminal_ranges": last_ranges})
    elif result["classification"] == "PCV013_FAIL_CLOSED_ABSOLUTE_ADMISSION_NO_LATER_BLOCKS":
        block_gates = result["block_local_gates"]
        absolute_gates = result["absolute_gates"]
        blocks = result["blocks"]
        failed_index = int(result["gates"]["failed_block_index"])
        last_gate = absolute_gates[-1]
        last_rows = last_gate["admission_telemetry"][-4:] if len(last_gate["admission_telemetry"]) >= 4 else []
        last_local_ranges = ranges(last_rows, list(STEADY_LIMITS)) if last_rows else {}
        last_absolute = bool(last_rows) and all(
            abs(float(row["temperature_gpu_c"]) - float(expected_anchor["temperature_target_c"])) <= 1.0
            and abs(float(row["clocks_sm_mhz"]) - float(expected_anchor["sm_clock_target_mhz"])) <= 100.0
            and abs(float(row["clocks_mem_mhz"]) - float(expected_anchor["memory_clock_target_mhz"])) <= 100.0
            and row["pstate"] == expected_anchor["pstate_target"]
            and row["uuid"] == expected_anchor["gpu_uuid_target"]
            for row in last_rows
        ) and all(last_local_ranges[key] <= limit for key, limit in STEADY_LIMITS.items())
        checks.update({
            "absolute_fail_closed_classification_exact": result["overall"] == "FAIL_CLOSED" and result["attribution"] == "NO_COMPLETE_MEASUREMENT_ABSOLUTE_ADMISSION_FAILED",
            "absolute_failed_block_identity_exact": failed_index == len(blocks) and len(block_gates) == failed_index + 1 and len(absolute_gates) == failed_index + 1,
            "absolute_failed_gate_contract_exact": last_gate["minimum_seconds"] == 6.0 and last_gate["maximum_seconds"] == 120.0 and last_gate["telemetry_cadence_seconds"] == 2.0 and last_gate["consecutive_samples"] == 4 and last_gate["anchor"] == expected_anchor,
            "absolute_failed_gate_recomputed": last_gate["envelope_pass"] is last_absolute and (not last_absolute or not resource_pass(last_gate["resource_after"])),
            "absolute_prior_local_and_absolute_gates_pass": all(gate["envelope_pass"] for gate in block_gates) and all(gate["envelope_pass"] for gate in absolute_gates[:-1]),
            "absolute_no_later_blocks_executed": result["gates"]["no_later_blocks_executed_pass"] is True and result["summaries"]["completed_blocks_before_abort"] == len(blocks),
        })
        recomputed.update({"failed_block_index": failed_index, "failed_absolute_envelope_pass": last_absolute, "failed_absolute_terminal_ranges": last_local_ranges})
    else:
        blocks = result["blocks"]
        block_gates = result["block_local_gates"]
        absolute_gates = result["absolute_gates"]
        summaries = result["summaries"]
        block_medians = {mode: [median([float(value) for value in block["raw_milliseconds"][mode]]) for block in blocks] for mode in ("mse", "smooth_l1")}
        first = {
            "mse": [block_medians["mse"][i] for i, order in enumerate(ORDERS) if order == "MSE_FIRST"],
            "smooth_l1": [block_medians["smooth_l1"][i] for i, order in enumerate(ORDERS) if order == "SMOOTH_L1_FIRST"],
        }
        second = {
            "mse": [block_medians["mse"][i] for i, order in enumerate(ORDERS) if order == "SMOOTH_L1_FIRST"],
            "smooth_l1": [block_medians["smooth_l1"][i] for i, order in enumerate(ORDERS) if order == "MSE_FIRST"],
        }
        aggregate = {mode: median(block_medians[mode]) for mode in block_medians}
        effects = {mode: median(second[mode]) / median(first[mode]) for mode in first}
        stability = min(block_medians["mse"]) / max(block_medians["mse"])
        telemetry_rows = [block[moment] for block in blocks for moment in ("device_telemetry_before", "device_telemetry_after")]
        resource_rows = [conditioning["resource_before"], conditioning["resource_after"]] + [row for index in range(8) for row in (block_gates[index]["resource_before"], block_gates[index]["resource_after"], absolute_gates[index]["resource_after"], blocks[index]["resource_after"])]
        block_gate_envelopes = []
        block_gate_ranges = []
        for gate in block_gates:
            gate_rows = gate["telemetry"][-4:] if len(gate["telemetry"]) >= 4 else []
            gate_ranges = ranges(gate_rows, list(STEADY_LIMITS)) if gate_rows else {}
            gate_pass = bool(gate_rows) and all(gate_ranges[key] <= limit for key, limit in STEADY_LIMITS.items()) and len({row["pstate"] for row in gate_rows}) == 1 and len({row["uuid"] for row in gate_rows}) == 1
            block_gate_envelopes.append(gate_pass)
            block_gate_ranges.append(gate_ranges)
        absolute_gate_envelopes = []
        absolute_gate_ranges = []
        for gate in absolute_gates:
            gate_rows = gate["admission_telemetry"][-4:] if len(gate["admission_telemetry"]) >= 4 else []
            gate_ranges = ranges(gate_rows, list(STEADY_LIMITS)) if gate_rows else {}
            gate_pass = bool(gate_rows) and all(
                abs(float(row["temperature_gpu_c"]) - float(expected_anchor["temperature_target_c"])) <= 1.0
                and abs(float(row["clocks_sm_mhz"]) - float(expected_anchor["sm_clock_target_mhz"])) <= 100.0
                and abs(float(row["clocks_mem_mhz"]) - float(expected_anchor["memory_clock_target_mhz"])) <= 100.0
                and row["pstate"] == expected_anchor["pstate_target"]
                and row["uuid"] == expected_anchor["gpu_uuid_target"]
                for row in gate_rows
            ) and all(gate_ranges[key] <= limit for key, limit in STEADY_LIMITS.items())
            absolute_gate_envelopes.append(gate_pass)
            absolute_gate_ranges.append(gate_ranges)
        measurement_ranges = ranges(telemetry_rows, list(NUMERIC_TELEMETRY))
        device_excursion = measurement_ranges["temperature_gpu_c"] >= 5.0 or measurement_ranges["clocks_sm_mhz"] >= 100.0 or measurement_ranges["power_draw_w"] >= 30.0
        order_associated = any(abs(math.log(float(value))) >= math.log(1.01) for value in effects.values())
        expected_attribution = "ABSOLUTE_ALIGNMENT_MEASUREMENT_EXCURSION_PERSISTS" if device_excursion else ("ABSOLUTE_ALIGNMENT_DID_NOT_REMOVE_ORDER_ASSOCIATION" if order_associated else ("ABSOLUTE_ALIGNMENT_ASSOCIATION_SUPPORTED" if stability >= 0.95 else "ABSOLUTE_ALIGNMENT_STABILITY_NOT_RECOVERED"))
        checks.update({
            "pass_classification_exact": result["overall"] == "PASS" and result["classification"] == "PCV013_PASS_MEASUREMENT_COMPLETE" and envelope_recomputed,
            "block_and_order_dimensions": len(blocks) == 8 and tuple(block["order"] for block in blocks) == ORDERS,
            "timing_dimensions": all(len(block["raw_milliseconds"][mode]) == 12 for block in blocks for mode in ("mse", "smooth_l1")),
            "timing_finite_positive": all(math.isfinite(float(value)) and float(value) > 0 for block in blocks for mode in ("mse", "smooth_l1") for value in block["raw_milliseconds"][mode]),
            "measurement_telemetry_complete": len(telemetry_rows) == 16 and all(row.get("uuid") and row.get("pstate") and all(math.isfinite(float(row[key])) for key in NUMERIC_TELEMETRY) for row in telemetry_rows),
            "all_block_gate_dimensions_and_envelopes": len(block_gates) == 8 and all(gate["minimum_seconds"] == 20.0 and gate["maximum_seconds"] == 60.0 and gate["telemetry_interval_seconds"] == 5.0 and gate["steady_samples"] == 4 and gate["steady_limits"] == STEADY_LIMITS and gate["envelope_pass"] is block_gate_envelopes[index] for index, gate in enumerate(block_gates)),
            "all_absolute_gate_dimensions_and_envelopes": len(absolute_gates) == 8 and all(gate["minimum_seconds"] == 6.0 and gate["maximum_seconds"] == 120.0 and gate["telemetry_cadence_seconds"] == 2.0 and gate["consecutive_samples"] == 4 and gate["anchor"] == expected_anchor and gate["envelope_pass"] is absolute_gate_envelopes[index] for index, gate in enumerate(absolute_gates)),
            "local_after_is_absolute_before": all(absolute_gates[index]["resource_before"] == block_gates[index]["resource_after"] for index in range(8)),
            "absolute_after_is_block_before": all(blocks[index]["resource_before"] == absolute_gates[index]["resource_after"] for index in range(8)),
            "all_thirty_four_resource_snapshots_pass": len(resource_rows) == 34 and all(resource_pass(row) for row in resource_rows),
            "block_medians_recomputed": all(close(block_medians[mode][i], summaries["block_median_milliseconds"][mode][i]) for mode in block_medians for i in range(8)),
            "aggregate_and_stability_recomputed": all(close(aggregate[mode], summaries["aggregate_mode_median_milliseconds"][mode]) for mode in aggregate) and close(stability, summaries["aggregate_mse_stability_min_over_max"]),
            "order_effects_recomputed": all(close(effects[mode], summaries["order_effect_ratio_second_over_first"][mode]) for mode in effects),
            "aggregate_ratio_recomputed": close(aggregate["mse"] / aggregate["smooth_l1"], summaries["aggregate_mse_over_smooth_l1_ratio"]),
            "telemetry_ranges_recomputed": all(close(measurement_ranges[key], summaries["telemetry_ranges"][key]) for key in measurement_ranges),
            "attribution_rule_recomputed": result["attribution"] == expected_attribution and summaries["device_excursion"] is device_excursion,
            "registered_completion_gates": all(result["gates"].values()),
        })
        recomputed.update({
            "attribution": expected_attribution,
            "aggregate_mse_stability_min_over_max": stability,
            "order_effect_ratio_second_over_first": effects,
            "aggregate_mse_over_smooth_l1_ratio": aggregate["mse"] / aggregate["smooth_l1"],
            "measurement_telemetry_ranges": measurement_ranges,
            "block_gate_terminal_ranges": block_gate_ranges,
            "absolute_gate_terminal_ranges": absolute_gate_ranges,
        })

    failed = [name for name, passed in checks.items() if not passed]
    audit = {
        "schema_version": "v5.pcv013.result_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "artifact_sha256": sha256(args.result),
        "runner_sha256": sha256(args.runner),
        "checks": checks,
        "checks_passed": len(checks) - len(failed),
        "checks_total": len(checks),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "classification": result["classification"] if not failed else "PCV013_AUDIT_FAIL_CLOSED",
        "recomputed": recomputed,
        "official_hands": 0,
        "behavior_launch_authority": "NONE_ROUTE_REVIEW025_ONLY",
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": audit["overall"], "passed": audit["checks_passed"], "total": audit["checks_total"], "failed": failed, "classification": audit["classification"], "recomputed": recomputed}, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
