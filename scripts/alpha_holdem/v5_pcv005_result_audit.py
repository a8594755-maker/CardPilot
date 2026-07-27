#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json,statistics
from datetime import datetime,timezone
from pathlib import Path
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def close(a,b,t=1e-10):return abs(float(a)-float(b))<=t
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--result",type=Path,required=True);p.add_argument("--preregistration",type=Path,required=True);p.add_argument("--tool",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=json.loads(a.result.read_text(encoding="utf-8-sig"));pr=json.loads(a.preregistration.read_text(encoding="utf-8-sig"));c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 ck("identity",d.get("classification")=="PCV005_FAIL" and d.get("overall")=="FAIL_CLOSED" and d.get("preregistration_sha256")==sha(a.preregistration)=="59b1828596af695ad46fbfb84e80af813fca480d86bcc62eeb1bd6835f4a00b4")
 ck("tool_hash",d.get("tool_sha256")==sha(a.tool));ck("source",d.get("source",{}).get("sha256")=="96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13" and d.get("source",{}).get("iteration")==35051 and d.get("source",{}).get("hands")==576021901)
 ck("trigger",d.get("trigger_proof",{}).get("pass") is True and len(d.get("trigger_proof",{}).get("results",[]))==24 and all(x.get("pass") and x.get("ppo_epochs_completed")==1 and x.get("catchup_epochs")==3 for x in d["trigger_proof"]["results"]))
 eq=d.get("equivalence",{});rows=[x for g in eq.get("results",[]) for x in g.get("rows",[])];g=pr["equivalence_gates"];ck("equivalence",eq.get("pass") is True and len(rows)==12 and all(x["forward_max_abs"]<=g["forward_max_abs_tolerance"] and x["gradient_max_abs"]<=g["gradient_max_abs_tolerance"] and x["adam_parameter_max_abs"]<=g["adam_parameter_max_abs_tolerance"] and x["adam_state_max_abs"]<=g["adam_state_max_abs_tolerance"] and x["finite"] for x in rows))
 raw=d["benchmark"]["raw_seconds"];repeat={m:[float(statistics.median(v)) for v in raw[m]] for m in ("mse","smooth_l1","huber")};med={m:float(statistics.median(repeat[m])) for m in repeat};hs=med["smooth_l1"]/med["huber"];hm=med["mse"]/med["huber"];st=min(repeat["mse"])/max(repeat["mse"]);rg=d["gates"]
 ck("sample_shape",all(len(raw[m])==5 and all(len(v)==8 for v in raw[m]) for m in raw));ck("medians",all(close(med[m],d["benchmark"]["mode_median_seconds"][m]) for m in med));ck("ratios",close(hs,rg["huber_over_smooth_l1_ratio"]) and close(hm,rg["huber_over_mse_ratio"]) and close(st,rg["mse_stability_ratio"]));ck("frozen_fail",hs<pr["representative_benchmark"]["huber_over_smooth_l1_throughput_ratio_min"] and rg["huber_over_smooth_l1_pass"] is False and rg["huber_over_mse_pass"] is True and rg["mse_stability_pass"] is True)
 ck("path1",d.get("path1",{}).get("coordinator_pid")==23720 and d.get("path1",{}).get("worker_count")==6 and d.get("path1",{}).get("changed") is False);ck("no_launch",d.get("trainer_started") is False and d.get("checkpoint_written") is False and d.get("behavior_change") is False and d.get("official_hands")==0)
 failed=sorted(k for k,v in c.items() if not v);o={"schema_version":"v5.pcv005.result_audit.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","classification":"PCV005_FAIL_CONFIRMED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"result_sha256":sha(a.result),"official_hands":0,"strength_claim":"FORBIDDEN"};
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(o,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
