#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
import psutil, torch

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--design-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 lp=Path(a.design_lock).resolve();lock=json.loads(lp.read_text(encoding='utf-8'));errors=[];checks={}
 def ck(n,ok,msg):checks[n]=bool(ok);errors.append(msg) if not ok else None
 ck('lock_hash',sha(lp)==a.expected_lock_sha256.lower(),'lock hash mismatch')
 ck('lock_status',lock.get('design_id')=='H2' and lock.get('status')=='LOCKED','lock identity/status')
 src=Path(lock['source']['path']);ck('source_hash',src.is_file() and sha(src)==lock['source']['sha256'],'source hash mismatch')
 x=torch.load(src,map_location='cpu',weights_only=False) if src.is_file() else {}
 ck('source_identity',int(x.get('iteration',-1))==31400 and int(x.get('total_hands',-1))==515989661,'source iter/hands mismatch')
 for rel,expected in lock.get('tools',{}).items():
  q=Path(rel);ck('tool_'+q.name,q.is_file() and sha(q)==expected,f'tool mismatch {rel}')
 for arm,v in lock['arms'].items():ck('run_dir_absent_'+arm,not Path(v['run_dir']).exists(),f'{arm} run dir already exists')
 trainers=[]
 for proc in psutil.process_iter(['pid','cmdline']):
  try:
   cmd=' '.join(proc.info.get('cmdline') or [])
   if 'train_v5.py' in cmd and 'v5_hybrid_h2_' in cmd:trainers.append({'pid':proc.pid,'cmd':cmd})
  except Exception:pass
 ck('no_h2_trainer',not trainers,'H2 trainer already running')
 prereg=Path(lock['preregistration']['path']);ck('prereg_hash',prereg.is_file() and sha(prereg)==lock['preregistration']['sha256'],'prereg mismatch')
 audit=Path(lock['preregistration']['audit_path']);ad=json.loads(audit.read_text(encoding='utf-8')) if audit.is_file() else {};ck('prereg_audit',audit.is_file() and sha(audit)==lock['preregistration']['audit_sha256'] and ad.get('overall')=='PASS_IMMUTABLE_H2_PREREGISTRATION','prereg audit mismatch')
 out={'schema_version':'v5.hybrid.h2.preflight.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_READY_CONTROL_LAUNCH' if not errors else 'FAIL_CLOSED','checks':checks,'errors':errors,'design_lock_sha256':sha(lp),'source_sha256':sha(src) if src.is_file() else None,'official_hands_authorized':0}
 Path(a.out).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out,indent=2,sort_keys=True));return 0 if not errors else 2
if __name__=='__main__':raise SystemExit(main())
