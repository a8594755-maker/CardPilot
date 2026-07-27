#!/usr/bin/env python3
"""Independent fail-closed audit of the immutable H18 design lock."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--design-lock", type=Path, required=True)
    parser.add_argument("--expected-lock-sha256", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    value = load(args.design_lock)
    checks: dict[str, bool] = {}
    errors: list[str] = []

    def check(name: str, passed: bool) -> None:
        checks[name] = bool(passed)
        if not passed:
            errors.append(name)

    check("hash", sha(args.design_lock) == args.expected_lock_sha256.lower())
    check(
        "identity",
        value.get("schema_version") == "v5.hybrid.h18.design_lock.v1"
        and value.get("design_id") == "H18"
        and value.get("status") == "LOCKED",
    )
    prereg = value.get("preregistration", {})
    prereg_audit = value.get("preregistration_audit", {})
    implementation = value.get("implementation_audit", {})
    integration = value.get("control_plane_integration_audit", {})
    route = value.get("route_review", {})
    check("preregistration", prereg.get("sha256") == "8f1f3df1c7fee8c4f8990d5354313330d497f75b1d81de6ceb1f7aa9b4225481")
    check("preregistration_audit", prereg_audit.get("overall") == "PASS" and prereg_audit.get("checks") == "32/32 PASS")
    check("implementation_audit", implementation.get("overall") == "PASS_H18_IMPLEMENTATION" and implementation.get("checks") == "23/23 PASS")
    check("integration_audit", integration.get("overall") == "PASS" and integration.get("checks") == "31/31 PASS")
    check("route_review", route.get("route_exhausted") is False and route.get("selected_next") == "H18_SEPARATELY_REGISTERED_TOLERANCE_AND_GPU_EVENT_PREARM_CORRECTION")
    pcv007 = value.get("pcv007", {})
    check("pcv007_binding", pcv007.get("classification") == "PCV007_PASS_NUMERICAL_ENVELOPE_AND_GPU_EVENT_TIMING" and pcv007.get("interpretation") == "CONTROL_PLANE_ONLY")

    source = value.get("source", {})
    source_path = Path(source.get("path", ""))
    check(
        "source",
        source.get("sha256") == "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"
        and source.get("iteration") == 35051
        and source.get("hands") == 576021901
        and source_path.is_file()
        and sha(source_path) == source.get("sha256"),
    )
    check("source_anchor", value.get("source_anchor") == source)
    check(
        "single_variable",
        value.get("single_variable") == {
            "name": "catchup_value_loss",
            "control": "mse",
            "treatment": "smooth_l1_beta_1.0",
            "common_value_head_catchup": True,
            "common_ppo_target_kl": 0.03,
        },
    )
    budget = value.get("arm_budget", {})
    check(
        "fresh_fixed_arms",
        budget.get("actual_hands_each") == 20_000_000
        and budget.get("minimum_endpoint_hands") == 596_021_901
        and budget.get("maximum_overshoot_hands") == 50_000
        and budget.get("order") == ["control", "treatment"]
        and value.get("common_config", {}).get("reset_optimizer") is False,
    )
    arms = value.get("arms", {})
    check("control_arm", arms.get("control", {}).get("catchup_value_loss") == "mse")
    check("treatment_arm", arms.get("treatment", {}).get("catchup_value_loss") == "smooth_l1")
    calibration = value.get("representative_prearm_calibration", {})
    check(
        "representative_prearm_calibration",
        calibration.get("rows") == 4096
        and calibration.get("mini_batch_size") == 1024
        and calibration.get("ppo_epochs") == 4
        and calibration.get("target_kl") == 1e-12
        and calibration.get("timer") == "torch.cuda.Event_with_synchronize"
        and calibration.get("warmup_updates_per_mode") == 4
        and calibration.get("timed_updates_per_repeat_per_mode") == 16
        and calibration.get("repeats") == 7
        and calibration.get("old_log_prob_offset") == 10.0
        and calibration.get("required_ppo_epochs_completed") == 1
        and calibration.get("required_catchup_epochs") == 3
        and calibration.get("full_update_throughput_ratio_min") == 0.85
        and calibration.get("mse_repeat_stability_ratio_min") == 0.95
        and calibration.get("non_value_model_max_abs_tolerance") == 1e-6
        and calibration.get("non_value_optimizer_max_abs_tolerance") == 1e-8
        and calibration.get("bitwise_non_value_identity") == "FORBIDDEN_AS_GATE",
    )

    registry = value.get("control_plane", {}).get("exact_lifecycle_child_registry", {})
    check(
        "exact_lifecycle_registry",
        registry.get("roles") == ["health", "protocol", "endpoint", "treatment_launch", "completion"]
        and registry.get("binding") == [
            "pid", "parent_pid", "creation_time", "executable",
            "command_line_sha256", "script_sha256", "design_lock_sha256", "role",
        ],
    )
    control_plane = value.get("control_plane", {})
    check("startup_readiness", control_plane.get("startup_readiness") == "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS")
    check("final_cleanup", control_plane.get("cleanup") == "FULL_REGISTERED_SEQUENCE_THEN_ONE_FINAL_TAGGED_SURVIVOR_GATE_WITHIN_15_SECONDS")
    check("safe_control_boundary", control_plane.get("control_safe_boundary") == "TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY")
    isolation = value.get("resource_isolation", {})
    check("active_isolation", isolation.get("evaluation_during_arm") == "FORBIDDEN" and isolation.get("parent_or_delegated_observer_commands") == "FORBIDDEN_WHILE_EITHER_ARM_ACTIVE_INCLUDING_FILE_READ_HASH_PROCESS_LIST")
    check("path1_policy", isolation.get("path1_existing_job") == "MAY_CONTINUE_EXISTING_EXACT_LOCKED_SIX_BELOWNORMAL_CPU_WORKERS_NO_RESTART_EXPANSION_OR_NEW_WORKERS")
    check("abort_terminalization", isolation.get("abort_terminalization") == "MUST_SUPPORT_CONTROL_OR_TREATMENT_PROTOCOL_ABORT")
    launch_policy = value.get("launch_policy", {})
    check("launch_policy", launch_policy.get("current_authority") == "NONE_CURRENT_HEARTBEAT" and launch_policy.get("launcher_requires_explicit_switch") == "LaunchAuthorized" and launch_policy.get("validate_only_allowed") is True)

    gates = value.get("gates", {})
    check(
        "scientific_gates",
        gates.get("endpoint_mse_primary_reduction_point_min") == 0.075
        and gates.get("endpoint_mse_primary_ci95_lower_min") == 0.0
        and gates.get("first60_hps_ratio_min") == 0.85
        and gates.get("mirror_treatment_control_ci95_lower_min_bb100") == -20.0
        and gates.get("mirror_treatment_source_ci95_lower_min_bb100") == -20.0
        and gates.get("mirror_ci95_lower_min_bb100") == -20.0,
    )
    measurement = value.get("measurement", {})
    manifest = Path(measurement.get("mirror_dir", "")) / "manifest.json"
    mirror_lock = Path(measurement.get("mirror_dir", "")) / "measurement_lock.json"
    check(
        "mirror_lock",
        measurement.get("mirror_pairs") == 40_000
        and manifest.is_file()
        and sha(manifest) == measurement.get("mirror_manifest_sha256")
        and mirror_lock.is_file()
        and sha(mirror_lock) == measurement.get("mirror_lock_sha256"),
    )
    check("no_official", value.get("official_hands") == 0 and value.get("strength_claim") == "FORBIDDEN")

    for relative, expected in value.get("tools", {}).items():
        path = Path(relative)
        check("tool_" + path.name, path.is_file() and sha(path) == expected)
    for item in value.get("frozen_files", []):
        path = Path(item.get("path", ""))
        check("frozen_" + path.name, path.is_file() and sha(path) == item.get("sha256"))

    result = {
        "schema_version": "v5.hybrid.h18.design_lock_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS_IMMUTABLE_H18_DESIGN_LOCK" if not errors else "FAIL_CLOSED",
        "checks": checks,
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "errors": errors,
        "design_lock_sha256": sha(args.design_lock),
        "official_hands": 0,
    }
    args.out.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not errors else 2


if __name__ == "__main__":
    raise SystemExit(main())
