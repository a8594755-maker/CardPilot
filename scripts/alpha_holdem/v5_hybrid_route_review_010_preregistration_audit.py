#!/usr/bin/env python3
"""Independent fail-closed audit of Route Review 010 preregistration."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
P = ROOT / "reports/v5_hybrid_route_review_010_preregistration_20260717.json"
OUT = ROOT / "reports/v5_hybrid_route_review_010_preregistration_audit_20260717.json"

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    d = json.loads(P.read_text(encoding="utf-8")); c = {}
    c["schema"] = d.get("schema_version") == "v5.hybrid.route_review.preregistration.v10.v1"
    c["identity"] = d.get("design_id") == "HYBRID-ROUTE-REVIEW-010"
    c["reporting_only"] = d.get("status") == "REGISTERED_REPORTING_ONLY_NO_LAUNCH"
    t = d["trigger"]
    c["judgment_hash"] = sha(ROOT / "reports/v5_hybrid_h13_judgment_20260717.json") == t["h13_judgment_sha256"]
    c["incident_hash"] = sha(ROOT / "reports/v5_hybrid_h13_resource_isolation_incident_20260717.json") == t["h13_incident_sha256"]
    c["terminal_audit_hash"] = sha(ROOT / "reports/v5_hybrid_h13_terminal_audit_20260717.json") == t["h13_terminal_audit_sha256"]
    audit = json.loads((ROOT / "reports/v5_hybrid_h13_terminal_audit_20260717.json").read_text(encoding="utf-8"))
    c["h13_terminal_pass"] = audit.get("overall") == "PASS_COMPLETE_H13_TERMINAL_INCONCLUSIVE_RESOURCE_ISOLATION"
    c["zero_progress"] = t.get("h13_training_progress_hands") == 0 and t.get("h13_terminal") == "H13_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION"
    f = d["frozen_inputs"]
    frozen_paths = {
        "route_review_009_result": "reports/v5_hybrid_route_review_009_result_20260716.json",
        "route_review_009_audit": "reports/v5_hybrid_route_review_009_audit_20260716.json",
        "h13_control_plane_repair": "reports/v5_h13_control_plane_repair_20260716.json",
        "h13_control_plane_repair_audit": "reports/v5_h13_control_plane_repair_audit_20260716.json",
        "cal_ext_002_completion": "reports/v5_cal_ext_002_completion_20260716.json",
        "cal_ext_002_completion_audit": "reports/v5_cal_ext_002_completion_audit_20260716.json",
        "path1_recovery": "reports/v5_h13_orphan_path1_recovery_20260717.json",
    }
    for key, rel in frozen_paths.items(): c[f"frozen_{key}"] = sha(ROOT / rel) == f[f"{key}_sha256"]
    truth = d["truth_constraints"]
    c["terminal_branches"] = all("TERMINAL" in truth[k] for k in ("w1", "exp005c", "h11", "h12", "h13"))
    c["h13_never_reopen"] = "NEVER_REOPEN" in truth["h13"]
    c["official_l0"] = truth.get("official_strength") == "L0"
    c["no_action_tuning"] = truth.get("action_regret") == "MISSING" and truth.get("action_specific_tuning") == "FORBIDDEN"
    c["path1_asset_only"] = "ASSET_GENERATION_ONLY" in truth.get("path1", "")
    order = d["candidate_order"]
    c["candidate_order"] = len(order) == 4 and order[0].startswith("H14_") and order[-1] == "ROUTE_EXHAUSTION_ESCALATION"
    rules = " ".join(d["decision_rule"]).lower()
    c["rule_no_h13_reopen"] = "never resume" in rules and "h13" in rules
    c["rule_exact_zero"] = "scientific exposure is exactly zero" in rules
    c["rule_same_science"] = "mse-versus-smoothl1 beta1" in rules
    c["rule_no_action_tune"] = "action regret" in rules
    c["rule_fail_closed"] = "do not launch h14" in rules
    c["rule_exhaustion"] = "route exhaustion only" in rules
    gates = d["mandatory_h14_control_plane_gate"]
    gate_text = " ".join(gates).lower()
    c["seven_gates"] = len(gates) == 7
    c["exact_roles"] = "every exact lock-bound lifecycle child role" in gate_text
    c["parent_lock_binding"] = "parent relationship" in gate_text and "design-lock" in gate_text
    c["adversarial"] = "unregistered sibling" in gate_text and "command-mismatch" in gate_text
    c["prior_repairs_retained"] = "startup-log pending" in gate_text and "rearm nonzero" in gate_text and "launcher survival" in gate_text
    c["orphans_absent"] = "dead-parent python" in gate_text
    c["path1_identity"] = "six belownormal cpu workers" in gate_text
    c["full_prelaunch"] = "production perf-cal" in gate_text and "canonical ordered rearm" in gate_text
    c["no_behavior_authority"] = d["output_contract"].get("behavior_launch_authority") == "NONE_REVIEW_ONLY"
    c["official_zero"] = d["output_contract"].get("official_hands_authority") == 0
    c["no_strength"] = d["evidence_policy"].get("strength_claim") == "FORBIDDEN"
    failed = sorted(k for k,v in c.items() if not v)
    out = {"schema_version":"v5.hybrid.route_review.preregistration_audit.v10.v1","checked_at":datetime.now(timezone.utc).isoformat(),"preregistration_sha256":sha(P),"checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"overall":"PASS" if not failed else "FAIL_CLOSED","behavior_launch_authority":"NONE_AUDIT_ONLY","official_hands":0,"strength_claim":"FORBIDDEN"}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(out,indent=2,sort_keys=True)); return 0 if not failed else 1

if __name__ == "__main__": raise SystemExit(main())
