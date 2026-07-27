#!/usr/bin/env python3
"""Fail-closed poker-research inference reviewer for the V5 program.

The reviewer separates observations, associations, causal method evidence and
external strength evidence.  It is deliberately conservative: absence of a
validated artifact is represented as MISSING, never inferred from narrative
text, raw chip losses, action frequencies or training health.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "v5.poker_research_review.v1"
ACTION_REGRET_SCHEMA = "v5.action_regret.audit.v1"
OPPONENT_PANEL_SCHEMA = "v5.opponent_panel.audit.v1"
EXP_W1_FAILURE_SCHEMA = "v5.exp_w1.warmup_protocol_failure.v1"
EXP_W1_DESIGN_LOCK_SHA256 = "ed38a7d1465cc22afb1fe69fa7fddb9a5daeb7c0272c437b5f19bb01c1e32984"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_optional(path_text: str | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not path_text:
        return None, None
    path = Path(path_text).resolve()
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"artifact must be a JSON object: {path}")
    return payload, {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


def nested(payload: dict[str, Any] | None, *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def review_loss(payload: dict[str, Any] | None) -> dict[str, Any]:
    valid = bool(
        payload
        and payload.get("schema_version") == "v5.loss_inference.audit.v1"
        and payload.get("status") == "PASS_DESCRIPTIVE_INFERENCE_AUDIT"
    )
    return {
        "status": "AVAILABLE_DESCRIPTIVE_ONLY" if valid else "MISSING_OR_INVALID",
        "evidence_level": "OBSERVATIONAL_LOCALIZATION" if valid else "NONE",
        "loss_localization_available": valid,
        "action_value_identified": False,
        "action_regret_identified": False,
        "may_authorize_behavior_change": False,
        "multiplicity_controlled_association_count": (
            len(payload.get("multiplicity_controlled_associations", payload.get("stable_associations", []))) if valid else 0
        ),
        "reason": (
            "cluster uncertainty and opportunities are available, but realized outcomes do not identify unchosen-action EV"
            if valid
            else "a valid v5.loss_inference.audit.v1 artifact is absent"
        ),
    }


def review_action_regret(payload: dict[str, Any] | None) -> dict[str, Any]:
    checks = {
        "schema": bool(payload and payload.get("schema_version") == ACTION_REGRET_SCHEMA),
        "status": bool(payload and payload.get("status") == "PASS"),
        "validated_estimator": bool(payload and payload.get("counterfactual_estimator_validated") is True),
        "same_information_state": bool(payload and payload.get("same_information_state") is True),
        "legal_action_coverage": bool(payload and payload.get("legal_action_coverage_complete") is True),
        "preregistered_selection": bool(payload and payload.get("selection_preregistered") is True),
        "uncertainty": bool(payload and payload.get("uncertainty_validated") is True),
        "identity_bound": bool(payload and payload.get("identity_bound") is True),
        "source_bundle_verified": bool(payload and payload.get("source_bundle_hash_verified") is True),
        "artifact_audit": bool(payload and payload.get("artifact_audit") == "PASS"),
        "opponent_scope": bool(
            payload and payload.get("opponent_continuation_scope") in {"frozen_internal_policy", "exact_external_policy"}
        ),
    }
    valid = all(checks.values())
    supported_rows = []
    if valid:
        for row in payload.get("rows", []):
            if isinstance(row, dict) and isinstance(row.get("regret_ci_lower_bb"), (int, float)) and row["regret_ci_lower_bb"] > 0:
                supported_rows.append(row)
    return {
        "status": "VALIDATED" if valid else "MISSING_OR_INVALID",
        "evidence_level": "COUNTERFACTUAL_ACTION" if valid else "NONE",
        "checks": checks,
        "supported_action_regret_rows": len(supported_rows),
        "action_specific_intervention_supported": bool(supported_rows),
        "reason": (
            "validated same-information-state counterfactual regret is available"
            if valid
            else "no validated action-regret estimator; do not infer regret from loss buckets"
        ),
    }


def review_crossplay(payload: dict[str, Any] | None) -> dict[str, Any]:
    status = str(payload.get("status") or "") if payload else ""
    errors = payload.get("errors") if payload else None
    valid = bool(
        payload
        and payload.get("schema_version") == "v5.crossplay.cycle_audit.v1"
        and status
        in {
            "SUPPORTED_NONTRANSITIVE_CYCLE",
            "NO_CYCLE_PROVEN_UNCERTAIN_EDGES",
            "NO_SUPPORTED_CYCLE_IN_TESTED_PANEL",
        }
        and nested(payload, "matrix", "complete") is True
        and isinstance(errors, list)
        and not errors
        and nested(payload, "claims", "behavior_change_authorized") is False
        and nested(payload, "claims", "strength_claim_authorized") is False
    )
    temporal = bool(valid and nested(payload, "claims", "temporal_self_play_cycle_supported") is True)
    nontransitive = bool(valid and nested(payload, "claims", "nontransitivity_supported") is True)
    return {
        "status": status if valid else "MISSING_OR_INVALID",
        "evidence_level": "COMMON_DEAL_CROSSPLAY" if valid else "NONE",
        "nontransitivity_supported": nontransitive,
        "temporal_self_play_cycle_supported": temporal,
        "global_nonconvergence_proven": False,
        "may_authorize_behavior_change": False,
        "reason": (
            "frozen common-deal payoff matrix audited"
            if valid
            else "no valid complete common-deal cross-play audit; action-rate oscillation is not cycle proof"
        ),
    }


def review_value(payload: dict[str, Any] | None) -> dict[str, Any]:
    complete = bool(payload and payload.get("status") == "COMPLETED_REPORTING_ONLY")
    decision_payload = payload.get("decision") if payload else None
    decision_payload = decision_payload if isinstance(decision_payload, dict) else {}
    decision = str(decision_payload.get("decision") or "")
    supports = bool(complete and decision_payload.get("route_pivot_exp_w1_eligible") is True and decision.startswith("SUPPORTS_"))
    registration_now = bool(complete and decision_payload.get("exp_w1_registration_authorized_now") is True)
    return {
        "status": decision or "MISSING_OR_INVALID",
        "evidence_level": "OFF_POLICY_CALIBRATION" if payload else "NONE",
        "critic_or_reward_problem_supported": supports,
        "exp_w1_registration_authorized_by_artifact": registration_now,
        "strength_evidence": False,
        "reason": "value calibration is mechanism evidence only, never poker strength",
    }


def review_asset(payload: dict[str, Any] | None) -> dict[str, Any]:
    complete = bool(payload and payload.get("status") == "COMPLETED_REPORTING_ONLY")
    decision_payload = payload.get("decision") if payload else None
    decision_payload = decision_payload if isinstance(decision_payload, dict) else {}
    decision = str(decision_payload.get("decision") or "")
    compatible = bool(complete and decision_payload.get("route_pivot_exp_w2_eligible") is True)
    return {
        "status": decision or "MISSING_OR_INVALID",
        "evidence_level": "ASSET_COMPATIBILITY" if payload else "NONE",
        "compatible_full_200bb_asset": compatible,
        "exp_w2_registration_authorized_by_artifact": bool(complete and decision_payload.get("exp_w2_registration_authorized_now") is True),
        "strength_evidence": False,
    }


def review_method(payload: dict[str, Any] | None) -> dict[str, Any]:
    if not payload:
        return {
            "status": "MISSING",
            "evidence_level": "NONE",
            "same_start_controlled": False,
            "classification": None,
            "inference_scope": None,
        }
    first_60 = payload.get("first_60_rows") if isinstance(payload.get("first_60_rows"), dict) else {}
    design_lock = payload.get("design_lock") if isinstance(payload.get("design_lock"), dict) else {}
    registered_gate = payload.get("registered_gate") if isinstance(payload.get("registered_gate"), dict) else {}
    protocol_effect = payload.get("protocol_effect") if isinstance(payload.get("protocol_effect"), dict) else {}
    valid_protocol_abort = (
        payload.get("schema_version") == "v5.exp005c.protocol_failure.v1"
        and payload.get("immutable") is True
        and payload.get("classification") == "EXP005C_FAIL_PROTOCOL_ABORT"
        and design_lock.get("sha256") == "2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007"
        and design_lock.get("sha256") == design_lock.get("expected_sha256")
        and int(registered_gate.get("minimum_rows") or 0) == 60
        and float(registered_gate.get("abort_ratio_below") or 0.0) == 0.85
        and int((first_60.get("control") or {}).get("row_count") or 0) == 60
        and int((first_60.get("treatment") or {}).get("row_count") or 0) == 60
        and first_60.get("gate_result") == "FAIL"
        and float(first_60.get("treatment_over_control_ratio") or 1.0) < float(first_60.get("threshold") or 0.0)
        and protocol_effect.get("authoritative_method_classification") == "EXP005C_FAIL_PROTOCOL_ABORT"
        and protocol_effect.get("classification") == "POST_PROTOCOL_EXPLORATORY_ONLY"
    )
    if valid_protocol_abort:
        return {
            "status": "VALID_PROTOCOL_ABORT",
            "evidence_level": "OPS_PROTOCOL_VALIDITY",
            "same_start_controlled": False,
            "common_deal_endpoint_evaluation": False,
            "classification": "FAIL",
            "inference_scope": "REGISTERED_PROTOCOL_ABORT_NO_POKER_EFFECT_ESTIMATE",
            "single_model_candidate_decision_authorized": False,
            "general_method_claim_authorized": False,
        }
    warmup = payload.get("warmup_gate") if isinstance(payload.get("warmup_gate"), dict) else {}
    treatment = payload.get("treatment") if isinstance(payload.get("treatment"), dict) else {}
    downstream = payload.get("downstream") if isinstance(payload.get("downstream"), dict) else {}
    valid_w1_warmup_abort = (
        payload.get("schema_version") == EXP_W1_FAILURE_SCHEMA
        and payload.get("immutable") is True
        and payload.get("classification") == "EXP_W1_FAIL_WARMUP_GATE"
        and design_lock.get("revision") == 3
        and design_lock.get("sha256") == EXP_W1_DESIGN_LOCK_SHA256
        and warmup.get("status") == "FAIL"
        and warmup.get("locked_failure_action") == "ABORT_BEFORE_NORMAL_PPO"
        and isinstance(warmup.get("relative_heldout_mse_reduction"), (int, float))
        and isinstance(warmup.get("minimum_relative_heldout_mse_reduction"), (int, float))
        and float(warmup["relative_heldout_mse_reduction"])
        < float(warmup["minimum_relative_heldout_mse_reduction"])
        and float(warmup["minimum_relative_heldout_mse_reduction"]) == 0.02
        and treatment.get("normal_ppo_iterations_completed") == 0
        and treatment.get("endpoint_authority") == "NONE"
        and downstream.get("primary100k") == "FORBIDDEN"
        and downstream.get("promotion20k") == "FORBIDDEN"
        and downstream.get("formal100k") == "FORBIDDEN"
        and downstream.get("slumbot") == "FORBIDDEN"
        and payload.get("program_stop") == "FREEZE_TIER2_NO_2_7B_INERTIA"
    )
    if valid_w1_warmup_abort:
        return {
            "status": "VALID_WARMUP_ABORT",
            "evidence_level": "OPS_PROTOCOL_VALIDITY",
            "same_start_controlled": False,
            "common_deal_endpoint_evaluation": False,
            "classification": "FAIL",
            "inference_scope": "REGISTERED_WARMUP_ABORT_NO_POKER_EFFECT_ESTIMATE",
            "single_model_candidate_decision_authorized": False,
            "general_method_claim_authorized": False,
            "terminal_experiment": "EXP-W1",
        }
    terminal_experiments = [
        str(item) for item in payload.get("terminal_experiments", [])
        if isinstance(item, str) and item
    ]
    classification = str(payload.get("classification") or payload.get("decision") or payload.get("status") or "").upper()
    if classification not in {"PASS", "FAIL", "INCONCLUSIVE"}:
        classification = None
    same_start = bool(payload.get("same_start_controlled") is True)
    common_deal = bool(payload.get("common_deal_endpoint_evaluation") is True)
    seed_count = int(payload.get("independent_training_seeds") or 1)
    valid = classification is not None and same_start and common_deal
    scope = None
    if valid:
        scope = "GENERAL_METHOD_EFFECT" if seed_count >= 2 else "CONDITIONAL_SINGLE_SEED_METHOD_EFFECT"
    return {
        "status": "VALID" if valid else "MISSING_OR_INVALID",
        "evidence_level": "SAME_START_CAUSAL" if valid else "NONE",
        "same_start_controlled": same_start,
        "common_deal_endpoint_evaluation": common_deal,
        "classification": classification if valid else None,
        "independent_training_seeds": seed_count if valid else None,
        "inference_scope": scope,
        "terminal_experiments": terminal_experiments,
        "general_method_claim_authorized": bool(valid and classification == "PASS" and seed_count >= 2),
        "single_model_candidate_decision_authorized": bool(valid and classification == "PASS"),
    }


def review_opponent_panel(payload: dict[str, Any] | None) -> dict[str, Any]:
    opponents = payload.get("opponents", []) if payload else []
    checks = {
        "schema": bool(payload and payload.get("schema_version") == OPPONENT_PANEL_SCHEMA),
        "status": bool(payload and payload.get("status") == "PASS"),
        "full_hand_200bb": bool(payload and payload.get("full_hand_200bb") is True),
        "greedy_policy": bool(payload and payload.get("policy_mode") == "greedy"),
        "preregistered": bool(payload and payload.get("selection_preregistered") is True),
        "fixed_panel": bool(payload and payload.get("adaptive_opponent_selection") is False),
        "opponent_count": isinstance(opponents, list) and len(opponents) >= 3,
        "identity_and_ci_audited": bool(payload and payload.get("identity_and_ci_audited") is True),
    }
    valid = all(checks.values())
    return {
        "status": "VALIDATED" if valid else "MISSING_OR_INVALID",
        "evidence_level": "FROZEN_OPPONENT_PANEL" if valid else "NONE",
        "checks": checks,
        "opponent_count": len(opponents) if isinstance(opponents, list) else 0,
        "general_200bb_panel_claim_supported": valid,
        "slumbot_strength_claim_authorized": False,
    }


def review_official(payload: dict[str, Any] | None) -> dict[str, Any]:
    result = payload.get("result", payload) if payload else {}
    hands = result.get("hands") if isinstance(result, dict) else None
    bb100 = result.get("bb_per_100") if isinstance(result, dict) else None
    lower = result.get("ci_lower") if isinstance(result, dict) else None
    upper = result.get("ci_upper") if isinstance(result, dict) else None
    evidence_class = str(payload.get("evidence_class") or "") if payload else ""
    policy = str(payload.get("policy_mode") or nested(payload, "policy", "mode") or "") if payload else ""
    if not policy and "greedy_direct" in evidence_class.lower():
        policy = "greedy-direct"
    official = bool(payload and ("official" in evidence_class.lower() or payload.get("official") is True))
    valid_numbers = all(isinstance(value, (int, float)) for value in (hands, bb100, lower, upper))
    ci_order_valid = bool(valid_numbers and float(lower) <= float(bb100) <= float(upper))
    artifacts = payload.get("artifacts", {}) if payload and isinstance(payload.get("artifacts"), dict) else {}
    bundle_complete = bool(
        artifacts.get("bundle_complete") is True
        and artifacts.get("artifact_audit") == "PASS"
        and artifacts.get("hand_review") == "PASS"
    )
    formal = bool(official and ci_order_valid and bundle_complete and int(hands) >= 100_000 and policy.startswith("greedy"))
    l5 = bool(formal and float(bb100) > 0 and float(lower) > 0)
    l6 = bool(l5 and float(bb100) >= 9.1)
    return {
        "status": "FORMAL" if formal else ("EXTERNAL_NONFORMAL" if official and ci_order_valid and bundle_complete else "MISSING_OR_INVALID"),
        "evidence_level": "FORMAL_EXTERNAL" if formal else ("STAGED_EXTERNAL" if official and ci_order_valid and bundle_complete else "NONE"),
        "hands": hands,
        "bb100": bb100,
        "ci_lower": lower,
        "ci_upper": upper,
        "policy_mode": policy or None,
        "ci_order_valid": ci_order_valid,
        "bundle_complete_and_audited": bundle_complete,
        "l5_claim_authorized": l5,
        "l6_claim_authorized": l6,
        "strength_claim_authorized": l5,
    }


def build_review(
    *,
    loss: dict[str, Any] | None = None,
    action_regret: dict[str, Any] | None = None,
    crossplay: dict[str, Any] | None = None,
    value: dict[str, Any] | None = None,
    asset: dict[str, Any] | None = None,
    method: dict[str, Any] | None = None,
    opponent_panel: dict[str, Any] | None = None,
    official: dict[str, Any] | None = None,
    program_state: str = "ACTIVE_REGISTERED_EXPERIMENT",
    sources: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    evidence = {
        "loss_localization": review_loss(loss),
        "action_regret": review_action_regret(action_regret),
        "crossplay_cycle": review_crossplay(crossplay),
        "value_calibration": review_value(value),
        "asset_compatibility": review_asset(asset),
        "method_experiment": review_method(method),
        "opponent_panel": review_opponent_panel(opponent_panel),
        "official_strength": review_official(official),
    }
    stop_triggered = program_state in {
        "PROGRAM_STOP_TRIGGERED",
        "TIER2_FROZEN_ROUTE_PIVOT",
        "EXP005C_FAIL_PROTOCOL_ABORT",
        "EXP_W1_FAIL_WARMUP_GATE",
    }
    terminal_experiment = evidence["method_experiment"].get("terminal_experiment")
    terminal_experiments = set(evidence["method_experiment"].get("terminal_experiments") or [])
    if terminal_experiment:
        terminal_experiments.add(str(terminal_experiment))
    w1_eligible = bool(
        stop_triggered
        and evidence["value_calibration"]["critic_or_reward_problem_supported"]
        and "EXP-W1" not in terminal_experiments
    )
    w2_eligible = bool(stop_triggered and evidence["asset_compatibility"]["compatible_full_200bb_asset"])
    action_intervention = bool(evidence["action_regret"]["action_specific_intervention_supported"])
    temporal_cycle = bool(evidence["crossplay_cycle"]["temporal_self_play_cycle_supported"])

    if not stop_triggered:
        overall = "CONTINUE_REGISTERED_PROGRAM_NO_NEW_BEHAVIOR_DECISION"
    elif w1_eligible and w2_eligible:
        overall = "ROUTE_PIVOT_CHOICE_REQUIRED_NEVER_BUNDLE"
    elif w1_eligible:
        overall = "ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION"
    elif w2_eligible:
        overall = "ROUTE_PIVOT_EXP_W2_ELIGIBLE_REQUIRES_REGISTRATION"
    else:
        overall = "PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET"

    next_evidence: list[str] = []
    if not evidence["loss_localization"]["loss_localization_available"]:
        next_evidence.append("run v5_loss_inference_audit on the complete official dump bundle")
    if not evidence["action_regret"]["action_specific_intervention_supported"]:
        next_evidence.append("do not tune an action from raw loss; preregister a validated counterfactual or same-state control if action-specific causality is required")
    if not temporal_cycle:
        next_evidence.append("do not claim self-play cycling; build a complete frozen common-deal snapshot cross-play matrix")
    if not evidence["opponent_panel"]["general_200bb_panel_claim_supported"]:
        next_evidence.append("do not generalize from Slumbot alone; use a preregistered frozen 200bb opponent panel for broad-policy claims")
    if evidence["method_experiment"]["status"] == "MISSING":
        next_evidence.append("wait for the registered same-start method experiment rather than selecting a new behavior change")
    if "EXP-W1" in terminal_experiments:
        next_evidence.append("EXP-W1 is terminally failed; do not reopen it from the historical value-audit eligibility signal")

    return {
        "schema_version": SCHEMA_VERSION,
        "checked_at": utc_now(),
        "program_state": program_state,
        "overall": overall,
        "evidence_matrix": evidence,
        "permissions": {
            "may_localize_loss": evidence["loss_localization"]["loss_localization_available"],
            "may_claim_action_leak_causal": action_intervention,
            "may_register_action_specific_intervention": action_intervention,
            "may_claim_panel_nontransitivity": evidence["crossplay_cycle"]["nontransitivity_supported"],
            "may_claim_temporal_self_play_cycle": temporal_cycle,
            "may_claim_global_nonconvergence": False,
            "may_claim_general_200bb_panel_performance": evidence["opponent_panel"]["general_200bb_panel_claim_supported"],
            "may_claim_l5": evidence["official_strength"]["l5_claim_authorized"],
            "may_claim_l6": evidence["official_strength"]["l6_claim_authorized"],
            "route_pivot_exp_w1_eligible": w1_eligible,
            "route_pivot_exp_w2_eligible": w2_eligible,
            "may_bundle_w1_w2": False,
            "new_behavior_change_authorized_by_this_review": False,
        },
        "claim_language": {
            "loss": "where realized outcomes occurred; not the EV of an unchosen action",
            "value": "critic/reward mechanism support; not poker strength",
            "cycle": "panel non-transitivity only when the complete common-deal matrix supports it; never global non-convergence",
            "method": evidence["method_experiment"].get("inference_scope"),
            "generalization": "frozen preregistered opponent panel only; Slumbot alone is the acceptance target, not broad generalization",
            "strength": "formal official greedy-direct evidence only",
        },
        "required_next_evidence": next_evidence,
        "sources": sources or [],
    }


def write_markdown(result: dict[str, Any], path: Path) -> None:
    permissions = result["permissions"]
    lines = [
        "# V5 Poker Research Review",
        "",
        f"- Program state: `{result['program_state']}`",
        f"- Overall: `{result['overall']}`",
        f"- Causal action leak claim allowed: `{permissions['may_claim_action_leak_causal']}`",
        f"- Temporal self-play cycle claim allowed: `{permissions['may_claim_temporal_self_play_cycle']}`",
        f"- Global non-convergence claim allowed: `{permissions['may_claim_global_nonconvergence']}`",
        f"- L5 / L6 claim allowed: `{permissions['may_claim_l5']}` / `{permissions['may_claim_l6']}`",
        "",
        "## Evidence matrix",
        "",
        "| domain | status | level |",
        "|---|---|---|",
    ]
    for name, row in result["evidence_matrix"].items():
        lines.append(f"| `{name}` | `{row.get('status')}` | `{row.get('evidence_level')}` |")
    lines.extend(["", "## Required next evidence", ""])
    if result["required_next_evidence"]:
        lines.extend(f"- {item}" for item in result["required_next_evidence"])
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "This review never launches a behavior change. It only determines which claims and experiment registrations the current evidence can support.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a fail-closed poker research evidence matrix.")
    parser.add_argument("--loss-inference-json", default="")
    parser.add_argument("--action-regret-json", default="")
    parser.add_argument("--crossplay-cycle-json", default="")
    parser.add_argument("--value-audit-json", default="")
    parser.add_argument("--asset-audit-json", default="")
    parser.add_argument("--method-judgment-json", default="")
    parser.add_argument("--opponent-panel-json", default="")
    parser.add_argument("--official-result-json", default="")
    parser.add_argument(
        "--program-state",
        choices=["ACTIVE_REGISTERED_EXPERIMENT", "PROGRAM_STOP_TRIGGERED", "TIER2_FROZEN_ROUTE_PIVOT", "EXP005C_FAIL_PROTOCOL_ABORT", "EXP_W1_FAIL_WARMUP_GATE"],
        default="ACTIVE_REGISTERED_EXPERIMENT",
    )
    parser.add_argument("--out-json", default="")
    parser.add_argument("--out-md", default="")
    args = parser.parse_args()

    payloads: dict[str, dict[str, Any] | None] = {}
    sources: list[dict[str, Any]] = []
    for key, path_text in {
        "loss": args.loss_inference_json,
        "action_regret": args.action_regret_json,
        "crossplay": args.crossplay_cycle_json,
        "value": args.value_audit_json,
        "asset": args.asset_audit_json,
        "method": args.method_judgment_json,
        "opponent_panel": args.opponent_panel_json,
        "official": args.official_result_json,
    }.items():
        payload, source = load_optional(path_text)
        payloads[key] = payload
        if source:
            source["role"] = key
            sources.append(source)
    result = build_review(program_state=args.program_state, sources=sources, **payloads)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.out_json:
        output = Path(args.out_json)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.out_md:
        write_markdown(result, Path(args.out_md))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
