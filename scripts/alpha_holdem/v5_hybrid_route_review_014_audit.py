#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p:Path)->dict:return json.loads(p.read_text(encoding="utf-8-sig"))
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--artifact",type=Path,required=True);p.add_argument("--kind",choices=("registration","result"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=load(a.artifact);c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 if a.kind=="registration":
  ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-014" and d.get("status")=="REGISTERED_REPORTING_ONLY")
  t=d.get("trigger",{});ck("trigger",t.get("h16_classification")=="H16_FAIL_PREARM_REPRESENTATIVE_PERF_CAL_EXECUTION_NO_LAUNCH" and t.get("h16_judgment_sha256")=="96e0a4bea8c119c991ad1cd2710e7897d7938a161451e7cf7fec65400a8c86d0" and t.get("h16_terminal_audit_sha256")=="3076c88f1e136cec92a15455cda19ff7241d882f62f65cf9b504c2c369b13ec9" and t.get("trainer_started") is False and t.get("valid_timing_sample") is False)
  ck("trigger_hashes",sha(ROOT/"reports/v5_hybrid_h16_judgment_20260719.json")==t.get("h16_judgment_sha256") and sha(ROOT/"reports/v5_hybrid_h16_prearm_terminal_audit_20260719.json")==t.get("h16_terminal_audit_sha256"))
  loc=d.get("causal_localization",{});ck("causal_boundary","OFFSET_DID_NOT GUARANTEE" in loc.get("supported","") and len(loc.get("not_supported",[]))==3 and loc.get("h16_same_window_repair")=="FORBIDDEN")
  candidates=d.get("candidate_order",[]);ck("candidate_order",len(candidates)==3 and candidates[0].get("candidate")=="PCV005_NUMERICALLY_EQUIVALENT_SMOOTHL1_KERNEL_ENGINEERING_GATE" and candidates[1].get("candidate")=="ROUTE_REVIEW_015" and candidates[2].get("candidate")=="ROUTE_EXHAUSTION")
  ck("pcv005_gates",all(token in candidates[0].get("required","") for token in ("DETERMINISTIC_FORCED_KL_TRIGGER_PROOF","EXACT_FORWARD_GRADIENT_OPTIMIZER_EQUIVALENCE","THROUGHPUT_RATIO_AT_LEAST_0.85","MSE_STABILITY_AT_LEAST_0.95")))
  ck("decision_rule","H16_REGISTRATION_EXPLICITLY_FROZE_IT_AS_THE_FALLBACK" in d.get("decision_rule",""))
  con=d.get("constraints",{});ck("no_behavior",con.get("behavior_change") is False and con.get("trainer_launch") is False and con.get("official_hands")==0 and con.get("h16_rerun_resume_extend_reclassify")=="FORBIDDEN")
 else:
  ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-014" and d.get("overall")=="PASS_ROUTE_REVIEW")
  ck("registration",d.get("registration_sha256")=="b2d35078a706971face669befd100b4780225dc204c53b24cf797e2a6f72460c" and sha(ROOT/"reports/v5_hybrid_route_review_014_preregistration_20260719.json")==d.get("registration_sha256"))
  e=d.get("evidence_matrix",{});ck("h16_terminal",e.get("h16",{}).get("valid_timing_sample") is False and e.get("h16",{}).get("method_inference")=="NONE" and e.get("h16",{}).get("trainer_started") is False)
  dec=d.get("decision",{});ck("selection",dec.get("selected_next")=="PCV005_NUMERICALLY_EQUIVALENT_SMOOTHL1_KERNEL_ENGINEERING_GATE" and dec.get("route_exhausted") is False and dec.get("authority")=="SEPARATE_PCV005_PREREGISTRATION_ONLY")
  ck("closures",d.get("closures",{}).get("h16")=="TERMINAL_NO_REOPEN")
  ck("no_official",d.get("official_hands")==0 and d.get("strength_claim")=="FORBIDDEN")
 failed=sorted(k for k,v in c.items() if not v);out={"schema_version":f"v5.hybrid.route_review.014.{a.kind}_audit.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"artifact_sha256":sha(a.artifact),"official_hands":0,"strength_claim":"FORBIDDEN"};
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(out,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(out,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
