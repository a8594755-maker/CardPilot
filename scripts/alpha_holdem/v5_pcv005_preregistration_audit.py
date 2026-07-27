#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
def sha(p:Path)->str:return hashlib.sha256(p.read_bytes()).hexdigest()
def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--preregistration",type=Path,required=True);p.add_argument("--out",type=Path,required=True);a=p.parse_args();d=json.loads(a.preregistration.read_text(encoding="utf-8-sig"));c={}
 def ck(n,x):c.__setitem__(n,bool(x))
 ck("identity",d.get("design_id")=="PCV005" and d.get("status")=="REGISTERED_TRAINERLESS_NO_LAUNCH")
 rr=d.get("route_review",{});ck("route",sha(ROOT/rr.get("result_path",""))==rr.get("result_sha256") and sha(ROOT/rr.get("audit_path",""))==rr.get("audit_sha256") and rr.get("route_exhausted") is False)
 s=d.get("source",{});sp=Path(s.get("checkpoint_path",""));ck("source",sp.is_file() and sha(sp)==s.get("checkpoint_sha256")=="96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13" and s.get("iteration")==35051 and s.get("hands")==576021901)
 e=d.get("engineering_candidate",{});ck("candidate",e.get("baseline","").startswith("torch.nn.functional.smooth_l1_loss") and e.get("candidate","").startswith("torch.nn.functional.huber_loss") and e.get("scope")=="VALUE_HEAD_CATCHUP_ONLY" and e.get("behavior_change") is False)
 t=d.get("deterministic_trigger_proof",{});ck("trigger",t.get("rows")==4096 and t.get("mini_batch_size")==1024 and t.get("ppo_epochs")==4 and t.get("target_kl")==1e-12 and t.get("old_log_prob_offset")==10.0 and len(t.get("seeds",[]))==8)
 eqa=d.get("equivalence_gates",{});ck("equivalence",eqa.get("forward_max_abs_tolerance")==1e-7 and eqa.get("gradient_max_abs_tolerance")==1e-7 and eqa.get("adam_parameter_max_abs_tolerance")==1e-7 and eqa.get("adam_state_max_abs_tolerance")==1e-7 and len(eqa.get("seeds",[]))==4)
 b=d.get("representative_benchmark",{});ck("benchmark",b.get("rows")==4096 and b.get("warmup_updates")==2 and b.get("timed_updates")==8 and b.get("repeats")==5 and b.get("huber_over_smooth_l1_throughput_ratio_min")==1.0 and b.get("huber_over_mse_full_update_throughput_ratio_min")==0.85 and b.get("mse_repeat_stability_ratio_min")==0.95)
 con=d.get("constraints",{});ck("no_launch",con.get("trainer_launch") is False and con.get("checkpoint_write") is False and con.get("h16_rerun") is False and con.get("official_hands")==0)
 failed=sorted(k for k,v in c.items() if not v);o={"schema_version":"v5.pcv005.preregistration_audit.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if not failed else "FAIL_CLOSED","checks":c,"checks_passed":sum(c.values()),"checks_total":len(c),"failed":failed,"preregistration_sha256":sha(a.preregistration),"authority":"NONE_AUDIT_ONLY","official_hands":0};
 if a.out.exists():raise FileExistsError(a.out)
 a.out.write_text(json.dumps(o,indent=2,sort_keys=True)+"\n",encoding="utf-8");print(json.dumps(o,indent=2,sort_keys=True));return 0 if not failed else 2
if __name__=="__main__":raise SystemExit(main())
