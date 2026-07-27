#!/usr/bin/env python3
"""Exact registered H1 endpoint judgment; no official evaluation and no launch."""
from __future__ import annotations
import argparse, hashlib, json, statistics, subprocess, sys
from datetime import datetime
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def rows(p):
 out=[]
 for line in Path(p).read_text(encoding='utf-8').splitlines():
  if line.strip():out.append(json.loads(line))
 return out
def effective(xs,n=None):
 ys=xs[:n] if n else xs
 if len(ys)<2:return None
 dt=(datetime.fromisoformat(ys[-1]['recorded_at'])-datetime.fromisoformat(ys[0]['recorded_at'])).total_seconds()
 return (int(ys[-1]['hands'])-int(ys[0]['hands']))/dt if dt>0 else None
def main():
 p=argparse.ArgumentParser();p.add_argument('--design-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--control-status',required=True);p.add_argument('--treatment-status',required=True);p.add_argument('--out-json',required=True);p.add_argument('--device',choices=['cpu','cuda'],default='cuda');a=p.parse_args()
 lockp=Path(a.design_lock); lock=json.loads(lockp.read_text(encoding='utf-8')); errors=[]
 if sha(lockp)!=a.expected_lock_sha256.lower():errors+=['lock SHA mismatch']
 status=[]
 for arm,path in [('control',a.control_status),('treatment',a.treatment_status)]:
  s=json.loads(Path(path).read_text(encoding='utf-8')); status.append(s)
  if s.get('overall')!='PASS' or s.get('state')!='ARM_ENDPOINT_FROZEN' or s.get('arm')!=arm:errors+=[f'{arm} endpoint status invalid']
  elif sha(Path(s['checkpoint_path']))!=s['checkpoint_sha256']:errors+=[f'{arm} endpoint hash mismatch']
 if errors:
  out={'schema_version':'v5.hybrid.h1.judgment.v1','overall':'INCONCLUSIVE','errors':errors,'official_hands':0};Path(a.out_json).write_text(json.dumps(out,indent=2)+'\n');print(json.dumps(out,indent=2));return 1
 cal=lock['calibration']['path']; cmpout=Path(a.out_json).with_name(Path(a.out_json).stem+'_calibration.json')
 cp=[s['checkpoint_path'] for s in status]
 subprocess.run([sys.executable,'scripts/alpha_holdem/v5_h1_calibration.py','compare','--bundle-dir',cal,'--control',cp[0],'--treatment',cp[1],'--device',a.device,'--out-json',str(cmpout)],check=True)
 comp=json.loads(cmpout.read_text(encoding='utf-8')); crows=rows(Path(lock['arms']['control']['run_dir'])/'h1_training_metrics.jsonl'); trows=rows(Path(lock['arms']['treatment']['run_dir'])/'h1_training_metrics.jsonl')
 c60,t60=effective(crows,60),effective(trows,60); cf,tf=effective(crows),effective(trows); ratio60=t60/c60 if c60 and t60 else None; ratiofull=tf/cf if cf and tf else None
 ce=statistics.median(float(x['entropy']) for x in crows[-200:]);te=statistics.median(float(x['entropy']) for x in trows[-200:]); point=float(comp.get('relative_reduction',float('-inf'))); lower=float(comp.get('ci95_lower',float('-inf')))
 checks={'mse_point':point>=.15,'mse_ci_lower':lower>=.10,'throughput_first60':ratio60 is not None and ratio60>=.85,'throughput_full':ratiofull is not None and ratiofull>=.85,'entropy_floor':te>=.3,'entropy_noninferior':te>=ce-.10}
 guard_names=['throughput_first60','throughput_full','entropy_floor','entropy_noninferior']
 verdict=('FAIL' if not all(checks[n] for n in guard_names) or comp.get('status')=='FAIL_VALUE_GATE' else ('PASS' if comp.get('status')=='PASS_VALUE_GATE' else 'INCONCLUSIVE'))
 out={'schema_version':'v5.hybrid.h1.judgment.v1','overall':verdict,'checks':checks,'calibration_comparison':str(cmpout.resolve()),'mse_relative_reduction':point,'mse_bootstrap_ci_lower':lower,'control_effective_hps_first60':c60,'treatment_effective_hps_first60':t60,'throughput_ratio_first60':ratio60,'throughput_ratio_full':ratiofull,'control_entropy_median_last200':ce,'treatment_entropy_median_last200':te,'official_hands':0,'strength_claim':'FORBIDDEN'}
 Path(a.out_json).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps(out,indent=2));return 0
if __name__=='__main__':raise SystemExit(main())