#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--artifact",type=Path,required=True);p.add_argument("--kind",choices=("registration","result"),required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=json.loads(a.artifact.read_text(encoding="utf-8-sig"));c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 if a.kind=="registration":
  ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-015" and d.get("status")=="REGISTERED_REPORTING_ONLY");t=d.get("trigger",{});ck("trigger",t.get("pcv005_result_sha256")==sha(ROOT/"reports/v5_pcv005_result_20260719.json") and t.get("pcv005_audit_sha256")==sha(ROOT/"reports/v5_pcv005_result_audit_20260719.json") and t.get("consecutive_no_progress_windows")==2)
  e=d.get("evidence_boundary",{});v=e.get("valid_supporting_components",{});ck("components",v.get("deterministic_trigger_proof").startswith("PASS_24") and v.get("smooth_l1_huber_equivalence")=="PASS" and v.get("smooth_l1_over_mse_full_update_ratio")>=v.get("smooth_l1_over_mse_registered_floor") and v.get("mse_stability_ratio")>=0.95);ck("primary_fail","0.9948549347" in e.get("primary_pcv005_fail","") and len(e.get("not_supported",[]))==3)
  cand=d.get("candidate_order",[]);ck("candidates",len(cand)==3 and cand[0].get("candidate").startswith("H17_CORRECTED_DETERMINISTIC_TRIGGER") and cand[1].get("candidate")=="HYBRID_VALUE_TARGET_ROUTE_REVIEW" and cand[2].get("candidate")=="ROUTE_EXHAUSTION");ck("decision","DO_NOT_ADOPT_HUBER" in d.get("decision_rule","") and "OFFSET10_TRIGGER_STABILITY" in d.get("decision_rule",""));ck("constraints",d.get("constraints",{}).get("h16_and_pcv005_terminal") is True and d.get("constraints",{}).get("same_window_rerun") is False and d.get("constraints",{}).get("official_hands")==0)
 else:
  ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-015" and d.get("overall")=="PASS_ROUTE_REVIEW");ck("registration",d.get("registration_sha256")==sha(ROOT/"reports/v5_hybrid_route_review_015_preregistration_20260719.json"));dec=d.get("decision",{});ck("selection",dec.get("selected_next").startswith("H17_CORRECTED_DETERMINISTIC_TRIGGER") and dec.get("adopt_huber") is False and dec.get("route_exhausted") is False and dec.get("authority")=="SEPARATE_H17_PREREGISTRATION_ONLY");ck("evidence",d.get("evidence_matrix",{}).get("pcv005",{}).get("primary_verdict")=="FAIL" and d.get("evidence_matrix",{}).get("pcv005",{}).get("trigger_component")=="PASS" and d.get("evidence_matrix",{}).get("pcv005",{}).get("original_smooth_l1_full_update_gate")=="PASS");ck("closures",d.get("closures",{}).get("h16_pcv005")=="TERMINAL_NO_REOPEN");ck("no_official",d.get("official_hands")==0 and d.get("strength_claim")=="FORBIDDEN")
 failed=sorted(k for k,v in c.items() if not v);o={"schema_version":f"v5.hybrid.route_review.015.{a.kind}_audit.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"artifact_sha256":sha(a.artifact),"official_hands":0};
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(o,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
