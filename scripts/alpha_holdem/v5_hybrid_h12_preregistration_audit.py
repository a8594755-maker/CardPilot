#!/usr/bin/env python3
"""Fail-closed independent audit for the immutable H12 preregistration."""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    registration = load(args.registration)
    checks: dict[str, bool] = {}

    def check(name: str, value: bool) -> None:
        checks[name] = bool(value)

    check("identity", registration.get("experiment_id") == "H12" and registration.get("status") == "REGISTERED_NO_LAUNCH")
    check("schema_v3", registration.get("schema_version") == "v5.hybrid.h12.preregistration.v3")
    supersedes = registration.get("supersedes", {})
    superseded_path = root / supersedes.get("path", "")
    check(
        "supersedes_predecessor_prelaunch",
        superseded_path.is_file()
        and sha(superseded_path) == supersedes.get("sha256") == "a9ac9a6aee36c8aa370956d5f9938fa984d54fe04eee5035813b5bde3d0070bc"
        and supersedes.get("launches_under_predecessor") == 0,
    )
    route = registration.get("route_review", {})
    route_path = root / route.get("result_path", "")
    route_audit_path = root / route.get("audit_path", "")
    check("route_result", route_path.is_file() and sha(route_path) == route.get("result_sha256") == "f118c73e4721a2c06731798aaf63fc4762dd63d513c97fa5fa6674f959a1bffe")
    check("route_audit", route_audit_path.is_file() and sha(route_audit_path) == route.get("audit_sha256") == "042f5247367e17e5656d6be4334cf12d47ea7a907233d076765a80088935832e")
    check("route_selection", route.get("selected_next") == "H12_RESOURCE_MATCHED_ROBUST_VALUE_HEAD_CATCHUP_AFTER_PERF_CAL_AND_CONTROL_PLANE_REPAIR" and route.get("route_exhausted") is False)
    source = registration.get("source", {})
    source_path = Path(source.get("checkpoint_path", ""))
    check("source_exact", source_path.is_file() and sha(source_path) == source.get("checkpoint_sha256") == "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13")
    check("source_gate", source.get("iteration") == 35051 and source.get("hands") == 576021901 and source.get("optimizer_preserved") is True)
    forbidden = registration.get("forbidden_sources", [])
    check("four_forbidden_sources", len(forbidden) == 4)
    for index, item in enumerate(forbidden):
        path = root / item.get("path", "")
        check(f"forbidden_source_{index + 1}", path.is_file() and sha(path) == item.get("sha256"))
    variable = registration.get("single_variable", {})
    check("single_variable", variable.get("control") == "MSE" and variable.get("treatment") == "SmoothL1" and variable.get("treatment_beta_raw_bb") == 1.0)
    check("standard_critic_unchanged", variable.get("standard_ppo_critic_loss_both_arms") == "MSE")
    arms = registration.get("arms", {})
    check("fresh_fixed_arms", arms.get("actual_hands_each") == 20000000 and arms.get("minimum_endpoint_hands") == 596021901 and arms.get("maximum_overshoot_hands") == 50000 and arms.get("fresh_same_start") is True)
    check("no_adaptive_reuse", arms.get("adaptive_extension") is False and arms.get("second_seed") is False and arms.get("later_endpoint") is False and arms.get("h9_h10_h11_partial_outcome_reuse") is False)
    check("h12_run_ids", "v5_hybrid_h12_control" in arms.get("control_run_id", "") and "v5_hybrid_h12_treatment" in arms.get("treatment_run_id", ""))
    common = registration.get("frozen_common_config", {})
    check("config_core", common.get("target_kl") == 0.03 and common.get("workers") == 22 and common.get("rollout_envs_per_worker") == 16)
    check("priors_fixed", common.get("preflop_action_prior_coef") == 0.01 and common.get("postflop_action_prior_coef") == 0.02)
    perf = registration.get("performance_calibration", {})
    check("perf_exact_settings", perf.get("required_immediately_before_each_arm") is True and perf.get("seed") == 2026071601 and perf.get("batch_size") == 1024 and perf.get("warmup_steps") == 10 and perf.get("timed_steps") == 40 and perf.get("repeats") == 3 and perf.get("device") == "cuda")
    check("perf_gates", perf.get("loss_throughput_ratio_min") == 0.95 and perf.get("treatment_common_mse_control_baseline_ratio_min") == 0.95 and perf.get("failure_action") == "FAIL_CLOSED_NO_ARM_LAUNCH")
    for label in ("tool", "audit_tool", "offline_smoke", "offline_audit"):
        path = root / perf.get(f"{label}_path", "")
        check(f"perf_{label}_identity", path.is_file() and sha(path) == perf.get(f"{label}_sha256"))
    check("smoke_not_arm_gate", perf.get("offline_smoke_role") == "IMPLEMENTATION_READINESS_ONLY_NOT_ARM_GATE")
    plane = registration.get("control_plane", {})
    for label in ("health_producer", "ordered_rearm", "canonical_rearm"):
        path = root / plane.get(f"{label}_path", "")
        check(f"control_plane_{label}_identity", path.is_file() and sha(path) == plane.get(f"{label}_sha256"))
    check("control_order", plane.get("control_stage_order") == [["health", "protocol"], ["endpoint"], ["treatment_launch", "completion"]])
    check("treatment_order", plane.get("treatment_stage_order") == [["health", "protocol"], ["endpoint"], ["completion"]])
    check("status_identity", plane.get("status_identity") == "DESIGN_LOCK_SHA_AND_ARM_STATE_REQUIRED" and plane.get("unexpected_watcher_exit") == "FAIL_CLOSED_AND_TERMINATE_ACTIVE_H12_TRAINER")
    isolation = registration.get("resource_isolation", {})
    check("no_observer", isolation.get("parent_or_delegated_observer_commands") == "FORBIDDEN_WHILE_EITHER_ARM_ACTIVE_INCLUDING_FILE_READ_HASH_PROCESS_LIST")
    check("full_provenance", isolation.get("full_trigger_provenance") == ["pid", "parent_pid", "creation_time", "executable", "command_line", "command_line_sha256"])
    check("either_arm_terminalization", isolation.get("abort_terminalization") == "MUST_SUPPORT_CONTROL_OR_TREATMENT_PROTOCOL_ABORT")
    check("path1_only_exception", isolation.get("path1_existing_job") == "MAY_CONTINUE_EXISTING_BELOWNORMAL_NO_RESTART_EXPANSION_OR_NEW_WORKERS")
    gates = registration.get("gates", {})
    expected_gates = {
        "endpoint_mse_primary_reduction_point_min": 0.075,
        "endpoint_mse_primary_ci95_lower_min": 0.0,
        "source_anchor_degradation_point_max": 0.05,
        "source_anchor_degradation_ci95_upper_max": 0.10,
        "kl_p95_max": 0.03,
        "kl_fraction_above_0_03_max": 0.06044407894736842,
        "early_stop_trigger_fraction_min": 0.05,
        "first60_hps_ratio_min": 0.85,
        "full_hps_ratio_min": 0.85,
        "entropy_median_last200_min": 0.3,
        "entropy_treatment_minus_control_min": -0.1,
        "mirror_pairs": 40000,
        "mirror_treatment_control_ci95_lower_min_bb100": -20.0,
        "mirror_treatment_source_ci95_lower_min_bb100": -20.0,
    }
    check("gates_exact", gates == expected_gates)
    external = registration.get("post_window_external_policy", {})
    check("external_debt", external.get("current_external_debt_hands") == 20010816 and external.get("expected_post_h12_debt_hands") == 40010816 and str(external.get("cal_ext_002_before_h13", "")).startswith("MANDATORY"))
    authority = registration.get("authority", {})
    check("launch_blocked", str(authority.get("launch", "")).startswith("BLOCKED_UNTIL_IMPLEMENTATION"))
    check("official_zero", authority.get("official_hands") == 0 and external.get("during_arms_official_hands") == 0)
    check("strength_forbidden", authority.get("strength_claim") == "FORBIDDEN")
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.h12.preregistration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "preregistration_sha256": sha(args.registration),
        "launch_authority": "NONE",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
