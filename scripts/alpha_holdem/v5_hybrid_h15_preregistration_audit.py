#!/usr/bin/env python3
"""Independent fail-closed audit of immutable H15 preregistration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_hybrid_h15_preregistration_20260719.json"
OUT = ROOT / "reports/v5_hybrid_h15_preregistration_audit_v2_20260719.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8"))
    c: dict[str, bool] = {}
    c["schema"] = d.get("schema_version") == "v5.hybrid.h15.preregistration.v1"
    c["identity"] = d.get("experiment_id") == "H15"
    c["registered_no_launch"] = d.get("status") == "REGISTERED_NO_LAUNCH"
    rr = d["route_review"]
    c["rr_result_hash"] = sha(ROOT / rr["result_path"]) == rr["result_sha256"]
    c["rr_audit_hash"] = sha(ROOT / rr["audit_path"]) == rr["audit_sha256"]
    c["rr_selection"] = rr.get("selected_prerequisite") == "CPV004_CORRECTED_FINAL_CLEANUP_OBSERVATION_GATE" and rr.get("route_exhausted") is False
    ep = d["engineering_prerequisite"]
    c["cpv_result_hash"] = sha(ROOT / ep["result_path"]) == ep["result_sha256"]
    c["cpv_audit_hash"] = sha(ROOT / ep["audit_path"]) == ep["audit_sha256"]
    cpv_result = json.loads((ROOT / ep["result_path"]).read_text(encoding="utf-8"))
    cpv_audit = json.loads((ROOT / ep["audit_path"]).read_text(encoding="utf-8"))
    c["cpv_pass"] = cpv_result.get("overall") == "PASS" and cpv_result.get("aggregate", {}).get("cycles_passed") == 20
    c["cpv_audit_pass"] = cpv_audit.get("overall") == "PASS" and cpv_audit.get("checks_passed") == 33
    c["cpv_effect"] = ep.get("effect") == "PERMITS_SEPARATE_H15_PREREGISTRATION_ONLY"
    repair = d["control_plane_repair"]
    c["repair_proven"] = repair.get("status") == "PROVEN_BY_CPV004_PASS_PENDING_H15_INTEGRATION_AUDIT"
    c["repair_readiness"] = repair.get("readiness") == "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS"
    c["repair_identity"] = "CREATION_TIME" in repair.get("supervisor_identity", "") and "COMMAND_LINE_SHA256" in repair.get("supervisor_identity", "")
    c["five_roles"] = repair.get("required_exact_child_roles") == ["health", "protocol", "endpoint", "treatment_launch", "completion"]
    c["final_cleanup"] = "ONE_FINAL_TAGGED_SURVIVOR_GATE" in repair.get("cleanup", "") and repair.get("per_child_survivor_snapshots") == "DIAGNOSTIC_ONLY_NOT_GATE"
    source = d["source"]
    c["source_hash"] = sha(Path(source["checkpoint_path"])) == source["checkpoint_sha256"]
    c["source_identity"] = source.get("iteration") == 35051 and source.get("hands") == 576021901 and source.get("optimizer_preserved") is True
    terminal = d["source_terminal_evidence"]
    for key in ("run_manifest", "endpoint_status", "protocol_status"):
        c[f"source_{key}_hash"] = sha(ROOT / terminal[f"{key}_path"]) == terminal[f"{key}_sha256"]
    manifest = json.loads((ROOT / terminal["run_manifest_path"]).read_text(encoding="utf-8"))
    endpoint = json.loads((ROOT / terminal["endpoint_status_path"]).read_text(encoding="utf-8"))
    protocol = json.loads((ROOT / terminal["protocol_status_path"]).read_text(encoding="utf-8"))
    c["source_terminal"] = manifest.get("status") == "finished" and endpoint.get("overall") == "PASS" and protocol.get("overall") == "PASS"
    single = d["single_variable"]
    c["single_variable"] = single.get("control") == "MSE" and single.get("treatment") == "SmoothL1" and single.get("treatment_beta_raw_bb") == 1.0 and single.get("standard_ppo_critic_loss_both_arms") == "MSE"
    c["no_beta_search"] = "no CAL-EXT-002" in single.get("beta_selection", "")
    forbidden = " ".join(d["forbidden_sources"])
    c["partials_forbidden"] = all(token in forbidden for token in ("H12 attempted", "H13 attempted", "H14 partial"))
    c["dummy_forbidden"] = "CPV003 or CPV004 dummy-process artifacts as training input" in forbidden
    arms = d["arms"]
    c["fresh_fixed_arms"] = arms.get("order") == ["control", "treatment"] and arms.get("actual_hands_each") == 20000000 and arms.get("minimum_endpoint_hands") == 596021901 and arms.get("maximum_overshoot_hands") == 50000 and arms.get("fresh_same_start") is True
    c["no_adaptation"] = all(arms.get(key) is False for key in ("adaptive_extension", "second_seed", "later_endpoint", "terminal_partial_reuse"))
    c["run_ids"] = "v5_hybrid_h15_control_" in arms.get("control_run_id", "") and "v5_hybrid_h15_treatment_" in arms.get("treatment_run_id", "")
    cfg = d["frozen_common_config"]
    expected_cfg = {"target_kl": 0.03, "value_head_catchup_after_kl_stop": True, "critic_contract": "critic_v1", "value_coef": 0.5, "ppo_epochs": 4, "mini_batch_size": 1024, "workers": 22, "rollout_mode": "multi", "rollout_envs_per_worker": 16, "fixed_training_deal_stream": True, "opponent_assignment": "per-iteration", "preflop_action_prior_coef": 0.01, "postflop_action_prior_coef": 0.02, "optimizer_reset": False}
    c["common_config"] = all(cfg.get(key) == value for key, value in expected_cfg.items())
    c["allin_ev"] = cfg.get("mirror_self_play_deals") is True and cfg.get("allin_runout_ev") is True and cfg.get("allin_runout_ev_max_runouts") == 200
    perf = d["performance_calibration"]
    c["perf_cal"] = perf.get("required_immediately_before_each_arm") is True and perf.get("control_seed") == 2026071905 and perf.get("treatment_seed") == 2026071906 and perf.get("warmup_steps") == 10 and perf.get("timed_steps") == 40 and perf.get("repeats") == 3 and perf.get("loss_throughput_ratio_min") == 0.95
    c["perf_fail_closed"] = perf.get("failure_action") == "FAIL_CLOSED_NO_ARM_LAUNCH" and "H15_DESIGN_LOCK" in perf.get("tool_hashes", "")
    cp = d["control_plane"]
    c["cp_readiness"] = cp.get("startup_readiness") == "INITIAL_READY_BEFORE_PROCESS_SCAN_WITHIN_10_SECONDS"
    c["cp_binding"] = "CREATION_TIME" in cp.get("allowed_child_binding", "") and len(cp.get("allowed_child_roles", [])) == 5 and cp.get("broad_process_class_allowlist") == "FORBIDDEN"
    c["cp_pid_reuse"] = cp.get("supervisor_exit_or_pid_reuse") == "LIFECYCLE_SHUTDOWN_NOT_RESOURCE_VIOLATION_AFTER_CREATION_IDENTITY_CHECK"
    c["cp_final_cleanup"] = "ONE_FINAL_TAGGED_SURVIVOR_GATE" in cp.get("cleanup", "") and cp.get("per_child_survivor_snapshots") == "DIAGNOSTIC_ONLY_NOT_GATE"
    c["cp_stage_order"] = cp.get("control_stage_order") == [["health", "protocol"], ["endpoint"], ["treatment_launch", "completion"]] and cp.get("treatment_stage_order") == [["health", "protocol"], ["endpoint"], ["completion"]]
    isolation = d["resource_isolation"]
    c["isolation"] = isolation.get("evaluation_during_arm") == isolation.get("slumbot_during_arm") == "FORBIDDEN" and "INCLUDING_FILE_READ_HASH_PROCESS_LIST" in isolation.get("parent_or_delegated_observer_commands", "")
    c["path1"] = "EXISTING_EXACT_LOCKED_SIX_BELOWNORMAL" in isolation.get("path1_existing_job", "") and "NO_RESTART_EXPANSION" in isolation.get("path1_existing_job", "")
    gates = d["gates"]
    expected_gates = {"endpoint_mse_primary_reduction_point_min": 0.075, "endpoint_mse_primary_ci95_lower_min": 0.0, "source_anchor_degradation_point_max": 0.05, "source_anchor_degradation_ci95_upper_max": 0.1, "kl_p95_max": 0.03, "first60_hps_ratio_min": 0.85, "full_hps_ratio_min": 0.85, "entropy_median_last200_min": 0.3, "entropy_treatment_minus_control_min": -0.1, "mirror_pairs": 40000, "mirror_treatment_control_ci95_lower_min_bb100": -20.0, "mirror_treatment_source_ci95_lower_min_bb100": -20.0}
    c["science_gates"] = all(gates.get(key) == value for key, value in expected_gates.items())
    c["verdicts"] = all(key in d["judgment"] for key in ("pass", "fail", "inconclusive")) and d["judgment"].get("route_review_after_fail_or_inconclusive") is True
    external = d["external_policy"]
    c["official_policy"] = external.get("during_arms_official_hands") == 0 and "H15_TREATMENT_GREEDY_DIRECT_QUICK5K" in external.get("method_pass_next", "") and "ROUTE_REVIEW_013" in external.get("fail_or_inconclusive_next", "")
    authority = d["authority"]
    c["launch_blocked"] = authority.get("launch", "").startswith("BLOCKED_UNTIL_H15_CPV004_INTEGRATION_AUDIT")
    c["official_zero"] = authority.get("official_hands") == 0
    c["no_strength"] = authority.get("strength_claim") == "FORBIDDEN"
    c["holdout_forbidden"] = "FORBIDDEN_HOLDOUT_ONLY" in d.get("holdout", "")
    failed = sorted(name for name, passed in c.items() if not passed)
    out = {
        "schema_version": "v5.hybrid.h15.preregistration_audit.v2",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": sha(P),
        "checks": c,
        "checks_passed": sum(c.values()),
        "checks_total": len(c),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "launch_authority": "NONE_REGISTRATION_AUDIT_ONLY",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
