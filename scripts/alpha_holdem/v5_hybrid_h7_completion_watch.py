#!/usr/bin/env python3
"""Duplicate-safe H7 post-arm evaluation and terminal judgment supervisor."""
from __future__ import annotations

import argparse, hashlib, json, os, subprocess, sys, time
from datetime import datetime, timezone
from pathlib import Path

PAIRS=40000
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def status(path,**payload):
 value={'schema_version':'v5.hybrid.h7.completion_watch_status.v1','checked_at':datetime.now(timezone.utc).isoformat(),**payload};path.parent.mkdir(parents=True,exist_ok=True);temp=path.with_suffix(path.suffix+'.tmp');temp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8');temp.replace(path)
def count_rows(path):
 with path.open('rb') as f:return sum(1 for line in f if line.strip())
def complete(path,lock_sha,tool_sha):
 summary=path.with_suffix('.summary.json')
 if not path.is_file() or not summary.is_file():return False
 value=load(summary);return value.get('pairs')==PAIRS and value.get('rows_sha256')==sha(path) and count_rows(path)==PAIRS and value.get('measurement_lock_sha256')==lock_sha and value.get('tool_sha256')==tool_sha
def preserve(path):
 stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');result=[]
 for item in (path,path.with_suffix('.summary.json')):
  if item.exists():dest=item.with_name(item.name+f'.interrupted-{stamp}');item.replace(dest);result.append(str(dest.resolve()))
 return result
def run(command,status_path,stage):
 status(status_path,overall='RUNNING',state=stage,command=command);process=subprocess.Popen(command,cwd=Path(__file__).resolve().parents[2]);status(status_path,overall='RUNNING',state=stage,child_pid=process.pid,command=command);rc=process.wait()
 if rc!=0:raise RuntimeError(f'{stage}_exit_{rc}')
def endpoint(path,arm):
 if not path.is_file():return None
 value=load(path)
 if value.get('overall')=='PENDING':return None
 if value.get('overall')!='PASS' or value.get('state')!='ARM_ENDPOINT_FROZEN' or value.get('arm')!=arm:raise ValueError(f'{arm} endpoint terminal')
 checkpoint=Path(value['checkpoint_path'])
 if not checkpoint.is_file() or sha(checkpoint)!=value.get('checkpoint_sha256'):raise ValueError(f'{arm} checkpoint identity')
 return value
