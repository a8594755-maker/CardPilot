#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from datetime import datetime, timezone
from pathlib import Path
from v5_hybrid_h2_mirror import ACTIVE_POOL_IDS, PAIRS, PREREG_SHA, SEED, audit_manifest, sha256_file

def main():
 p=argparse.ArgumentParser();p.add_argument('--lock',required=True);p.add_argument('--out',required=True);a=p.parse_args();lp=Path(a.lock).resolve();x=json.loads(lp.read_text(encoding='utf-8'));e=[];checks={}
 def ck(n,ok,msg):checks[n]=bool(ok);e.append(msg) if not ok else None
 ck('identity',x.get('design_id')=='H2-MIRROR-001' and x.get('status')=='LOCKED','identity/status')
 ck('prereg',x.get('preregistration_sha256')==PREREG_SHA,'prereg')
 mp=Path(x.get('manifest_path',''));tp=Path(x.get('tool_path',''))
 ck('manifest_hash',mp.is_file() and sha256_file(mp)==x.get('manifest_sha256'),'manifest hash')
 ck('tool_hash',tp.is_file() and sha256_file(tp)==x.get('tool_sha256'),'tool hash')
 m=json.loads(mp.read_text(encoding='utf-8')) if mp.is_file() else {};me=audit_manifest(m);ck('manifest_content',not me,'; '.join(me))
 c=x.get('fixed_contract',{});ck('fixed_sample',c.get('pairs')==PAIRS and c.get('seed')==SEED and c.get('active_pool_ids')==ACTIVE_POOL_IDS,'fixed sample')
 ck('no_optional_stopping',c.get('adaptive_extension_allowed') is False and c.get('second_seed_allowed') is False and c.get('later_endpoint_allowed') is False,'optional stopping')
 ck('gate',c.get('bootstrap_repetitions')==10000 and c.get('bootstrap_seed')==SEED and c.get('noninferiority_ci95_lower_bb100')==-20.0,'gate')
 ck('holdout',c.get('training_use')=='FORBIDDEN_HOLDOUT_ONLY' and x.get('official_hands')==0,'holdout/official')
 rt=x.get('runtime',{});ck('runtime',rt.get('device')=='cpu' and rt.get('priority')=='below-normal' and rt.get('torch_threads')==1 and rt.get('torch_interop_threads')==1 and rt.get('gpu_forbidden') is True,'runtime')
 out={'schema_version':'v5.hybrid.h2.mirror_lock_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_IMMUTABLE_H2_MIRROR_LOCK' if not e else 'FAIL_CLOSED','checks':checks,'errors':e,'lock_path':str(lp),'lock_sha256':sha256_file(lp),'manifest_sha256':sha256_file(mp) if mp.is_file() else None,'tool_sha256':sha256_file(tp) if tp.is_file() else None,'official_hands':0};Path(a.out).write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out,indent=2,sort_keys=True));return 0 if not e else 2
if __name__=='__main__':raise SystemExit(main())
