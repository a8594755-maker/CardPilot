#!/usr/bin/env python3
"""Independent fail-closed audit for HYBRID Route Review007."""
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
    parser.add_argument("--result", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    registration = load(args.registration)
    result = load(args.result)
    checks: dict[str, bool] = {}

    def check(name: str, condition: bool) -> None:
        checks[name] = bool(condition)

    check("registration_identity", registration.get("design_id") == "HYBRID-ROUTE-REVIEW-007" and registration.get("status") == "REGISTERED")
    check("result_identity", result.get("design_id") == "HYBRID-ROUTE-REVIEW-007" and result.get("overall") == "PASS_ROUTE_REVIEW")
    check("registration_hash_bound", result.get("registration_sha256") == sha(args.registration))
    frozen = registration.get("frozen_inputs", [])
    check("frozen_inputs_count", len(frozen) == 9)
    for index, item in enumerate(frozen):
        path = Path(item.get("path", ""))
        check(f"frozen_input_{index + 1}", path.is_file() and sha(path) == item.get("sha256"))
    trigger = registration.get("trigger", {})
    check("two_no_progress_incidents", trigger.get("consecutive_method_no_progress_windows") == 2 and trigger.get("h10_method_evidence") == "NONE")
    h10 = result.get("evidence_matrix", {}).get("H10", {})
    check("h10_judgment_exact", h10.get("judgment_sha256") == "c29671f5e5fce292d0fdadc4a351c2c089137f2d018f614b7564657dd3178897")
    check("h10_incident_exact", h10.get("incident_sha256") == "5c40cb7b692d71f8211bacf05aba4cc1571f8e0bd4ab34d140a40a421e5adb57")
    check("h10_endpoint_missing", h10.get("control_last_hands") == 557293500 and h10.get("remaining_hands") == 18717585)
    check("h10_no_method_evidence", h10.get("treatment_launched") is False and h10.get("method_evidence") == "NONE")
    check("h10_provenance_limit", h10.get("trigger_command_identity_preserved") is False and h10.get("resource_contention_proven") is False)
    check("first60_not_method", h10.get("control_first60_inference") == "THROUGHPUT_BASELINE_ONLY")
    external = result.get("evidence_matrix", {}).get("external_state", {})
    check("external_result_exact", external.get("cal_ext_001_hands") == 5000 and external.get("cal_ext_001_bb100") == -207.1804)
    check("external_not_action_authority", external.get("action_specific_intervention_authorized") is False)
    path1 = result.get("evidence_matrix", {}).get("Path1", {})
    check("path1_incomplete_ineligible", path1.get("frozen_complete_qa_pass_boards") == 204 and path1.get("v55_training_eligible") is False)
    decision = result.get("decision", {})
    check("h11_selected", decision.get("selected_next") == "H11_CLEAN_RERUN_ROBUST_VALUE_HEAD_CATCHUP_AFTER_CONTROL_PLANE_GATE")
    check("source_exact", decision.get("source", {}).get("checkpoint_sha256") == "7c388ec68114d497f775157def3c0b3abc82db7ee25baf7e7cb7e9e916f66438")
    variable = decision.get("single_variable", {})
    check("single_variable_exact", variable.get("control") == "MSE" and variable.get("treatment") == "SmoothL1 beta=1.0 raw critic-v1 bb unit")
    gate = decision.get("control_plane_gate", [])
    check("full_trigger_provenance_required", any("command-line SHA256" in item for item in gate))
    check("control_abort_terminalization_required", any("either control or treatment" in item for item in gate))
    check("no_observer_active_arm_required", any("No parent or delegated shell" in item for item in gate))
    scientific = decision.get("scientific_lock", [])
    check("fresh_h11_only", any("never use H9/H10 partial checkpoints" in item for item in scientific))
    check("fixed_sample_unchanged", any("fixed20M actual hands per arm" in item for item in scientific))
    check("h10_baseline_not_reused", any("Do not reuse H10 first60" in item for item in scientific))
    check("route_not_exhausted", result.get("route_exhausted") is False)
    check("no_direct_launch", str(result.get("behavior_launch_authorized", "")).startswith("ONLY_AFTER_NEW_H11"))
    check("official_zero", result.get("official_hands_authorized") == 0)
    check("strength_forbidden", result.get("strength_claim") == "FORBIDDEN")
    failed = [name for name, passed in checks.items() if not passed]
    payload = {
        "schema_version": "v5.hybrid.route_review.audit.v7.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "checks_passed": sum(checks.values()),
        "checks_total": len(checks),
        "checks": checks,
        "failed": failed,
        "preregistration_sha256": sha(args.registration),
        "result_sha256": sha(args.result),
        "route_exhausted": result.get("route_exhausted"),
        "behavior_launch_authority": "NONE_UNTIL_NEW_H11_LIFECYCLE_PASS",
        "official_hands": 0,
        "strength_claim": "FORBIDDEN",
    }
    args.out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main())
