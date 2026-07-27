#!/usr/bin/env python3
"""Execute the immutable trainerless PCV005 engineering gate."""
from __future__ import annotations
import argparse,hashlib,json,math,statistics,sys
from datetime import datetime,timezone
from pathlib import Path
from typing import Any
import numpy as np
import torch
import torch.nn.functional as F

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"scripts/alpha_holdem"))
from v5_hybrid_h16_perf_cal import (active_forbidden_processes,deterministic_transitions,one_full_update,path1_identity,sha256,transition_sha256)  # noqa:E402

PREREG_SHA="59b1828596af695ad46fbfb84e80af813fca480d86bcc62eeb1bd6835f4a00b4"
SOURCE_SHA="96a007039b0baa29f0c39b0bd7adc67d8ca0733a41a261203f52430e60b5ca13"

def load(p:Path)->dict[str,Any]:return json.loads(p.read_text(encoding="utf-8-sig"))
def atomic(p:Path,v:dict[str,Any])->None:
 if p.exists():raise FileExistsError(p)
 p.write_text(json.dumps(v,indent=2,sort_keys=True)+"\n",encoding="utf-8")
def maxdiff(a:torch.Tensor,b:torch.Tensor)->float:return float((a-b).abs().max().item())

def equivalence(seed:int,shapes:list[list[int]],device:str)->dict[str,Any]:
 rows=[]
 for shape in shapes:
  g=torch.Generator(device=device);g.manual_seed(seed+int(np.prod(shape)))
  base=torch.randn(*shape,generator=g,device=device)*100.0
  target=torch.randn(*shape,generator=g,device=device)*100.0
  x1=base.clone().requires_grad_(True);x2=base.clone().requires_grad_(True)
  l1=F.smooth_l1_loss(x1,target,beta=1.0);l2=F.huber_loss(x2,target,delta=1.0)
  l1.backward();l2.backward()
  p1=torch.nn.Parameter(base.clone());p2=torch.nn.Parameter(base.clone())
  o1=torch.optim.Adam([p1],lr=3e-4);o2=torch.optim.Adam([p2],lr=3e-4)
  a=F.smooth_l1_loss(p1,target,beta=1.0);b=F.huber_loss(p2,target,delta=1.0)
  o1.zero_grad();o2.zero_grad();a.backward();b.backward();o1.step();o2.step()
  state_diffs=[]
  for key in ("exp_avg","exp_avg_sq"):
   state_diffs.append(maxdiff(o1.state[p1][key],o2.state[p2][key]))
  rows.append({"shape":shape,"forward_max_abs":abs(float(l1.item())-float(l2.item())),"gradient_max_abs":maxdiff(x1.grad,x2.grad),"adam_parameter_max_abs":maxdiff(p1,p2),"adam_state_max_abs":max(state_diffs),"finite":all(math.isfinite(x) for x in (float(l1.item()),float(l2.item()),*state_diffs))})
 return {"seed":seed,"rows":rows}

def shifted_transitions(checkpoint:dict[str,Any],device:str,seed:int,rows:int)->list[tuple]:
 source=deterministic_transitions(checkpoint,device,seed,rows)
 shifted=[]
 for t in source:
  row=list(t);row[5]=float(row[5])+9.9;shifted.append(tuple(row))
 return shifted

def shape_ok(stats:dict[str,Any])->bool:
 return bool(stats["kl_early_stop_triggered"]) and int(stats["ppo_epochs_completed"])==1 and int(stats["value_head_catchup_epochs"])==3 and bool(stats["value_head_catchup_actor_state_unchanged"])

