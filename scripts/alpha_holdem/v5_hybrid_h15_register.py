#!/usr/bin/env python3
"""Publish immutable H15 preregistration after CPV004 PASS."""
from __future__ import annotations

import copy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/v5_hybrid_h14_preregistration_20260717.json"
OUT = ROOT / "reports/v5_hybrid_h15_preregistration_20260719.json"


def transform(value):
    if isinstance(value, dict):
        return {key: transform(item) for key, item in value.items()}
    if isinstance(value, list):
        return [transform(item) for item in value]
    if isinstance(value, str):
        return value.replace("H14", "H15").replace("h14", "h15").replace("20260717", "20260719")
    return value


def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite immutable H15 preregistration")
    data = transform(copy.deepcopy(json.loads(SOURCE.read_text(encoding="utf-8"))))
    data["schema_version"] = "v5.hybrid.h15.preregistration.v1"
    data["experiment_id"] = "H15"
    data["registered_at"] = "2026-07-19T15:34:00Z"
    data["route_review"] = {
        "result_path": "reports/v5_hybrid_route_review_012_result_20260719.json",
        "result_sha256": "c2efbdfb9c5090c0434413d45adb8c2a4a9030270ea0c0b17bdbddbcb97165dd",
        "audit_path": "reports/v5_hybrid_route_review_012_audit_20260719.json",
        "audit_sha256": "83361d82fc4e0c613d5045ac2d4d54467852259c6ad8fc38fb072ab2282f2e57",
        "selected_prerequisite": "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE",
        "route_exhausted": False,
    }
    data["engineering_prerequisite"] = {
        "design_id": "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE",
        "result_path": "reports/v5_cpv004_result_20260719.json",
        "result_sha256": "69cdeedc406d5322a407cf3abd54d5f10d13d50ade87c84448b2a49dca132449",
        "audit_path": "reports/v5_cpv004_result_audit_20260719.json",
        "audit_sha256": "b4b03759131ddfc71e04842459fafc3ea46ee684cd6de430a1c6f610cdee38cf",
        "result": "PASS_20_OF_20",
        "audit": "PASS_33_OF_33",
        "effect": "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY",
    }
    data["control_plane_repair"] = {
        "status": "PROVEN_BY_CPV004_PASS_PENDING_H15_INTEGRATION_AUDIT",
        "guard_module": "scripts/alpha_holdem/v5_lifecycle_guard_v2.py",
        "readiness": "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS",
        "supervisor_identity": "PID_CREATION_TIME_EXECUTABLE_COMMAND_LINE_SHA256",
        "supervisor_exit": "LIFECYCLE_SHUTDOWN",
        "supervisor_pid_reuse": "LIFECYCLE_SHUTDOWN_PID_REUSED_NOT_RESOURCE_VIOLATION",
        "required_exact_child_roles": ["health", "protocol", "endpoint", "treatment_launch", "completion"],
        "cleanup": "FULL_REGISTERED_SEQUENCE_THEN_ONE_FINAL_TAGGED_SURVIVOR_GATE_WITHIN_15_SECONDS",
        "per_child_survivor_snapshots": "DIAGNOSTIC_ONLY_NOT_GATE",
        "adversarial_contract": "REGISTERED_CHILDREN_PASS;UNREGISTERED_SIBLING_WRONG_PARENT_OR_HASH_MISMATCH_FAILS_CLOSED",
        "independent_h15_integration_audit": "REQUIRED_BEFORE_DESIGN_LOCK",
    }
    data["hypothesis"] = "CPV004 prospectively validated the corrected lifecycle control plane without trainer exposure. From the exact clean H11 source,replacing only catch-up value-head MSE with SmoothL1 beta1.0 may improve frozen endpoint critic calibration while preserving source-anchor accuracy,KL,throughput,entropy and common-deal mirror performance."
    data["forbidden_sources"] = [
        "H9 partial control",
        "H10 partial control",
        "H11 partial treatment",
        "H12 attempted control directory or any H12 artifact",
        "H13 attempted control directory or any H13 artifact",
        "H14 partial control or any H14 artifact",
        "CPV003 or CPV004 dummy-process artifacts as training input",
        "CAL-EXT-001 or CAL-EXT-002 benchmark checkpoint copies",
        "any later checkpoint or optimizer reset",
    ]
    data["arms"].update({
        "control_run_id": "v5_hybrid_h15_control_catchmse_same35051_20m_r1_20260719",
        "treatment_run_id": "v5_hybrid_h15_treatment_catchsmoothl1b1_same35051_20m_r1_20260719",
    })
    data["performance_calibration"].update({
        "implementation_path": "scripts/alpha_holdem/v5_hybrid_h15_perf_cal.py",
        "independent_audit_path": "scripts/alpha_holdem/v5_hybrid_h15_perf_cal_audit.py",
        "control_seed": 2026071905,
        "treatment_seed": 2026071906,
        "tool_hashes": "MUST_BE_FROZEN_BY_H15_DESIGN_LOCK_AFTER_IMPLEMENTATION_AUDIT",
    })
    data["control_plane"] = {
        "shared_guard_module": "scripts/alpha_holdem/v5_lifecycle_guard_v2.py",
        "startup_readiness": "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS",
        "allowed_child_roles": ["health", "protocol", "endpoint", "treatment_launch", "completion"],
        "allowed_child_binding": "EXACT_PID_PARENT_CREATION_TIME_EXECUTABLE_SCRIPT_DESIGN_LOCK_ROLE_AND_COMMAND_LINE_SHA256",
        "broad_process_class_allowlist": "FORBIDDEN",
        "supervisor_exit_or_pid_reuse": "LIFECYCLE_SHUTDOWN_NOT_RESOURCE_VIOLATION_AFTER_CREATION_IDENTITY_CHECK",
        "unregistered_sibling_or_identity_mismatch": "FAIL_CLOSED_FULL_PROVENANCE_AND_TERMINATE_ACTIVE_H15_TRAINER",
        "cleanup": "FULL_REGISTERED_SEQUENCE_THEN_ONE_FINAL_TAGGED_SURVIVOR_GATE_WITHIN_15_SECONDS",
        "per_child_survivor_snapshots": "DIAGNOSTIC_ONLY_NOT_GATE",
        "canonical_rearm_survival_failure": "STATUS_FALSE_AND_EXIT_NONZERO",
        "launcher_rearm_success": "PROCESS_EXIT_ZERO_AND_STATUS_SURVIVAL_PASS_TRUE",
        "control_stage_order": [["health", "protocol"], ["endpoint"], ["treatment_launch", "completion"]],
        "treatment_stage_order": [["health", "protocol"], ["endpoint"], ["completion"]],
        "unexpected_watcher_exit": "FAIL_CLOSED_AND_TERMINATE_ACTIVE_H15_TRAINER",
        "h15_specific_tool_hashes": "MUST_BE_FROZEN_BY_DESIGN_LOCK",
        "canonical_rearm_validate_only": "MUST_PASS_BEFORE_LAUNCH",
    }
    data["resource_isolation"].update({
        "path1_existing_job": "MAY_CONTINUE_EXISTING_EXACT_LOCKED_SIX_BELOWNORMAL_CPU_WORKERS_NO_RESTART_EXPANSION_OR_NEW_WORKERS",
        "allowed_project_processes": "EXACT_LOCKED_H15_LIFECYCLE_PLUS_EXISTING_EXACT_PATH1_ONLY",
    })
    data["external_policy"].update({
        "method_pass_next": "EXACT_H15_TREATMENT_GREEDY_DIRECT_QUICK5K_BEFORE_PROMOTION_DECISION",
        "fail_or_inconclusive_next": "ROUTE_REVIEW_013;CAL_ONLY_IF_25M_TARGET_OR_50M_OR_TWO_TERMINAL_WINDOWS_GATE_IS_DUE",
    })
    data["authority"].update({
        "launch": "BLOCKED_UNTIL_H15_CPV004_INTEGRATION_AUDIT_IMPLEMENTATION_AUDIT_DESIGN_LOCK_PREFLIGHT_EXACT_CONTROL_PERF_CAL_AND_CANONICAL_REARM_PASS",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    })
    OUT.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
