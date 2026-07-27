#!/usr/bin/env python3
"""H2 registered first60-throughput and sustained-entropy abort watcher."""
from __future__ import annotations
import argparse,hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
import psutil

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def load(p):
 try:return json.loads(Path(p).read_text(encoding='utf-8-sig'))
 except Exception:return {}
def rows(p):
 try:
  with Path(p).open(encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]
 except Exception:return []
def write(p,x):Path(p).write_text(json.dumps(x,indent=2,sort_keys=True)+'\n',encoding='utf-8')
def effective(xs):
 ys=xs[1:61]
 if len(ys)<60:return None
 dt=(datetime.fromisoformat(ys[-1]['recorded_at'])-datetime.fromisoformat(ys[0]['recorded_at'])).total_seconds()
 return (int(ys[-1]['hands'])-int(ys[0]['hands']))/dt if dt>0 else None
def stop(pid):
 try:
  p=psutil.Process(pid);p.terminate();p.wait(20);return 'TERMINATED'
 except psutil.TimeoutExpired:
  p.kill();p.wait(10);return 'KILLED_AFTER_TIMEOUT'
 except psutil.NoSuchProcess:return 'ALREADY_EXITED'
def main():
 p=argparse.ArgumentParser();p.add_argument('--arm',choices=['control','treatment'],required=True);p.add_argument('--design-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--status-json',required=True);p.add_argument('--poll-seconds',type=int,default=15);a=p.parse_args();lp=Path(a.design_lock).resolve();st=Path(a.status_json);lock=load(lp);e=[]
 if not lp.is_file() or sha(lp)!=a.expected_lock_sha256.lower():e+=['lock SHA mismatch']
 if lock.get('design_id')!='H2' or lock.get('status')!='LOCKED':e+=['lock identity/status']
 arm=lock.get('arms',{}).get(a.arm,{});rd=Path(arm.get('run_dir',''))
 if not arm:e+=['arm missing']
 if e:write(st,{'overall':'FAIL','state':'STATIC_CONTRACT_FAILURE','errors':e});return 2
 control_rd=Path(lock['arms']['control']['run_dir']);first_done=False
 while True:
  m=load(rd/'run_manifest.json');rs=rows(rd/'h1_training_metrics.jsonl')
  if not m:write(st,{'overall':'PENDING','state':'WAITING_FOR_ARM'});time.sleep(a.poll_seconds);continue
  pid=int(m.get('process_id',-1));low20=len(rs)>=20 and all(float(x.get('entropy',99))<.3 for x in rs[-20:])
  if low20:
   action=stop(pid);write(st,{'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'FAIL','state':'H2_FAIL_PROTOCOL_ABORT_ENTROPY20','arm':a.arm,'pid':pid,'stop_action':action,'rows':len(rs)});return 3
  first={'status':'PENDING','rows':len(rs)}
  if len(rs)>=61:
   own=effective(rs)
   if a.arm=='control':first={'status':'PASS_CONTROL_BASELINE_FROZEN','effective_hps':own,'rows_used':[2,61]};first_done=True
   else:
    cr=rows(control_rd/'h1_training_metrics.jsonl');base=effective(cr)
    if base is None:write(st,{'overall':'PENDING','state':'WAITING_FOR_CONTROL_FIRST60','rows':len(rs)});time.sleep(a.poll_seconds);continue
    ratio=own/base if own and base else None;first={'status':'PASS' if ratio is not None and ratio>=.85 else 'FAIL','control_effective_hps':base,'treatment_effective_hps':own,'ratio':ratio,'minimum':.85,'rows_used':[2,61]};first_done=True
    if first['status']=='FAIL':
     action=stop(pid);write(st,{'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'FAIL','state':'H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT','arm':a.arm,'pid':pid,'stop_action':action,'first60':first});return 3
  state='ARM_RUNNING_GUARDS_PASS' if m.get('status') in ('initialized','running') else 'ARM_FINISHED_GUARDS_PASS'
  write(st,{'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS' if m.get('status')=='finished' and first_done else 'PENDING','state':state,'arm':a.arm,'pid':pid,'rows':len(rs),'first60':first,'entropy20_abort':False})
  if m.get('status')=='finished':return 0 if first_done else 2
  time.sleep(a.poll_seconds)
if __name__=='__main__':raise SystemExit(main())
