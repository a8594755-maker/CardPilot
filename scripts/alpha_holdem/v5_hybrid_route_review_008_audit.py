#!/usr/bin/env python3
"""Independent fail-closed audit for HYBRID Route Review008."""
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
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--registration", type=Path, required=True)
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    registration = load(args.registration)
    result = load(args.result)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("registration_identity", registration.get("design_id") == "HYBRID-ROUTE-REVIEW-008" and registration.get("status") == "REGISTERED")
    check("result_identity", result.get("design_id") == "HYBRID-ROUTE-REVIEW-008" and result.get("overall") == "PASS_ROUTE_REVIEW")
    check("registration_hash_bound", result.get("registration_sha256") == sha(args.registration))
    frozen = registration.get("frozen_inputs", [])
    check("frozen_inputs_count", len(frozen) == 13)
    for index, item in enumerate(frozen):
        path = repo / item.get("path", "")
        check(f"frozen_input_{index + 1}", path.is_file() and sha(path) == item.get("sha256"))

    trigger = registration.get("trigger", {})
    check("review_trigger", trigger.get("consecutive_method_no_progress_windows") == 2 and trigger.get("h11_method_effect_evidence") == "NONE" and trigger.get("route_review_required") is True)
    h11 = result.get("evidence_matrix", {}).get("H11", {})
    check("h11_terminal_exact", h11.get("terminal") == "H11_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT" and h11.get("judgment_sha256") == "88f86867183a36abbf34fedc6eb7556b2fd81e33c1fd47f79e44031ae41fa316")
    check("h11_terminal_audit_exact", h11.get("terminal_audit_sha256") == "fb6217793ea703eb7521dcc6b7d9bdf2d4980c5895c578867e5208aa117c0122" and h11.get("terminal_audit") == "PASS_COMPLETE_H11_TERMINAL_FAIL_PROTOCOL_ABORT")
    check("h11_protocol_numbers", h11.get("control_first60_hps") == 1971.3414690797654 and h11.get("treatment_first60_hps") == 1366.4866033762237 and h11.get("first60_ratio") == 0.6931760046696062 and h11.get("first60_minimum") == 0.85)
    check("h11_no_treatment_endpoint", h11.get("treatment_endpoint_frozen") is False and h11.get("method_effect_evidence") == "NONE")
    check("h11_clean_control", h11.get("control_endpoint_frozen") is True and h11.get("control_endpoint_hands") == 576021901 and h11.get("control_checkpoint_sha256") == "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13")
    diagnosis = result.get("evidence_matrix", {}).get("throughput_diagnosis", {})
    check("diagnosis_exact", diagnosis.get("artifact_sha256") == "8e92b23f9d2984b1cbc2f83bf797f1a5962476e558064ebcda2c3b4d5261c6bd" and diagnosis.get("registered_fail_valid") is True)
    check("diagnosis_no_causal_overreach", diagnosis.get("smooth_l1_causal_30pct_penalty_established") is False and diagnosis.get("cross_day_resource_matching_established") is False)
    check("diagnosis_values", diagnosis.get("ratio_without_catchup_epochs") == 0.6923162158841403 and diagnosis.get("isolated_loss_time_ratio_mse_over_smoothl1") == 0.974035219953)
    control_plane = result.get("evidence_matrix", {}).get("control_plane", {})
    check("control_plane_not_ready", control_plane.get("h12_launch_ready") is False and "NOT_YET_FIXED" in control_plane.get("endpoint_health_producer_under_strict_rearm", "") and "NOT_YET_FIXED" in control_plane.get("dependent_watcher_start_order", ""))
    external = result.get("evidence_matrix", {}).get("external_state", {})
    check("external_debt_exact", external.get("new_clean_source_hands") - external.get("cal_ext_001_checkpoint_hands") == 20010816 and external.get("target_25m_due_now") is False and external.get("hard_50m_due_now") is False)
    check("external_strength_l0", external.get("cal_ext_001_hands") == 5000 and external.get("cal_ext_001_bb100") == -207.1804 and external.get("strength") == "L0")
    path1 = result.get("evidence_matrix", {}).get("Path1", {})
    check("path1_unchanged_ineligible", path1.get("coordinator_pid") == 37656 and path1.get("workers") == 6 and path1.get("v55_training_eligible") is False and path1.get("transition_authority") == "UNCHANGED_DIAGNOSTIC_ONLY_NO_TOUCH")
    alternatives = result.get("evidence_matrix", {}).get("alternative_readiness", {})
    check("alternatives_not_ready", alternatives.get("opponent_pool") == "H4_TERMINAL_INCONCLUSIVE_NO_CANDIDATE" and "INELIGIBLE" in alternatives.get("cfr_distillation", "") and "INCOMPLETE" in alternatives.get("play_time_resolving", ""))
    decision = result.get("decision", {})
    check("h12_selected", decision.get("selected_next") == "H12_RESOURCE_MATCHED_ROBUST_VALUE_HEAD_CATCHUP_AFTER_PERF_CAL_AND_CONTROL_PLANE_REPAIR")
    source = decision.get("source", {})
    check("source_exact", source.get("checkpoint_sha256") == "96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13" and source.get("iteration") == 35051 and source.get("hands") == 576021901)
    variable = decision.get("single_variable", {})
    check("single_variable_exact", variable.get("control") == "MSE" and variable.get("treatment") == "SmoothL1 beta=1.0 raw critic-v1 bb unit" and variable.get("standard_ppo_critic_loss") == "MSE_UNCHANGED")
    scientific = decision.get("scientific_lock", [])
    check("fixed20m_same_start", any("fresh same-start" in item and "fixed20M" in item for item in scientific))
    check("throughput_gate_retained", any("minimum0.85" in item and "no override" in item for item in scientific))
    check("partial_reuse_forbidden", any("H11 treatment partial" in item and "forbidden" in item for item in scientific))
    prelaunch = decision.get("mandatory_prelaunch_gate", [])
    check("perf_cal_required", any("PERF-CAL" in item and ">=0.95" in item for item in prelaunch))
    check("common_baseline_required", any("common MSE system baseline" in item and ">=0.95" in item for item in prelaunch))
    check("health_producer_required", any("endpoint health producer" in item for item in prelaunch))
    check("ordered_rearm_required", any("dependency ordered" in item for item in prelaunch))
    check("path1_no_touch", any("remain untouched" in item for item in prelaunch))
    debt = result.get("external_debt_transition", {})
    check("cal_ext_002_frozen", debt.get("expected_post_h12_debt_hands") == 40010816 and debt.get("cal_ext_002_required_before_h13") is True)
    check("route_not_exhausted", result.get("route_exhausted") is False and decision.get("route_exhausted") is False)
    check("launch_still_blocked", str(result.get("behavior_launch_authorized", "")).startswith("ONLY_AFTER_H12_PERF_CAL_CONTROL_PLANE"))
    check("official_zero", result.get("official_hands_authorized") == 0)
    check("strength_forbidden", result.get("strength_claim") == "FORBIDDEN")

    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.route_review.audit.v8.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "preregistration_sha256": sha(args.registration),
        "result_sha256": sha(args.result),
        "route_exhausted": result.get("route_exhausted"),
        "behavior_launch_authority": "NONE_UNTIL_H12_PERF_CAL_AND_FULL_LIFECYCLE_PASS",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.resolve().write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
