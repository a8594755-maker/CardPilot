#!/usr/bin/env python3
"""Independent fail-closed H7 design-lock audit."""
from __future__ import annotations
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--design-lock',type=Path,required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();x=json.loads(a.design_lock.read_text(encoding='utf-8-sig'));checks={};errors=[]
 def ck(name,value):checks[name]=bool(value);errors.append(name) if not value else None
 ck('hash',sha(a.design_lock)==a.expected_lock_sha256.lower());ck('identity',x.get('design_id')=='H7' and x.get('status')=='LOCKED');ck('source',x.get('source',{}).get('iteration')==31400 and Path(x['source']['path']).is_file() and sha(x['source']['path'])==x['source']['sha256']);ck('single_variable',x.get('single_variable')=={'name':'ppo_epoch_mean_kl_early_stop_threshold','control':0.0,'treatment':0.03});ck('fresh_arms',x.get('arm_budget',{}).get('actual_hands_each')==20000000 and x['arm_budget'].get('order')==['control','treatment']);ck('resource_isolation',x.get('resource_isolation',{}).get('evaluation_during_arm')=='FORBIDDEN' and x['resource_isolation'].get('evaluation_start')=='AFTER_BOTH_ENDPOINTS_FROZEN_PASS');ck('gates',x.get('gates',{}).get('first60_hps_ratio_min')==.85 and x['gates'].get('mirror_ci95_lower_min_bb100')==-20.);ck('no_official',x.get('official_hands')==0 and x.get('strength_claim')=='FORBIDDEN')
 for rel,expected in x.get('tools',{}).items():path=Path(rel);ck('tool_'+path.name,path.is_file() and sha(path)==expected)
 for item in x.get('frozen_files',[]):path=Path(item['path']);ck('frozen_'+path.name,path.is_file() and sha(path)==item['sha256'])
 result={'schema_version':'v5.hybrid.h7.design_lock_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_IMMUTABLE_H7_DESIGN_LOCK' if not errors else 'FAIL_CLOSED','checks':checks,'errors':errors,'design_lock_sha256':sha(a.design_lock),'official_hands':0};a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2,sort_keys=True));return 0 if not errors else 2
if __name__=='__main__':raise SystemExit(main())
