#!/usr/bin/env python3
"""Fail-closed audit for the HYBRID H1 critic-v2 preregistration."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA = "v5.hybrid.h1.preregistration.v1"
AUDIT_SCHEMA = "v5.hybrid.h1.preregistration_audit.v1"
SOURCE_SHA = "bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e"
GOAL_SHA = "7b691750e19716289956036c0d9cf84901941453e6120fa7d6b620bfd942b156"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def nested(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def audit(payload: dict[str, Any], *, repo: Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []

    def add(name: str, passed: bool, detail: str) -> None:
        checks.append({"name": name, "pass": bool(passed), "detail": detail})

    add("schema", payload.get("schema_version") == SCHEMA, str(payload.get("schema_version")))
    add("identity", payload.get("experiment_id") == "H1" and payload.get("route") == "HYBRID", "H1/HYBRID")
    add("immutable_registered_no_launch", payload.get("immutable") is True and payload.get("status") == "REGISTERED_NO_LAUNCH", str(payload.get("status")))
    add("user_escalation", nested(payload, "authority", "user_route_escalation_event") == "v5-user-route-escalation-hybrid-goal-20260711", str(nested(payload, "authority", "user_route_escalation_event")))
    add("source_identity", nested(payload, "source", "checkpoint_sha256") == SOURCE_SHA and nested(payload, "source", "iteration") == 31400 and nested(payload, "source", "hands") == 515989661, str(payload.get("source")))
    add("goal_identity", nested(payload, "baseline_code", "goal_sha256") == GOAL_SHA, str(nested(payload, "baseline_code", "goal_sha256")))
    add("terminal_experiments_closed", nested(payload, "terminal_experiment_exclusions", "exp005c") == "EXP005C_FAIL_PROTOCOL_ABORT_DO_NOT_REOPEN" and nested(payload, "terminal_experiment_exclusions", "exp_w1") == "EXP_W1_FAIL_WARMUP_GATE_DO_NOT_REOPEN_OR_REUSE_ENDPOINTS", str(payload.get("terminal_experiment_exclusions")))
    add("single_atomic_contract", nested(payload, "single_window_variable", "name") == "critic_contract" and nested(payload, "single_window_variable", "control") == "critic_v1" and nested(payload, "single_window_variable", "treatment") == "critic_v2" and nested(payload, "single_window_variable", "atomic_package") is True, str(payload.get("single_window_variable")))
    add("fixed_scaling_no_popart", nested(payload, "arms", "treatment", "fixed_effective_stack_divisor") == 200.0 and nested(payload, "arms", "treatment", "popart") is False, str(nested(payload, "arms", "treatment", "fixed_effective_stack_divisor")))
    add("critic_isolation_depth", nested(payload, "arms", "treatment", "value_head_input") == "shared trunk h.detach()" and nested(payload, "arms", "treatment", "value_gradient_to_shared_trunk") is False and nested(payload, "arms", "treatment", "value_head") == "Sequential Linear(256,256),ReLU,Linear(256,128),ReLU,Linear(128,1)", str(nested(payload, "arms", "treatment", "value_head")))
    add("value_coefficient", nested(payload, "arms", "control", "value_coef") == 0.5 and nested(payload, "arms", "treatment", "value_coef") == 1.0, f"{nested(payload, 'arms', 'control', 'value_coef')}->{nested(payload, 'arms', 'treatment', 'value_coef')}")
    add("actor_identity_gate", nested(payload, "cutover_invariants", "pretraining_policy_logits_max_abs_delta") == 0.0 and nested(payload, "cutover_invariants", "source_actor_weights_bitwise_identical") is True and nested(payload, "cutover_invariants", "actor_optimizer_state_bitwise_identical") is True, str(payload.get("cutover_invariants")))
    add("same_start_fixed_window", nested(payload, "arms", "common", "actual_hands_per_arm") == 20_000_000 and nested(payload, "arms", "common", "fixed_training_deal_stream") is True and nested(payload, "statistics", "no_adaptive_extension") is True and nested(payload, "statistics", "no_second_seed") is True and nested(payload, "statistics", "no_later_endpoint") is True, str(nested(payload, "arms", "common", "actual_hands_per_arm")))
    add("holdout_contract", nested(payload, "calibration_dataset", "id") == "H1-CAL-001" and nested(payload, "calibration_dataset", "training_use") == "FORBIDDEN_HOLDOUT_ONLY" and nested(payload, "calibration_dataset", "common_deal_pairs") == 10_000 and nested(payload, "calibration_dataset", "status_required_before_launch") == "IMMUTABLE_BUNDLE_AUDIT_PASS", str(payload.get("calibration_dataset")))
    add("primary_gate", nested(payload, "statistics", "pass_point_relative_reduction") == 0.15 and nested(payload, "statistics", "pass_ci_lower_relative_reduction") == 0.10 and nested(payload, "statistics", "cluster_bootstrap_repetitions") == 10_000, str(payload.get("statistics")))
    add("throughput_entropy_guards", nested(payload, "guards", "throughput", "abort_if_treatment_over_control_effective_hps_below") == 0.85 and nested(payload, "guards", "throughput", "full_window_noninferiority_ratio") == 0.85 and nested(payload, "guards", "entropy", "treatment_median_min") == 0.3 and nested(payload, "guards", "entropy", "noninferior_to_control_median_delta") == -0.10, str(payload.get("guards")))
    add("terminal_rules_frozen", nested(payload, "terminal_rule", "no_extension") is True and nested(payload, "terminal_rule", "no_reclassification") is True and all(isinstance(nested(payload, "terminal_rule", name), str) and nested(payload, "terminal_rule", name) for name in ("pass", "fail", "inconclusive")), str(payload.get("terminal_rule")))
    add("no_official_or_strength", nested(payload, "authority", "official_slumbot_hands") == 0 and nested(payload, "authority", "official_evaluation") == "FORBIDDEN_IN_H1" and nested(payload, "downstream", "official_slumbot") == "FORBIDDEN" and nested(payload, "downstream", "l5_l6_claim") == "FORBIDDEN", str(payload.get("downstream")))
    add("launch_still_blocked", nested(payload, "authority", "control_or_treatment_launch") == "NONE_UNTIL_SEPARATE_DESIGN_LOCK_AND_PREFLIGHT_PASS", str(nested(payload, "authority", "control_or_treatment_launch")))

    if repo is not None:
        source = repo / str(nested(payload, "source", "checkpoint_path"))
        goal = repo / "docs" / "V5_CURRENT_GOAL.md"
        ledger = repo / "reports" / "v5_experiment_ledger.md"
        current_goal_matches = goal.is_file() and sha256_file(goal) == GOAL_SHA
        ledger_bytes = ledger.read_bytes() if ledger.is_file() else b""
        authority_event = b"v5-user-route-escalation-hybrid-goal-20260711"
        ledger_authority_matches = authority_event in ledger_bytes and GOAL_SHA.encode("ascii") in ledger_bytes
        add("source_file_hash", source.is_file() and sha256_file(source) == SOURCE_SHA, str(source))
        add(
            "goal_authority_chain",
            current_goal_matches or ledger_authority_matches,
            f"current_alias={current_goal_matches}; ledger_event={ledger_authority_matches}",
        )

    failed = [row for row in checks if not row["pass"]]
    return {
        "schema_version": AUDIT_SCHEMA,
        "checked_at": utc_now(),
        "status": "PASS_REGISTERED_NO_LAUNCH" if not failed else "FAIL_CLOSED",
        "checks": checks,
        "passed": len(checks) - len(failed),
        "failed": len(failed),
        "failed_checks": [row["name"] for row in failed],
        "launch_authority": "NONE",
        "official_hands_authorized": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preregistration", required=True)
    parser.add_argument("--repo", default=".")
    parser.add_argument("--out-json", required=True)
    args = parser.parse_args()
    prereg = Path(args.preregistration)
    result = audit(json.loads(prereg.read_text(encoding="utf-8")), repo=Path(args.repo).resolve())
    result["preregistration_path"] = str(prereg.resolve())
    result["preregistration_sha256"] = sha256_file(prereg)
    Path(args.out_json).write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"].startswith("PASS_") else 2


if __name__ == "__main__":
    raise SystemExit(main())
