#!/usr/bin/env python3
"""Independent terminal audit for Hybrid Route Review 010."""
from __future__ import annotations
import hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
R = ROOT / "reports/v5_hybrid_route_review_010_result_20260717.json"
OUT = ROOT / "reports/v5_hybrid_route_review_010_audit_20260717.json"

def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()

def main() -> int:
    d=json.loads(R.read_text(encoding="utf-8")); c={}
    c["schema"]=d.get("schema_version")=="v5.hybrid.route_review.result.v10.v1"
    c["identity"]=d.get("design_id")=="HYBRID-ROUTE-REVIEW-010"
    c["pass_review"]=d.get("overall")=="PASS_ROUTE_REVIEW"
    c["prereg_hash"]=sha(ROOT/"reports/v5_hybrid_route_review_010_preregistration_20260717.json")==d["registration_sha256"]
    c["prereg_audit_hash"]=sha(ROOT/"reports/v5_hybrid_route_review_010_preregistration_audit_20260717.json")==d["registration_audit_sha256"]
    pa=json.loads((ROOT/"reports/v5_hybrid_route_review_010_preregistration_audit_20260717.json").read_text(encoding="utf-8")); c["prereg_audit_pass"]=pa.get("overall")=="PASS" and pa.get("checks_passed")==38
    e=d["evidence_matrix"]; h=e["H13"]
    c["h13_judgment_hash"]=sha(ROOT/"reports/v5_hybrid_h13_judgment_20260717.json")==h["judgment_sha256"]
    c["h13_incident_hash"]=sha(ROOT/"reports/v5_hybrid_h13_resource_isolation_incident_20260717.json")==h["incident_sha256"]
    c["h13_audit_hash"]=sha(ROOT/"reports/v5_hybrid_h13_terminal_audit_20260717.json")==h["terminal_audit_sha256"]
    c["h13_zero_science"]=h.get("control_training_progress_hands")==0 and h.get("control_endpoint") is False and h.get("treatment_launched") is False and h.get("mirror_launched") is False and h.get("official_hands")==0 and h.get("method_effect_evidence")=="NONE"
    c["h13_closed"]=h.get("resume_or_reclassify")=="FORBIDDEN"
    c["trigger_identity"]=h.get("trigger_pid")==50384 and h.get("trigger_parent_pid")==6276 and h.get("trigger_command_sha256")=="d0e91a948fe46eb3d24cc95f72097426f911c5cc30af309c3ff4e083eab06b77"
    cp=e["control_plane"]
    c["prior_repair_hash"]=sha(ROOT/"reports/v5_h13_control_plane_repair_20260716.json")==cp["prior_repair_sha256"]
    c["prior_repair_audit_hash"]=sha(ROOT/"reports/v5_h13_control_plane_repair_audit_20260716.json")==cp["prior_repair_audit_sha256"]
    c["repairable_specific"]=cp.get("repairable_prospectively") is True and cp.get("missing_role")=="v5_hybrid_h13_health_watch.py" and "exact lifecycle child roles" in cp.get("required_contract","")
    src=e["clean_source"]
    c["source_hash"]=sha(ROOT/src["checkpoint_path"])==src["checkpoint_sha256"]
    c["source_identity"]=src.get("iteration")==35051 and src.get("hands")==576021901 and src.get("available") is True
    ext=e["external"]
    c["external_l0"]=ext.get("official_hands")==5000 and ext.get("level")=="L0" and ext.get("promotion_or_formal100k_authorized") is False
    c["external_point_ci"]=ext.get("bb_per_100")==-146.17260000000002 and ext.get("ci95")==[-238.59789051053525,-53.7473094894648]
    c["no_action_tune"]=ext.get("action_regret")=="MISSING" and ext.get("action_specific_tuning")=="FORBIDDEN"
    p=e["Path1"]
    c["path1_recovery_hash"]=sha(ROOT/"reports/v5_h13_orphan_path1_recovery_20260717.json")==p["recovery_sha256"]
    c["path1_asset_hash"]=sha(ROOT/"reports/v5_h3_path1_successor_asset_lock_20260713.json")==p["asset_lock_sha256"]
    c["path1_contract"]=p.get("coordinator_pid")==23720 and p.get("workers")==6 and p.get("priority")=="BelowNormal" and p.get("gpu") is False and "NO_OVERWRITE" in p.get("policy","")
    alt=e["alternatives"]
    c["terminal_alternatives"]=all("TERMINAL" in alt[k] for k in ("W1","EXP005_C","H13"))
    c["deferred_alternatives"]=all("DEFERRED" in alt[k] for k in ("opponent_pool","cfr_distillation","play_time_resolving"))
    dec=d["decision"]
    c["selected_h14"]=dec.get("selected_next")=="H14_CLEAN_ROBUST_VALUE_HEAD_CATCHUP_AFTER_EXACT_LIFECYCLE_CHILD_ALLOWLIST_FIX"
    c["route_not_exhausted"]=dec.get("route_exhausted") is False
    c["decision_source"]=dec["source"].get("checkpoint_sha256")==src.get("checkpoint_sha256") and dec["source"].get("iteration")==35051 and dec["source"].get("hands")==576021901
    sv=dec["single_variable"]
    c["single_variable"]=sv.get("control")=="MSE" and "SmoothL1 beta=1.0" in sv.get("treatment","") and sv.get("standard_ppo_critic_loss")=="MSE_UNCHANGED"
    w=dec["window"]
    c["fixed_fresh_window"]=w.get("fresh_run_ids") is True and w.get("fresh_same_start") is True and w.get("control_hands")==w.get("treatment_hands")==20000000 and w.get("no_extension") is True and w.get("no_second_seed") is True and w.get("no_later_endpoint") is True
    c["no_partial_reuse"]=w.get("terminal_partial_reuse")=="FORBIDDEN"
    gates=dec["mandatory_prelaunch_control_plane_gate"]; gt=" ".join(gates).lower()
    c["seven_gates"]=len(gates)==7
    c["all_child_roles"]=all(role in gt for role in ("health","protocol","endpoint","treatment-launch","completion"))
    c["exact_binding"]="expected script" in gt and "parent relationship" in gt and "design-lock identity" in gt
    c["adversarial"]="unregistered sibling" in gt and "command mismatch" in gt
    c["old_guards_retained"]="startup-log pending" in gt and "rearm nonzero" in gt and "launcher exit-plus-survival" in gt
    c["orphans_gate"]="zero dead-parent python" in gt
    c["path1_gate"]="coordinator23720" in gt and "exactly six belownormal cpu workers" in gt
    c["full_prelaunch"]="production perf-cal" in gt and "canonical ordered rearm" in gt
    cd=d["candidate_dispositions"]
    c["no_h13_repair"]=cd.get("resume_or_repair_h13")=="FORBIDDEN_TERMINAL"
    c["no_false_method_fail"]="ZERO_SCIENTIFIC_EXPOSURE" in cd.get("declare_smoothl1_method_fail","")
    c["no_action_regret_tune"]="NO_COUNTERFACTUAL" in cd.get("tune_postflop_aggression","")
    c["no_launch_authority"]=d.get("behavior_launch_authorized","").startswith("NONE_UNTIL_H14_")
    c["official_zero"]=d.get("official_hands_authorized")==0
    c["no_strength"]=d.get("strength_claim")=="FORBIDDEN"
    failed=sorted(k for k,v in c.items() if not v)
    out={"schema_version":"v5.hybrid.route_review.audit.v10.v1","checked_at":datetime.now(timezone.utc).isoformat(),"result_sha256":sha(R),"checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"overall":"PASS" if not failed else "FAIL_CLOSED","selected_next":dec.get("selected_next") if not failed else None,"route_exhausted":dec.get("route_exhausted") if not failed else None,"behavior_launch_authority":"NONE_REVIEW_AUDIT_ONLY","official_hands":0,"strength_claim":"FORBIDDEN"}
    OUT.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8"); print(json.dumps(out,indent=2,sort_keys=True)); return 0 if not failed else 1

if __name__=="__main__": raise SystemExit(main())
