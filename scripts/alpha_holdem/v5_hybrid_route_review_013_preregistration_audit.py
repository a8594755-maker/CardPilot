#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p:Path)->dict:return json.loads(p.read_text(encoding="utf-8-sig"))
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--preregistration",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=load(a.preregistration);c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-013" and d.get("status")=="REGISTERED_REPORTING_ONLY")
 t=d.get("trigger",{});ck("h15_terminal",t.get("h15_classification")=="H15_FAIL_PREARM_PERF_CAL_NO_LAUNCH" and t.get("trainer_started") is False and t.get("method_evidence")=="NONE_NO_ARM_LAUNCHED")
 j=ROOT/"reports/v5_hybrid_h15_judgment_20260719.json";ta=ROOT/"reports/v5_hybrid_h15_prearm_terminal_audit_20260719.json"
 ck("judgment_hash",sha(j)==t.get("h15_judgment_sha256"));ck("terminal_audit_hash",sha(ta)==t.get("h15_terminal_audit_sha256") and load(ta).get("overall")=="PASS")
 ck("ratio",abs(float(t.get("observed_loss_only_ratio",0))-0.9298062924031755)<1e-12 and t.get("registered_loss_only_minimum")==0.95)
 f=d.get("frozen_truth",{});ck("terminal_history",all("TERMINAL" in f.get(k,"") for k in ("h12","h13","h14","h15")));ck("clean_source","ITER35051_HANDS576021901" in f.get("clean_source","") and "SHA96A007" in f.get("clean_source",""));ck("official_l0",f.get("latest_official_level")=="L0" and f.get("official_hands_this_review")==0);ck("external_debt",f.get("external_debt_hands")==0);ck("path1","UNTOUCHED" in f.get("path1",""))
 loc=d.get("causal_localization",{});ck("causal_scope","VALUE_HEAD_ONLY" in loc.get("supported","") and len(loc.get("not_supported",[]))==3 and "NOT_REPRESENTATIVE" in loc.get("measurement_issue",""))
 cand=d.get("candidate_order",[]);ck("candidate_count",len(cand)==3);ck("h16_first",cand[0].get("candidate")=="H16_REPRESENTATIVE_FULL_PPO_PERF_CAL_SAME_SCIENCE" and "0.85" in cand[0].get("required_prearm_gate",""));ck("pcv_second",cand[1].get("candidate")=="PCV005_NUMERICALLY_EQUIVALENT_SMOOTHL1_KERNEL_ENGINEERING_GATE");ck("route_last",cand[2].get("candidate")=="ROUTE_EXHAUSTION")
 ck("decision_rule","SELECT_H16" in d.get("decision_rule","") and "OTHERWISE_SELECT_PCV005" in d.get("decision_rule", ""));co=d.get("constraints",{});ck("closures",co.get("h15_rerun_resume_extend_reclassify")=="FORBIDDEN");ck("single_variable",co.get("single_behavior_variable") is True);ck("identity_bound",co.get("exact_checkpoint_identity") is True);ck("no_official",co.get("official_hands")==0 and co.get("strength_claim")=="FORBIDDEN");ck("no_action_tuning",co.get("action_tuning")=="FORBIDDEN");ck("reporting_only",d.get("authority")=="REPORTING_ONLY_NO_BEHAVIOR_LAUNCH")
 failed=sorted(k for k,v in c.items() if not v);r={"schema_version":"v5.hybrid.route_review.preregistration_audit.v13.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"preregistration_sha256":sha(a.preregistration),"official_hands":0};a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(r,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