def main():
 p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--design-lock',type=Path,required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--status-json',type=Path,required=True);p.add_argument('--poll-seconds',type=int,default=30);p.add_argument('--validate-only',action='store_true');a=p.parse_args();repo=a.repo.resolve();os.chdir(repo);sp=a.status_json.resolve();lp=a.design_lock.resolve()
 try:
  if not lp.is_file() or sha(lp)!=a.expected_lock_sha256.lower():raise ValueError('design lock SHA')
  lock=load(lp)
  if lock.get('design_id')!='H7' or lock.get('status')!='LOCKED':raise ValueError('design lock identity')
  tools=lock['tools'];mirror_tool=repo/'scripts/alpha_holdem/v5_hybrid_h7_mirror.py';judge_tool=repo/'scripts/alpha_holdem/v5_hybrid_h7_judge.py'
  if sha(mirror_tool)!=tools['scripts/alpha_holdem/v5_hybrid_h7_mirror.py'] or sha(judge_tool)!=tools['scripts/alpha_holdem/v5_hybrid_h7_judge.py']:raise ValueError('child tool hash')
  mirror_dir=Path(lock['measurement']['mirror_dir']);manifest=mirror_dir/'manifest.json';measurement_lock=mirror_dir/'measurement_lock.json';mlsha=lock['measurement']['mirror_lock_sha256'];mtoolsha=tools['scripts/alpha_holdem/v5_hybrid_h7_mirror.py']
  if sha(manifest)!=lock['measurement']['mirror_manifest_sha256'] or sha(measurement_lock)!=mlsha:raise ValueError('mirror artifacts')
  if a.validate_only:status(sp,overall='PASS',state='VALIDATE_ONLY_STATIC_CONTRACT_PASS');return 0
  dirs={arm:Path(lock['arms'][arm]['run_dir']) for arm in ('control','treatment')};endpoint_status={arm:dirs[arm]/f'h7_{arm}_endpoint_status.json' for arm in dirs};protocol={arm:dirs[arm]/f'h7_{arm}_protocol_status.json' for arm in dirs};outputs={arm:mirror_dir/f'{arm}_pairs.jsonl' for arm in dirs};audit=mirror_dir/'audit.json';mirror_judgment=mirror_dir/'judgment.json';judgment=repo/'reports/v5_hybrid_h7_judgment_20260713.json'
  while True:
   if judgment.is_file():
    existing=load(judgment)
    if existing.get('design_lock_sha256')==sha(lp) and existing.get('overall') in {'PASS','FAIL','INCONCLUSIVE'}:status(sp,overall='PASS',state='TERMINAL_RESULT_READY_HANDOFF_UPDATE_REQUIRED',verdict=existing['overall'],h7_judgment=str(judgment.resolve()));return 0
   terminal=None
   for arm in ('control','treatment'):
    if protocol[arm].is_file() and load(protocol[arm]).get('overall')=='FAIL':terminal=arm;break
   if terminal:
    run([sys.executable,'-u',str(judge_tool),'--design-lock',str(lp),'--expected-lock-sha256',sha(lp),'--control-status',str(endpoint_status['control']),'--treatment-status',str(endpoint_status['treatment']),'--control-protocol',str(protocol['control']),'--treatment-protocol',str(protocol['treatment']),'--mirror-judgment',str(mirror_judgment),'--out',str(judgment),'--device','cuda'],sp,'RUNNING_H7_PROTOCOL_TERMINAL_JUDGMENT');continue
   eps={arm:endpoint(endpoint_status[arm],arm) for arm in ('control','treatment')}
   if not all(eps.values()):status(sp,overall='PENDING',state='WAITING_FOR_BOTH_FROZEN_ENDPOINTS',control_endpoint=bool(eps['control']),treatment_endpoint=bool(eps['treatment']));time.sleep(max(1,a.poll_seconds));continue
   for arm in ('control','treatment'):
    if not complete(outputs[arm],mlsha,mtoolsha):
     if outputs[arm].exists() or outputs[arm].with_suffix('.summary.json').exists():preserve(outputs[arm])
     run([sys.executable,'-u',str(mirror_tool),'run-arm','--manifest',str(manifest),'--endpoint',eps[arm]['checkpoint_path'],'--arm',arm,'--out',str(outputs[arm]),'--device','cpu','--priority','below-normal','--torch-threads','1','--torch-interop-threads','1','--measurement-lock',str(measurement_lock),'--expected-lock-sha256',mlsha],sp,f'RUNNING_{arm.upper()}_MIRROR')
     if not complete(outputs[arm],mlsha,mtoolsha):raise ValueError(f'{arm} mirror incomplete')
   if not audit.exists():run([sys.executable,'-u',str(mirror_tool),'audit','--manifest',str(manifest),'--control',str(outputs['control']),'--treatment',str(outputs['treatment']),'--out',str(audit),'--measurement-lock',str(measurement_lock),'--expected-lock-sha256',mlsha],sp,'RUNNING_MIRROR_AUDIT')
   if load(audit).get('overall')!='PASS_IMMUTABLE_H7_MIRROR':raise ValueError('mirror audit')
   if not mirror_judgment.exists():run([sys.executable,'-u',str(mirror_tool),'judge','--manifest',str(manifest),'--control',str(outputs['control']),'--treatment',str(outputs['treatment']),'--audit',str(audit),'--out',str(mirror_judgment),'--measurement-lock',str(measurement_lock),'--expected-lock-sha256',mlsha],sp,'RUNNING_MIRROR_JUDGMENT')
   if not judgment.exists():run([sys.executable,'-u',str(judge_tool),'--design-lock',str(lp),'--expected-lock-sha256',sha(lp),'--control-status',str(endpoint_status['control']),'--treatment-status',str(endpoint_status['treatment']),'--control-protocol',str(protocol['control']),'--treatment-protocol',str(protocol['treatment']),'--mirror-judgment',str(mirror_judgment),'--out',str(judgment),'--device','cuda'],sp,'RUNNING_H7_TERMINAL_JUDGMENT')
 except Exception as exc:status(sp,overall='FAIL_CLOSED',state='COMPLETION_CHAIN_STOPPED',error=f'{type(exc).__name__}: {exc}',behavior_launch_authorized=False,official_hands_authorized=0);return 2
if __name__=='__main__':raise SystemExit(main())
