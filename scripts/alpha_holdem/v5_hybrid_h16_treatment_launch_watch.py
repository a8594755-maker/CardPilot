#!/usr/bin/env python3
"""H16 control endpoint watcher that exposes a safe no-trainer treatment boundary."""
from __future__ import annotations
import argparse,json,os,subprocess,time
from datetime import datetime,timezone
from pathlib import Path
RUN_ID='v5_hybrid_h16_treatment_catchsmoothl1b1_same35051_20m_r1_20260719'
def load(path):
 try:return json.loads(Path(path).read_text(encoding='utf-8-sig'))
 except Exception:return {}
def write(path,value):
 path=Path(path);tmp=path.with_suffix(path.suffix+'.tmp');tmp.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n',encoding='utf-8');os.replace(tmp,path)
def main():
 p=argparse.ArgumentParser();p.add_argument('--control-dir',type=Path,required=True);p.add_argument('--treatment-dir',type=Path,required=True);p.add_argument('--launcher',type=Path,required=True);p.add_argument('--status-json',type=Path,required=True);p.add_argument('--poll-seconds',type=int,default=30);a=p.parse_args();control=a.control_dir.resolve();treatment=a.treatment_dir.resolve();launcher=a.launcher.resolve();status=a.status_json.resolve()
 if not launcher.is_file():write(status,{'overall':'FAIL','state':'STATIC_LAUNCHER_MISSING'});return 2
 while True:
  if treatment.exists():
   manifest=load(treatment/'run_manifest.json')
   if manifest.get('run_id')==RUN_ID:write(status,{'overall':'PASS','state':'TREATMENT_ALREADY_LAUNCHED','run_id':RUN_ID});return 0
   write(status,{'overall':'FAIL','state':'TREATMENT_DIR_IDENTITY_CONFLICT'});return 2
  endpoint=load(control/'h16_control_endpoint_status.json');protocol=load(control/'h16_control_protocol_status.json')
  if endpoint.get('overall')=='FAIL' or protocol.get('overall')=='FAIL':write(status,{'overall':'FAIL','state':'TERMINAL_BLOCKED_CONTROL_FAILED'});return 2
  ready=endpoint.get('overall')=='PASS' and endpoint.get('state')=='ARM_ENDPOINT_FROZEN' and protocol.get('overall')=='PASS' and protocol.get('first60',{}).get('status')=='PASS_CONTROL_BASELINE_FROZEN'
  if not ready:write(status,{'overall':'PENDING','state':'WAITING_FOR_CONTROL_ENDPOINT','checked_at':datetime.now(timezone.utc).isoformat(),'endpoint':endpoint.get('state'),'protocol':protocol.get('state')});time.sleep(max(1,a.poll_seconds));continue
  write(status,{
   'overall':'PASS','state':'TREATMENT_LAUNCH_READY_SAFE_NO_TRAINER_BOUNDARY',
   'launcher':str(launcher),'run_id':RUN_ID,
   'finished_at':datetime.now(timezone.utc).isoformat(),
   'launch_authority':'EXACT_LOCKED_LAUNCHER_AFTER_CONTROL_ORDERED_SUPERVISOR_CLEAN_EXIT',
  });return 0
if __name__=='__main__':raise SystemExit(main())
