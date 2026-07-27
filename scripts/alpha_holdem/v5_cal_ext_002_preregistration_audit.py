#!/usr/bin/env python3
"""Independent fail-closed audit for CAL-EXT-002 preregistration."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PREREG = ROOT / "reports/v5_cal_ext_002_preregistration_20260716.json"
OUT = ROOT / "reports/v5_cal_ext_002_preregistration_audit_20260716.json"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for block in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    p = json.loads(PREREG.read_text(encoding="utf-8"))
    c: dict[str, bool] = {}
    c["schema"] = p.get("schema_version") == "v5.external_calibration.preregistration.v1"
    c["identity"] = p.get("measurement_id") == "CAL-EXT-002_H11_CONTROL_GREEDY_QUICK5K"
    c["registered_no_launch"] = p.get("status") == "REGISTERED_NO_LAUNCH"
    c["classification"] = p.get("classification") == "EXTERNAL_STAGED_CALIBRATION_ONLY"
    a = p["authority"]
    authority_files = {
        "goal": ROOT / "reports/v5_campaign_goal_v2_activation_20260715.json",
        "rr8_result": ROOT / "reports/v5_hybrid_route_review_008_result_20260716.json",
        "rr8_audit": ROOT / "reports/v5_hybrid_route_review_008_audit_20260716.json",
        "h12_judgment": ROOT / "reports/v5_hybrid_h12_judgment_20260716.json",
        "h12_audit": ROOT / "reports/v5_hybrid_h12_terminal_audit_20260716.json",
    }
    expected_authority = {
        "goal": a["goal_v2_activation_sha256"],
        "rr8_result": a["route_review_008_result_sha256"],
        "rr8_audit": a["route_review_008_audit_sha256"],
        "h12_judgment": a["h12_terminal_judgment_sha256"],
        "h12_audit": a["h12_terminal_audit_sha256"],
    }
    for key, path in authority_files.items():
        c[f"authority_{key}"] = path.is_file() and sha(path) == expected_authority[key]
    h12_audit = json.loads(authority_files["h12_audit"].read_text(encoding="utf-8"))
    c["h12_terminal_pass"] = h12_audit.get("overall") == "PASS_COMPLETE_H12_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION"
    c["post_h12_gate"] = a.get("post_h12_cal_ext_002_required") is True and a.get("behavior_launch_blocked_until_cal_and_route_review_009_complete") is True
    cp = p["checkpoint"]
    source = Path(cp["source_path"])
    frozen = Path(cp["frozen_path"])
    c["source_exists"] = source.is_file()
    c["frozen_exists"] = frozen.is_file()
    c["checkpoint_hash_source"] = source.is_file() and sha(source) == cp["source_and_frozen_sha256"]
    c["checkpoint_hash_frozen"] = frozen.is_file() and sha(frozen) == cp["source_and_frozen_sha256"]
    c["checkpoint_bytes"] = source.is_file() and frozen.is_file() and source.stat().st_size == frozen.stat().st_size == cp["bytes"]
    manifest_path = ROOT / cp["run_manifest"]
    endpoint_path = ROOT / cp["endpoint_status"]
    protocol_path = ROOT / cp["protocol_status"]
    c["manifest_hash"] = sha(manifest_path) == cp["run_manifest_sha256"]
    c["endpoint_hash"] = sha(endpoint_path) == cp["endpoint_status_sha256"]
    c["protocol_hash"] = sha(protocol_path) == cp["protocol_status_sha256"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    endpoint = json.loads(endpoint_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    c["manifest_finished"] = manifest.get("status") == "finished"
    c["endpoint_pass"] = endpoint.get("overall") == "PASS" and endpoint.get("state") == "ARM_ENDPOINT_FROZEN"
    c["protocol_pass"] = protocol.get("overall") == "PASS" and protocol.get("state") == "ARM_FINISHED_GUARDS_PASS"
    c["checkpoint_identity"] = endpoint.get("run_id") == cp["run_id"] and endpoint.get("iteration") == cp["iteration"] and endpoint.get("hands") == cp["training_hands"] and endpoint.get("checkpoint_sha256") == cp["source_and_frozen_sha256"]
    m = p["match"]
    c["greedy_direct"] = m.get("policy_mode") == "greedy" and m.get("evidence_policy_label") == "greedy-direct"
    c["stack_200"] = m.get("stack_bb") == 200
    c["fixed_4x1250"] = m.get("sessions") == 4 and m.get("hands_per_session") == 1250 and m.get("planned_hands") == 5000
    c["no_adaptation"] = m.get("adaptive_extension") is False and m.get("later_checkpoint") is False and m.get("session_addition_after_score_peek") is False
    c["direct_cpu_below_normal"] = m.get("launch_path") == "direct" and m.get("device") == "cpu" and m.get("child_priority") == "BelowNormal_FAIL_CLOSED"
    gate = p["quick5k_gate_contract"]
    c["quick5k_fail_set"] = gate.get("accepted_fail_set_exact") == ["promotion_hands"] and gate.get("any_other_failure") == "FAIL_CLOSED"
    c["full_bundle"] = len(p.get("required_artifacts", [])) == 9 and "selector_replay_json_and_md" in p["required_artifacts"]
    for rel, expected in p["tool_lock"].items():
        path = ROOT / rel
        c[f"tool_{Path(rel).name}"] = path.is_file() and sha(path) == expected
    i = p["interpretation"]
    c["no_reclassification"] = i.get("h11_reclassification") == i.get("h12_reclassification") == "FORBIDDEN"
    c["no_strength_claim"] = i.get("l5_l6_claim") == "FORBIDDEN" and i.get("v4_improvement_claim") == "FORBIDDEN"
    c["route_review_009_next"] = i.get("must_enter_post_cal_route_review_009") is True
    failed = sorted(k for k, ok in c.items() if not ok)
    out = {
        "schema_version": "v5.external_calibration.preregistration_audit.v1",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "preregistration_sha256": sha(PREREG),
        "checks": c,
        "checks_passed": sum(c.values()),
        "checks_total": len(c),
        "failed": failed,
        "overall": "PASS" if not failed else "FAIL_CLOSED",
        "launch_authority": "NONE_REGISTRATION_AUDIT_ONLY",
    }
    OUT.write_text(json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out, indent=2, sort_keys=True))
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
