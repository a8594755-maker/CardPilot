#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def load(p:Path)->dict:return json.loads(p.read_text(encoding="utf-8-sig"))
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--result",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=load(a.result);c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 ck("identity",d.get("design_id")=="HYBRID-ROUTE-REVIEW-013" and d.get("overall")=="PASS_ROUTE_REVIEW")
 pr=ROOT/"reports/v5_hybrid_route_review_013_preregistration_20260719.json";pa=ROOT/"reports/v5_hybrid_route_review_013_preregistration_audit_20260719.json"
 ck("prereg_hash",sha(pr)==d.get("registration_sha256"));ck("prereg_audit_hash",sha(pa)==d.get("registration_audit_sha256") and load(pa).get("overall")=="PASS")
 h=d.get("evidence_matrix",{}).get("h15",{});j=ROOT/"reports/v5_hybrid_h15_judgment_20260719.json";ta=ROOT/"reports/v5_hybrid_h15_prearm_terminal_audit_20260719.json"
 ck("h15_hashes",sha(j)==h.get("judgment_sha256") and sha(ta)==h.get("terminal_audit_sha256"));ck("h15_terminal",h.get("classification")=="H15_FAIL_PREARM_PERF_CAL_NO_LAUNCH" and h.get("trainer_started") is False and h.get("method_inference")=="NONE");ck("ratios",abs(h.get("loss_only_ratio")-0.9298062924031755)<1e-12 and h.get("loss_only_gate")==0.95 and h.get("end_to_end_arm_gate")==0.85)
 loc=d.get("evidence_matrix",{}).get("localization",{});ck("localization",loc.get("loss_only_overhead_supported") is True and loc.get("end_to_end_throughput_regression_supported") is False and loc.get("scientific_effect_supported") is False and loc.get("same_window_rerun")=="FORBIDDEN")
 cam=d.get("evidence_matrix",{}).get("campaign",{});ck("campaign",cam.get("clean_h11_source_available") is True and cam.get("external_debt_hands")==0 and cam.get("latest_official_level")=="L0" and cam.get("official_hands_this_review")==0 and cam.get("path1")=="UNCHANGED")
 dec=d.get("decision",{});ck("selected_h16",dec.get("selected_next")=="H16_REPRESENTATIVE_FULL_PPO_PERF_CAL_SAME_SCIENCE");ck("same_science","MSE_CONTROL_VS_SMOOTHL1_BETA1" in dec.get("h16_science",""));ck("representative_gate","FULL_PPO_UPDATE" in dec.get("h16_prearm","") and "0.85" in dec.get("h16_prearm",""));ck("arm_gate","FIRST60" in dec.get("h16_arm_throughput","") and "0.85" in dec.get("h16_arm_throughput",""));ck("fallback","H16_REPRESENTATIVE_PREARM_GATE_FAILS" in dec.get("pcv005_fallback",""));ck("route_open",dec.get("route_exhausted") is False);ck("registration_only",dec.get("authority")=="SEPARATE_H16_PREREGISTRATION_ONLY")
 ck("closures",d.get("closures",{}).get("h15_perf_cal")=="NO_RERUN_OR_RECLASSIFICATION");ck("no_official",d.get("official_hands")==0 and d.get("strength_claim")=="FORBIDDEN")
 failed=sorted(k for k,v in c.items() if not v);r={"schema_version":"v5.hybrid.route_review.result_audit.v13.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"result_sha256":sha(a.result),"official_hands":0};a.out.write_text(json.dumps(r,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(r,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
