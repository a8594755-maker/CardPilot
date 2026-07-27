#!/usr/bin/env python3
"""Publish the immutable H14 preregistration from H13 science plus RR010 gates."""
from __future__ import annotations
import copy, json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "reports/v5_hybrid_h13_preregistration_20260716.json"
OUT = ROOT / "reports/v5_hybrid_h14_preregistration_20260717.json"

def transform(value):
    if isinstance(value, dict): return {k: transform(v) for k,v in value.items()}
    if isinstance(value, list): return [transform(v) for v in value]
    if isinstance(value, str):
        return value.replace("H13", "H14").replace("h13", "h14")
    return value

def main() -> int:
    if OUT.exists():
        raise SystemExit("refusing to overwrite immutable H14 preregistration")
    d = transform(copy.deepcopy(json.loads(SOURCE.read_text(encoding="utf-8"))))
    d["schema_version"] = "v5.hybrid.h14.preregistration.v1"
    d["experiment_id"] = "H14"
    d["registered_at"] = "2026-07-17T16:16:00Z"
    d["route_review"] = {
        "result_path": "reports/v5_hybrid_route_review_010_result_20260717.json",
        "result_sha256": "1c4ad93ce51350bb38374a81d7c1f5d53c70ea1f9f3b7400933f434f7268b3a7",
        "audit_path": "reports/v5_hybrid_route_review_010_audit_20260717.json",
        "audit_sha256": "401e7f5044b32d1d545317bde1e49eeadf611e505374e40f7c04b3175c96aac6",
        "selected_next": "H14_CLEAN_ROBUST_VALUE_HEAD_CATCHUP_AFTER_EXACT_LIFECYCLE_CHILD_ALLOWLIST_FIX",
        "route_exhausted": False,
    }
    d["control_plane_repair"] = {
        "status": "REQUIRED_BEFORE_IMPLEMENTATION_AUDIT_OR_LAUNCH",
        "trigger_incident_path": "reports/v5_hybrid_h13_resource_isolation_incident_20260717.json",
        "trigger_incident_sha256": "cad2d325faad44b12604f7b8d930408dc80716cf10aaa2c1c30430b80346172d",
        "terminal_audit_path": "reports/v5_hybrid_h13_terminal_audit_20260717.json",
        "terminal_audit_sha256": "e061add072023f8a474780fe6300bea12988d18d7f0150c0d334086b564a9fb5",
        "required_exact_child_roles": ["health", "protocol", "endpoint", "treatment_launch", "completion"],
        "binding": ["script_identity", "parent_relationship", "design_lock_identity", "command_line_sha256", "full_trigger_provenance"],
        "adversarial_contract": "REGISTERED_CHILDREN_PASS;UNREGISTERED_SIBLING_OR_COMMAND_MISMATCH_FAILS_CLOSED",
        "broad_process_class_allowlist": "FORBIDDEN",
        "independent_audit": "REQUIRED_BEFORE_DESIGN_LOCK",
    }
    d["hypothesis"] = "H13 supplied exactly zero scientific exposure because its protocol allowlist omitted the exact registered health-watcher child. With a prospectively complete exact-role lifecycle allowlist and all prior guards retained,replacing only catch-up value-head MSE with SmoothL1 beta1.0 may improve frozen endpoint critic calibration while preserving source-anchor accuracy,KL,throughput,entropy and common-deal mirror performance."
    d["forbidden_sources"] = [
        "H9 partial control", "H10 partial control", "H11 partial treatment",
        "H12 attempted control directory or any H12 artifact",
        "H13 attempted control directory or any H13 artifact",
        "CAL-EXT-001 or CAL-EXT-002 benchmark checkpoint copies",
        "any later checkpoint or optimizer reset",
    ]
    d["arms"].update({
        "control_run_id": "v5_hybrid_h14_control_catchmse_same35051_20m_r1_20260717",
        "treatment_run_id": "v5_hybrid_h14_treatment_catchsmoothl1b1_same35051_20m_r1_20260717",
    })
    d["performance_calibration"].update({
        "implementation_path": "scripts/alpha_holdem/v5_hybrid_h14_perf_cal.py",
        "independent_audit_path": "scripts/alpha_holdem/v5_hybrid_h14_perf_cal_audit.py",
        "control_seed": 2026071703,
        "treatment_seed": 2026071704,
        "tool_hashes": "MUST_BE_FROZEN_BY_H14_DESIGN_LOCK_AFTER_IMPLEMENTATION_AUDIT",
    })
    d["control_plane"] = {
        "startup_log_missing": "PENDING_UNTIL_180_SECONDS_THEN_FAIL_CLOSED",
        "allowed_child_roles": ["health", "protocol", "endpoint", "treatment_launch", "completion"],
        "allowed_child_binding": "EXACT_SCRIPT_PARENT_RELATIONSHIP_DESIGN_LOCK_AND_COMMAND_LINE_SHA256",
        "broad_process_class_allowlist": "FORBIDDEN",
        "unregistered_sibling_or_command_mismatch": "FAIL_CLOSED_FULL_PROVENANCE_AND_TERMINATE_ACTIVE_H14_TRAINER",
        "canonical_rearm_survival_failure": "STATUS_FALSE_AND_EXIT_NONZERO",
        "launcher_rearm_success": "PROCESS_EXIT_ZERO_AND_STATUS_SURVIVAL_PASS_TRUE",
        "control_stage_order": [["health", "protocol"], ["endpoint"], ["treatment_launch", "completion"]],
        "treatment_stage_order": [["health", "protocol"], ["endpoint"], ["completion"]],
        "unexpected_watcher_exit": "FAIL_CLOSED_AND_TERMINATE_ACTIVE_H14_TRAINER",
        "h14_specific_tool_hashes": "MUST_BE_FROZEN_BY_DESIGN_LOCK",
        "canonical_rearm_validate_only": "MUST_PASS_BEFORE_LAUNCH",
    }
    d["resource_isolation"].update({
        "path1_existing_job": "MAY_CONTINUE_EXISTING_PID23720_SIX_BELOWNORMAL_CPU_WORKERS_NO_RESTART_EXPANSION_OR_NEW_WORKERS",
        "allowed_project_processes": "EXACT_LOCKED_H14_LIFECYCLE_PLUS_EXISTING_PATH1_ONLY",
    })
    d["external_policy"].update({
        "method_pass_next": "EXACT_H14_TREATMENT_GREEDY_DIRECT_QUICK5K_BEFORE_PROMOTION_DECISION",
        "fail_or_inconclusive_next": "ROUTE_REVIEW_011;CAL_ONLY_IF_25M_TARGET_OR_50M_OR_TWO_TERMINAL_WINDOWS_GATE_IS_DUE",
    })
    d["authority"].update({
        "launch": "BLOCKED_UNTIL_H14_EXACT_ROLE_REPAIR_AUDIT_IMPLEMENTATION_AUDIT_DESIGN_LOCK_PREFLIGHT_EXACT_CONTROL_PERF_CAL_AND_CANONICAL_REARM_PASS",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    })
    OUT.write_text(json.dumps(d, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(OUT)
    return 0

if __name__ == "__main__": raise SystemExit(main())
