#!/usr/bin/env python3
"""Fail-closed independent audit for the immutable H11 preregistration."""
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

    check("identity", registration.get("experiment_id") == "H11" and registration.get("status") == "REGISTERED_NO_LAUNCH")
    route = registration.get("route_review", {})
    check("route_result", (root / route.get("result_path", "")).is_file() and sha(root / route["result_path"]) == route.get("result_sha256"))
    check("route_audit", route.get("audit_sha256") == sha(root / "reports/v5_hybrid_route_review_007_audit_20260715.json"))
    check("route_not_exhausted", route.get("route_exhausted") is False)
    source = registration.get("source", {})
    source_path = Path(source.get("checkpoint_path", ""))
    check("source_exact", source_path.is_file() and sha(source_path) == source.get("checkpoint_sha256") == "7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438")
    check("source_gate", source.get("iteration") == 33834 and source.get("hands") == 556011085 and source.get("optimizer_preserved") is True)
    forbidden = registration.get("forbidden_sources", [])
    check("three_forbidden_sources", len(forbidden) == 3)
    for index, item in enumerate(forbidden):
        path = root / item.get("path", "")
        check(f"forbidden_source_{index + 1}", path.is_file() and sha(path) == item.get("sha256"))
    variable = registration.get("single_variable", {})
    check("single_variable", variable.get("control") == "MSE" and variable.get("treatment") == "SmoothL1" and variable.get("treatment_beta_raw_bb") == 1.0)
    check("standard_critic_unchanged", variable.get("standard_ppo_critic_loss_both_arms") == "MSE")
    arms = registration.get("arms", {})
    check("fresh_fixed_arms", arms.get("actual_hands_each") == 20000000 and arms.get("minimum_endpoint_hands") == 576011085 and arms.get("fresh_same_start") is True)
    check("no_adaptive_reuse", arms.get("adaptive_extension") is False and arms.get("second_seed") is False and arms.get("later_endpoint") is False and arms.get("h9_or_h10_outcome_reuse") is False)
    check("h11_run_ids", "v5_hybrid_h11_control" in arms.get("control_run_id", "") and "v5_hybrid_h11_treatment" in arms.get("treatment_run_id", ""))
    common = registration.get("frozen_common_config", {})
    check("config_core", common.get("target_kl") == 0.03 and common.get("workers") == 22 and common.get("rollout_envs_per_worker") == 16)
    check("priors_fixed", common.get("preflop_action_prior_coef") == 0.01 and common.get("postflop_action_prior_coef") == 0.02)
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
    authority = registration.get("authority", {})
    check("launch_blocked", str(authority.get("launch", "")).startswith("BLOCKED_UNTIL_IMPLEMENTATION"))
    check("official_zero", authority.get("official_hands") == 0 and registration.get("post_window_external_policy", {}).get("during_arms_official_hands") == 0)
    check("strength_forbidden", authority.get("strength_claim") == "FORBIDDEN")
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.h11.preregistration_audit.v1",
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
