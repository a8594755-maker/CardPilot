#!/usr/bin/env python3
"""Fail-closed H7 control launch preflight."""
from __future__ import annotations
import argparse,hashlib,json,subprocess,sys,tempfile
from datetime import datetime,timezone
from pathlib import Path
import psutil,torch
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def main():
 p=argparse.ArgumentParser();p.add_argument('--design-lock',type=Path,required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();lock=load(a.design_lock);checks={};errors=[]
 def ck(name,value,message):checks[name]=bool(value);errors.append(message) if not value else None
 ck('lock_hash',sha(a.design_lock)==a.expected_lock_sha256.lower(),'lock hash');ck('identity',lock.get('design_id')=='H7' and lock.get('status')=='LOCKED','lock identity');source=Path(lock['source']['path']);ck('source_hash',source.is_file() and sha(source)==lock['source']['sha256'],'source hash');cp=torch.load(source,map_location='cpu',weights_only=False) if source.is_file() else {};ck('source_identity',int(cp.get('iteration',-1))==31400 and int(cp.get('total_hands',-1))==515989661,'source identity')
 for rel,expected in lock.get('tools',{}).items():path=Path(rel);ck('tool_'+path.name,path.is_file() and sha(path)==expected,'tool '+rel)
 for item in lock.get('frozen_files',[]):path=Path(item['path']);ck('frozen_'+path.name,path.is_file() and sha(path)==item['sha256'],'frozen '+str(path))
 for arm in ('control','treatment'):ck('run_dir_absent_'+arm,not Path(lock['arms'][arm]['run_dir']).exists(),arm+' dir exists')
 active=[];forbidden=[]
 for proc in psutil.process_iter(['pid','cmdline']):
  try:
   command=' '.join(proc.info.get('cmdline') or [])
   if 'train_v5.py' in command and 'v5_hybrid_h7_' in command:active.append(proc.pid)
   if 'v5_hybrid_h7_mirror.py' in command or 'slumbot' in command.lower():forbidden.append({'pid':proc.pid,'token':'h7_mirror_or_slumbot'})
  except Exception:pass
 ck('no_h7_trainer',not active,'H7 trainer');ck('no_forbidden_evaluator',not forbidden,'forbidden evaluator')
 for tool,extra in [('v5_hybrid_h7_endpoint_watch.py',['--arm','control']),('v5_hybrid_h7_endpoint_watch.py',['--arm','treatment']),('v5_hybrid_h7_protocol_watch.py',['--arm','control']),('v5_hybrid_h7_protocol_watch.py',['--arm','treatment']),('v5_hybrid_h7_completion_watch.py',['--repo',str(Path.cwd())])]:
  with tempfile.TemporaryDirectory() as tmp:
   status=Path(tmp)/'status.json';command=[sys.executable,str(Path('scripts/alpha_holdem')/tool),*extra,'--design-lock',str(a.design_lock.resolve()),'--expected-lock-sha256',sha(a.design_lock),'--status-json',str(status),'--validate-only'];done=subprocess.run(command,text=True,capture_output=True,timeout=90);value=load(status) if status.is_file() else {};ck('validate_'+tool+'_'+('_'.join(extra)),done.returncode==0 and value.get('overall')=='PASS','validate '+tool)
 result={'schema_version':'v5.hybrid.h7.preflight.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_READY_H7_CONTROL_LAUNCH' if not errors else 'FAIL_CLOSED','checks':checks,'errors':errors,'active_h7_trainers':active,'forbidden_evaluators':forbidden,'design_lock_sha256':sha(a.design_lock),'official_hands_authorized':0};a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2,sort_keys=True));return 0 if not errors else 2
if __name__=='__main__':raise SystemExit(main())
