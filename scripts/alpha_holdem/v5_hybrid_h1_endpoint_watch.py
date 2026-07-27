#!/usr/bin/env python3
"""Fail-closed H1 arm endpoint freezer; never launches evaluation or training."""
from __future__ import annotations
import argparse, hashlib, json, os, shutil, time
from datetime import datetime, timezone
from pathlib import Path
import psutil, torch
from v5_assignment_provenance_audit import audit as audit_provenance

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text(encoding='utf-8-sig'))
 except Exception:return {}
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def errors(actual,expected):
 out=[]; design_only={'assignment_provenance_schema'}
 for k,v in expected.items():
  if k in design_only: continue
  g=actual.get(k)
  if isinstance(v,float) and isinstance(g,(int,float)): ok=abs(float(g)-v)<=1e-12
  else:ok=g==v
  if not ok:out.append(f'config {k}: actual={g!r} expected={v!r}')
 return out
def main():
 p=argparse.ArgumentParser();p.add_argument('--arm',choices=['control','treatment'],required=True);p.add_argument('--design-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--status-json',required=True);p.add_argument('--poll-seconds',type=int,default=30);p.add_argument('--endpoint-readiness-timeout-seconds',type=int,default=180);p.add_argument('--validate-only',action='store_true');a=p.parse_args()
 lockp=Path(a.design_lock).resolve(); lock=load(lockp); arm=lock.get('arms',{}).get(a.arm,{}); rd=Path(arm.get('run_dir','')); st=Path(a.status_json); static=[]
 if sha(lockp)!=a.expected_lock_sha256.lower():static+=['lock SHA mismatch']
 if lock.get('design_id')!='H1' or lock.get('status')!='LOCKED':static+=['lock identity/status']
 if not arm or lock.get('arm_budget',{}).get('minimum_endpoint_hands')!=535989661:static+=['arm/budget incomplete']
 if static:write(st,{'overall':'FAIL','state':'STATIC_CONTRACT_FAILURE','errors':static});return 1
 if a.validate_only:write(st,{'overall':'PASS','state':'VALIDATE_ONLY_STATIC_CONTRACT_PASS','arm':a.arm});return 0
 readiness_deadline=None
 while True:
  m=load(rd/'run_manifest.json')
  if not m:write(st,{'overall':'PENDING','state':'WAITING_FOR_ARM'});time.sleep(max(1,a.poll_seconds));continue
  e=errors(m.get('config',{}),arm['expected_config'])
  if m.get('run_id')!=arm['run_id']:e+=['run_id mismatch']
  if e:write(st,{'overall':'FAIL','state':'ARM_IDENTITY_FAILURE','errors':e});return 1
  if m.get('status') in ['initialized','running']:
   pid=int(m.get('process_id',-1)); cmd=''
   try:cmd=' '.join(psutil.Process(pid).cmdline())
   except Exception:pass
   live=Path('scripts/alpha_holdem/train_v5.py'); trainer_ok=('train_v5_hybrid_h1.py' in cmd) or ('train_v5.py' in cmd and live.exists() and sha(live)==lock.get('trainer_sha256'))
   if arm['run_id'] not in cmd or not trainer_ok:write(st,{'overall':'FAIL','state':'PROCESS_IDENTITY_FAILURE'});return 1
   write(st,{'overall':'PENDING','state':'ARM_RUNNING','pid':pid,'hands':m.get('total_hands')});time.sleep(max(1,a.poll_seconds));continue
  if m.get('status')!='finished':write(st,{'overall':'FAIL','state':'UNEXPECTED_STATUS','manifest_status':m.get('status')});return 1
  cp=rd/'latest.pt'
  if not cp.exists():write(st,{'overall':'FAIL','state':'ENDPOINT_MISSING'});return 1
  c=torch.load(cp,map_location='cpu',weights_only=False); h=int(c.get('total_hands',-1)); it=int(c.get('iteration',-1)); min_h=lock['arm_budget']['minimum_endpoint_hands']; max_o=lock['arm_budget']['maximum_single_arm_overshoot_hands']; e=[]
  if not min_h<=h<=min_h+max_o:e+=['endpoint hands outside locked range']
  if c.get('critic_contract')!=arm['expected_config']['critic_contract'] or c.get('value_coef')!=arm['expected_config']['value_coef']:e+=['critic checkpoint contract mismatch']
  if os.path.normcase(os.path.abspath(str(m.get('lineage_parent_checkpoint',''))))!=os.path.normcase(os.path.abspath(lock['source_checkpoint']['path'])):e+=['lineage mismatch']
  if e:write(st,{'overall':'FAIL','state':'ENDPOINT_IDENTITY_FAILURE','errors':e});return 1
  health=load(rd/'health_status.json'); latest=health.get('latest',{}); readiness=[]
  if health.get('overall')!='PASS' or int(latest.get('iteration',-1))!=it or int(latest.get('hands',-1))!=h:readiness+=['exact endpoint health PASS missing']
  err=rd/'console.err.log'
  if not err.exists() or err.stat().st_size:readiness+=['stderr missing/nonempty']
  try:prov=audit_provenance(Path(arm['provenance_path']),expected_run_id=arm['run_id'],expected_mode='per-iteration',expected_workers=22,expected_groups=5,expected_worker_seed_base=73000,expected_first_iteration=31401,expected_last_iteration=it)
  except Exception as exc:prov={'overall':'FAIL','errors':[str(exc)]}
  write(rd/f'h1_{a.arm}_assignment_provenance_audit.json',prov)
  if prov.get('overall')!='PASS':readiness+=['provenance audit failed']
  if readiness:
   if readiness_deadline is None:readiness_deadline=time.monotonic()+max(0,a.endpoint_readiness_timeout_seconds)
   if time.monotonic()<readiness_deadline:
    write(st,{'overall':'PENDING','state':'WAITING_FOR_EXACT_ENDPOINT_ARTIFACTS','errors':readiness,'deadline_monotonic':readiness_deadline});time.sleep(max(1,a.poll_seconds));continue
   write(st,{'overall':'FAIL','state':'ENDPOINT_AUDIT_TIMEOUT','errors':readiness});return 1
  frozen=rd/f'h1_{a.arm}_endpoint.pt'
  if frozen.exists():write(st,{'overall':'FAIL','state':'FROZEN_ENDPOINT_ALREADY_EXISTS'});return 1
  shutil.copy2(cp,frozen)
  if sha(cp)!=sha(frozen):frozen.unlink(missing_ok=True);write(st,{'overall':'FAIL','state':'COPY_HASH_FAILURE'});return 1
  write(st,{'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS','state':'ARM_ENDPOINT_FROZEN','arm':a.arm,'run_id':arm['run_id'],'iteration':it,'hands':h,'checkpoint_path':str(frozen.resolve()),'checkpoint_sha256':sha(frozen),'design_lock_sha256':sha(lockp),'slumbot_authority':'NONE'});return 0
if __name__=='__main__':raise SystemExit(main())