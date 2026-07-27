#!/usr/bin/env python3
"""Fail-closed H2 endpoint freezer. Never launches training or evaluation."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, time
from datetime import datetime, timezone
from pathlib import Path
import psutil, torch
from v5_assignment_provenance_audit import audit as audit_provenance

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text(encoding='utf-8-sig'))
 except Exception:return {}
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def main():
 p=argparse.ArgumentParser();p.add_argument('--arm',choices=['control','treatment'],required=True);p.add_argument('--design-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--status-json',required=True);p.add_argument('--poll-seconds',type=int,default=30);p.add_argument('--endpoint-readiness-timeout-seconds',type=int,default=300);p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 lockp=Path(a.design_lock).resolve();lock=load(lockp);arm=lock.get('arms',{}).get(a.arm,{});rd=Path(arm.get('run_dir',''));st=Path(a.status_json);e=[]
 if not lockp.is_file() or sha(lockp)!=a.expected_lock_sha256.lower():e+=['lock SHA mismatch']
 if lock.get('design_id')!='H2' or lock.get('status')!='LOCKED':e+=['lock identity/status']
 if not arm or lock.get('arm_budget',{}).get('minimum_endpoint_hands')!=535989661:e+=['arm/budget incomplete']
 if e:write(st,{'overall':'FAIL','state':'STATIC_CONTRACT_FAILURE','errors':e});return 1
 if a.validate_only:write(st,{'overall':'PASS','state':'VALIDATE_ONLY_STATIC_CONTRACT_PASS','arm':a.arm});return 0
 deadline=None
 while True:
  m=load(rd/'run_manifest.json')
  if not m:write(st,{'overall':'PENDING','state':'WAITING_FOR_ARM'});time.sleep(max(1,a.poll_seconds));continue
  c=m.get('config',{});common=lock['common_config'];e=[]
  expected={**common,**{k:v for k,v in arm.items() if k in ('h2_window_arm','showdown_ev_value_targets','showdown_ev_value_target_max_runouts','showdown_ev_value_target_seed')}}
  design_only={'resume'}
  aliases={'allin_runout_ev_max_runouts':'allin_runout_ev_max_runouts'}
  for k,v in expected.items():
   if k in design_only:continue
   actual=c.get(aliases.get(k,k))
   if isinstance(v,float) and isinstance(actual,(int,float)):ok=abs(float(actual)-v)<=1e-12
   else:ok=actual==v
   if not ok:e.append(f'config {k}: actual={actual!r} expected={v!r}')
  if m.get('run_id')!=arm['run_id']:e+=['run_id mismatch']
  if e:write(st,{'overall':'FAIL','state':'ARM_IDENTITY_FAILURE','errors':e});return 1
  if m.get('status') in ('initialized','running'):
   pid=int(m.get('process_id',-1));cmd=''
   try:cmd=' '.join(psutil.Process(pid).cmdline())
   except Exception:pass
   if arm['run_id'] not in cmd or 'train_v5.py' not in cmd:write(st,{'overall':'FAIL','state':'PROCESS_IDENTITY_FAILURE'});return 1
   write(st,{'overall':'PENDING','state':'ARM_RUNNING','pid':pid,'hands':m.get('total_hands')});time.sleep(max(1,a.poll_seconds));continue
  if m.get('status')!='finished':write(st,{'overall':'FAIL','state':'UNEXPECTED_STATUS','manifest_status':m.get('status')});return 1
  cp=rd/'latest.pt'
  if not cp.exists():write(st,{'overall':'FAIL','state':'ENDPOINT_MISSING'});return 1
  x=torch.load(cp,map_location='cpu',weights_only=False);h=int(x.get('total_hands',-1));it=int(x.get('iteration',-1));lo=lock['arm_budget']['minimum_endpoint_hands'];hi=lo+lock['arm_budget']['maximum_overshoot_hands'];e=[]
  if not lo<=h<=hi:e+=['endpoint hands outside locked range']
  if x.get('h2_window_arm')!=a.arm or bool(x.get('h2_showdown_ev_value_targets'))!=(a.arm=='treatment'):e+=['checkpoint H2 arm contract mismatch']
  if os.path.normcase(os.path.abspath(str(m.get('lineage_parent_checkpoint',''))))!=os.path.normcase(os.path.abspath(lock['source']['path'])):e+=['lineage mismatch']
  if e:write(st,{'overall':'FAIL','state':'ENDPOINT_IDENTITY_FAILURE','errors':e});return 1
  health=load(rd/'health_status.json');latest=health.get('latest',{});ready=[]
  if health.get('overall')!='PASS' or int(latest.get('iteration',-1))!=it or int(latest.get('hands',-1))!=h:ready+=['exact endpoint health PASS missing']
  err=rd/'console.err.log'
  if not err.exists() or err.stat().st_size:ready+=['stderr missing/nonempty']
  try:prov=audit_provenance(Path(arm['provenance_path']),expected_run_id=arm['run_id'],expected_mode='per-iteration',expected_workers=22,expected_groups=5,expected_worker_seed_base=73000,expected_first_iteration=31401,expected_last_iteration=it)
  except Exception as exc:prov={'overall':'FAIL','errors':[str(exc)]}
  write(rd/f'h2_{a.arm}_assignment_provenance_audit.json',prov)
  if prov.get('overall')!='PASS':ready+=['provenance audit failed']
  if ready:
   if deadline is None:deadline=time.monotonic()+a.endpoint_readiness_timeout_seconds
   if time.monotonic()<deadline:write(st,{'overall':'PENDING','state':'WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS','errors':ready});time.sleep(max(1,a.poll_seconds));continue
   write(st,{'overall':'FAIL','state':'ENDPOINT_AUDIT_TIMEOUT','errors':ready});return 1
  frozen=rd/f'h2_{a.arm}_endpoint.pt'
  if frozen.exists():write(st,{'overall':'FAIL','state':'FROZEN_ENDPOINT_ALREADY_EXISTS'});return 1
  shutil.copy2(cp,frozen)
  if sha(cp)!=sha(frozen):frozen.unlink(missing_ok=True);write(st,{'overall':'FAIL','state':'COPY_HASH_FAILURE'});return 1
  write(st,{'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS','state':'ARM_ENDPOINT_FROZEN','arm':a.arm,'run_id':arm['run_id'],'iteration':it,'hands':h,'checkpoint_path':str(frozen.resolve()),'checkpoint_sha256':sha(frozen),'design_lock_sha256':sha(lockp),'slumbot_authority':'NONE'});return 0
if __name__=='__main__':raise SystemExit(main())