def main()->int:
 p=argparse.ArgumentParser();p.add_argument("--preregistration",type=Path,required=True);p.add_argument("--source",type=Path,required=True);p.add_argument("--path1-pid",type=int,default=23720);p.add_argument("--out",type=Path,required=True);a=p.parse_args()
 try:
  if sha256(a.preregistration)!=PREREG_SHA or sha256(a.source)!=SOURCE_SHA:raise ValueError("prereg/source identity")
  d=load(a.preregistration);device="cuda";forbidden=active_forbidden_processes()
  if forbidden:raise ValueError(f"forbidden processes {forbidden}")
  path1=path1_identity(a.path1_pid,6);checkpoint=torch.load(a.source,map_location="cpu",weights_only=False)
  eq=[equivalence(seed,d["equivalence_gates"]["tensor_shapes"],device) for seed in d["equivalence_gates"]["seeds"]]
  eq_rows=[row for group in eq for row in group["rows"]];g=d["equivalence_gates"]
  eq_pass=all(row["forward_max_abs"]<=g["forward_max_abs_tolerance"] and row["gradient_max_abs"]<=g["gradient_max_abs_tolerance"] and row["adam_parameter_max_abs"]<=g["adam_parameter_max_abs_tolerance"] and row["adam_state_max_abs"]<=g["adam_state_max_abs_tolerance"] and row["finite"] for row in eq_rows)
  trigger=[]
  trigger_data=shifted_transitions(checkpoint,device,2026071949,4096)
  for seed in d["deterministic_trigger_proof"]["seeds"]:
   for mode in ("mse","smooth_l1","huber"):
    _,stats,_,_=one_full_update(checkpoint,trigger_data,device,mode,seed,1024,4,1e-12)
    trigger.append({"seed":seed,"mode":mode,"pass":shape_ok(stats),"ppo_epochs_completed":stats["ppo_epochs_completed"],"catchup_epochs":stats["value_head_catchup_epochs"],"approx_kl":stats["approx_kl"]})
  trigger_pass=all(x["pass"] for x in trigger)
  b=d["representative_benchmark"];data=shifted_transitions(checkpoint,device,b["seed"],b["rows"]);modes=("mse","smooth_l1","huber")
  for w in range(b["warmup_updates"]):
   for mode in (modes if w%2==0 else tuple(reversed(modes))):one_full_update(checkpoint,data,device,mode,b["seed"]+100000+w,b["mini_batch_size"],b["ppo_epochs"],b["target_kl"])
  raw={m:[] for m in modes}
  for rep in range(b["repeats"]):
   order=modes if rep%2==0 else tuple(reversed(modes))
   for mode in order:
    vals=[]
    for u in range(b["timed_updates"]):
     elapsed,stats,_,_=one_full_update(checkpoint,data,device,mode,b["seed"]+rep*100+u,b["mini_batch_size"],b["ppo_epochs"],b["target_kl"])
     if not shape_ok(stats):raise RuntimeError("PCV005 deterministic trigger violated during timing")
     vals.append(elapsed)
    raw[mode].append(vals)
  repeat={m:[float(statistics.median(v)) for v in raw[m]] for m in modes};med={m:float(statistics.median(repeat[m])) for m in modes}
  huber_smooth=med["smooth_l1"]/med["huber"];huber_mse=med["mse"]/med["huber"];stability=min(repeat["mse"])/max(repeat["mse"])
  gates={"trigger_pass":trigger_pass,"equivalence_pass":eq_pass,"huber_over_smooth_l1_ratio":huber_smooth,"huber_over_smooth_l1_pass":huber_smooth>=b["huber_over_smooth_l1_throughput_ratio_min"],"huber_over_mse_ratio":huber_mse,"huber_over_mse_pass":huber_mse>=b["huber_over_mse_full_update_throughput_ratio_min"],"mse_stability_ratio":stability,"mse_stability_pass":stability>=b["mse_repeat_stability_ratio_min"]}
  passed=all((gates["trigger_pass"],gates["equivalence_pass"],gates["huber_over_smooth_l1_pass"],gates["huber_over_mse_pass"],gates["mse_stability_pass"]))
  out={"schema_version":"v5.pcv005.result.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"PASS" if passed else "FAIL_CLOSED","classification":"PCV005_PASS" if passed else "PCV005_FAIL","preregistration_sha256":PREREG_SHA,"source":{"path":str(a.source.resolve()),"sha256":SOURCE_SHA,"iteration":checkpoint["iteration"],"hands":checkpoint["total_hands"]},"equivalence":{"results":eq,"pass":eq_pass},"trigger_proof":{"transition_sha256":transition_sha256(trigger_data),"results":trigger,"pass":trigger_pass},"benchmark":{"raw_seconds":raw,"repeat_median_seconds":repeat,"mode_median_seconds":med},"gates":gates,"path1":path1,"forbidden_processes":forbidden,"trainer_started":False,"checkpoint_written":False,"behavior_change":False,"official_hands":0,"strength_claim":"FORBIDDEN","tool_sha256":sha256(Path(__file__).resolve())}
  atomic(a.out,out);print(json.dumps(out,indent=2,sort_keys=True));return 0 if passed else 2
 except Exception as e:
  out={"schema_version":"v5.pcv005.result.v1","checked_at":datetime.now(timezone.utc).isoformat(),"overall":"FAIL_CLOSED","classification":"PCV005_EXECUTION_FAILURE","error":f"{type(e).__name__}: {e}","trainer_started":False,"checkpoint_written":False,"behavior_change":False,"official_hands":0,"strength_claim":"FORBIDDEN"}
  if not a.out.exists():atomic(a.out,out)
  print(json.dumps(out,indent=2,sort_keys=True),file=sys.stderr);return 2
if __name__=="__main__":raise SystemExit(main())
