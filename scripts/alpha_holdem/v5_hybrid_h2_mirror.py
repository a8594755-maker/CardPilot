#!/usr/bin/env python3
"""Frozen H2 40k common-deal, fixed-pool mirror evaluator and audit."""
from __future__ import annotations
import argparse, hashlib, json, random, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
import torch
from v5_h1_calibration import ACTIVE_POOL_IDS, SOURCE_SHA, load_source_and_pool, play_trace
from v5_mirror_eval import configure_runtime, load_policy, sha256_file, shuffled_deck
from alpha_holdem.environment_v55 import HUNLEnvironmentV55

PAIRS=40000; SEED=2026071403; BOOTSTRAP_REPS=10000; BOOTSTRAP_SEED=2026071403
PREREG_SHA='aaf8bf30db6e757e15c1b9ae1bdd0b5e3eed379ec1dadbd23b2d8a70b1f2fa2f'
SOURCE_PATH=Path(r'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709\v5_exp005_cutover_gate31400_checkpoint.pt')
TOOL_PATH=Path(__file__).resolve()

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def payload_sha(x,field):
 y=dict(x);y.pop(field,None);return hashlib.sha256(canonical(y)).hexdigest()
def write_new(path:Path,text:str):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8',newline='\n') as f:f.write(text)
def load_measurement_lock(path:Path,expected_sha:str,manifest:Path)->dict[str,Any]:
 if sha256_file(path)!=expected_sha.lower():raise ValueError('measurement lock SHA mismatch')
 x=json.loads(path.read_text(encoding='utf-8'))
 if x.get('design_id')!='H2-MIRROR-001' or x.get('status')!='LOCKED':raise ValueError('measurement lock identity/status')
 if x.get('tool_sha256')!=sha256_file(TOOL_PATH) or x.get('manifest_sha256')!=sha256_file(manifest):raise ValueError('measurement lock tool/manifest binding')
 return x
def prepare(out:Path):
 if out.exists():raise FileExistsError(out)
 _,_,ident=load_source_and_pool(SOURCE_PATH,'cpu');rng=random.Random(SEED);stream=hashlib.sha256();deals=[]
 for i in range(PAIRS):
  deck=shuffled_deck(rng); raw=bytes(deck); dh=hashlib.sha256(raw).hexdigest();stream.update(i.to_bytes(8,'big'));stream.update(raw)
  deals.append({'index':i,'deal_id':f'h2mirror-{SEED}-{i:05d}-{dh[:16]}','deck_sha256':dh,'opponent_pool_id':ACTIVE_POOL_IDS[i%len(ACTIVE_POOL_IDS)]})
 m={'schema_version':'v5.hybrid.h2.mirror_manifest.v1','design_id':'H2','created_at':datetime.now(timezone.utc).isoformat(),'preregistration_sha256':PREREG_SHA,'pairs':PAIRS,'hands_per_arm':PAIRS*2,'seed':SEED,'seat_order':[0,1],'starting_stack_bb':200.0,'policy_mode':'greedy_argmax_both_sides','source_checkpoint_sha256':SOURCE_SHA,'active_pool_ids':ACTIVE_POOL_IDS,'identities':ident,'deal_stream_sha256':stream.hexdigest(),'cluster':'whole common deal pair','adaptive_extension_allowed':False,'training_use':'FORBIDDEN_HOLDOUT_ONLY','deals':deals}
 m['manifest_payload_sha256']=payload_sha(m,'manifest_payload_sha256');write_new(out,json.dumps(m,indent=2,sort_keys=True)+'\n');return m
def checkpoint_identity(path:Path,arm:str):
 c=torch.load(path,map_location='cpu',weights_only=False); cfg=c.get('config') or {}; expected=(arm=='treatment')
 if c.get('h2_window_arm')!=arm or bool(c.get('h2_showdown_ev_value_targets'))!=expected:raise ValueError('endpoint arm identity mismatch')
 if int(c.get('total_hands',-1))<535989661 or int(c.get('total_hands',-1))>536039661:raise ValueError('endpoint hands outside lock')
 if cfg.get('h2_preregistration_sha256')!=PREREG_SHA:raise ValueError('endpoint prereg hash mismatch')
 return {'path':str(path.resolve()),'sha256':sha256_file(path),'iteration':int(c['iteration']),'hands':int(c['total_hands']),'arm':arm,'showdown_targets':expected}
def run_arm(manifest_path:Path,endpoint:Path,arm:str,out:Path,device:str,lock_path:Path,lock_sha:str,runtime:dict[str,Any]):
 if out.exists():raise FileExistsError(out)
 lock=load_measurement_lock(lock_path,lock_sha,manifest_path);m=json.loads(manifest_path.read_text(encoding='utf-8')); errs=audit_manifest(m)
 if errs:raise ValueError('; '.join(errs))
 identity=checkpoint_identity(endpoint,arm); candidate=load_policy(arm,endpoint,device); _,pool,_=load_source_and_pool(SOURCE_PATH,device);env=HUNLEnvironmentV55(starting_stack=200.0);rng=random.Random(SEED);started=time.monotonic();ood=decisions=0
 out.parent.mkdir(parents=True,exist_ok=True)
 with out.open('x',encoding='utf-8',newline='\n') as f:
  for expected in m['deals']:
   deck=shuffled_deck(rng);dh=hashlib.sha256(bytes(deck)).hexdigest()
   if dh!=expected['deck_sha256']:raise RuntimeError('deal replay mismatch')
   opp=pool[int(expected['opponent_pool_id'])]; rewards=[]
   for seat in (0,1):
    h=play_trace(env,deck,candidate,opp,seat);rewards.append(float(h['reward_bb']));ood+=int(h['source_ood']);decisions+=int(h['source_decisions'])
   row={'schema_version':'v5.hybrid.h2.mirror_pair.v1','arm':arm,'deal_id':expected['deal_id'],'index':expected['index'],'deck_sha256':dh,'opponent_pool_id':expected['opponent_pool_id'],'candidate_rewards_bb':rewards,'pair_mean_bb_per_hand':sum(rewards)/2.0}
   f.write(json.dumps(row,sort_keys=True)+'\n')
 summary={'schema_version':'v5.hybrid.h2.mirror_arm_summary.v1','arm':arm,'endpoint':identity,'manifest_sha256':sha256_file(manifest_path),'measurement_lock_sha256':sha256_file(lock_path),'tool_sha256':sha256_file(TOOL_PATH),'pairs':PAIRS,'hands':PAIRS*2,'rows_sha256':sha256_file(out),'ood_rate':ood/max(decisions,1),'elapsed_seconds':time.monotonic()-started,'runtime':runtime,'official_hands':0}
 sp=out.with_suffix('.summary.json');write_new(sp,json.dumps(summary,indent=2,sort_keys=True)+'\n');return summary
def audit_manifest(m):
 e=[]
 if m.get('schema_version')!='v5.hybrid.h2.mirror_manifest.v1' or m.get('preregistration_sha256')!=PREREG_SHA:e+=['manifest identity']
 if m.get('pairs')!=PAIRS or m.get('seed')!=SEED or m.get('active_pool_ids')!=ACTIVE_POOL_IDS:e+=['manifest fixed fields']
 if m.get('manifest_payload_sha256')!=payload_sha(m,'manifest_payload_sha256'):e+=['manifest payload hash']
 ds=m.get('deals',[])
 if len(ds)!=PAIRS or len({d.get('deal_id') for d in ds})!=PAIRS:e+=['deal coverage/uniqueness']
 if any(d.get('index')!=i or d.get('opponent_pool_id')!=ACTIVE_POOL_IDS[i%5] for i,d in enumerate(ds)):e+=['deal order/panel assignment']
 return e
def read_rows(path:Path,arm:str,m):
 rows=[]
 with path.open(encoding='utf-8') as f:
  for line in f:
   if line.strip():rows.append(json.loads(line))
 e=[]
 if len(rows)!=PAIRS:e+=['row count']
 for i,r in enumerate(rows):
  if r.get('arm')!=arm or r.get('index')!=i or r.get('deal_id')!=m['deals'][i]['deal_id'] or r.get('deck_sha256')!=m['deals'][i]['deck_sha256']:e+=[f'row alignment {i}'];break
  vals=r.get('candidate_rewards_bb');
  if not isinstance(vals,list) or len(vals)!=2 or abs(float(r.get('pair_mean_bb_per_hand'))-sum(map(float,vals))/2)>1e-12:e+=[f'row numeric {i}'];break
 return rows,e
def audit_bundle(manifest:Path,control:Path,treatment:Path,out:Path,lock_path:Path,lock_sha:str):
 load_measurement_lock(lock_path,lock_sha,manifest);m=json.loads(manifest.read_text(encoding='utf-8'));e=audit_manifest(m);cr,ce=read_rows(control,'control',m);tr,te=read_rows(treatment,'treatment',m);e+=ce+te
 for arm,path in [('control',control),('treatment',treatment)]:
  sp=path.with_suffix('.summary.json');s=json.loads(sp.read_text(encoding='utf-8')) if sp.is_file() else {};rt=s.get('runtime',{});priority=rt.get('priority',{});e += ([] if s.get('rows_sha256')==sha256_file(path) and s.get('pairs')==PAIRS and s.get('ood_rate',1)<=.15 and s.get('measurement_lock_sha256')==sha256_file(lock_path) and s.get('tool_sha256')==sha256_file(TOOL_PATH) and rt.get('torch_threads')==1 and rt.get('torch_interop_threads')==1 and priority.get('requested')=='below-normal' and priority.get('applied') is True else [f'{arm} summary/hash/OOD/lock/runtime'])
 outv={'schema_version':'v5.hybrid.h2.mirror_audit.v1','overall':'PASS_IMMUTABLE_H2_MIRROR' if not e else 'FAIL_CLOSED','errors':e,'manifest_sha256':sha256_file(manifest),'measurement_lock_sha256':sha256_file(lock_path),'tool_sha256':sha256_file(TOOL_PATH),'control_sha256':sha256_file(control),'treatment_sha256':sha256_file(treatment),'pairs':len(cr) if not e else None,'official_hands':0};write_new(out,json.dumps(outv,indent=2,sort_keys=True)+'\n');return outv
def judge(manifest:Path,control:Path,treatment:Path,audit:Path,out:Path,lock_path:Path,lock_sha:str):
 load_measurement_lock(lock_path,lock_sha,manifest);a=json.loads(audit.read_text(encoding='utf-8'));m=json.loads(manifest.read_text(encoding='utf-8'))
 if a.get('overall')!='PASS_IMMUTABLE_H2_MIRROR':raise ValueError('mirror audit not PASS')
 cr,_=read_rows(control,'control',m);tr,_=read_rows(treatment,'treatment',m);d=np.array([(float(t['pair_mean_bb_per_hand'])-float(c['pair_mean_bb_per_hand']))*100 for c,t in zip(cr,tr)]);point=float(d.mean());rng=np.random.default_rng(BOOTSTRAP_SEED);means=np.empty(BOOTSTRAP_REPS)
 for i in range(BOOTSTRAP_REPS):means[i]=float(d[rng.integers(0,PAIRS,PAIRS)].mean())
 lo,hi=map(float,np.quantile(means,[.025,.975]));status='PASS' if lo>=-20 else ('FAIL' if hi < -20 else 'INCONCLUSIVE')
 x={'schema_version':'v5.hybrid.h2.mirror_judgment.v1','status':status,'pairs':PAIRS,'treatment_minus_control_bb100':point,'ci95_lower_bb100':lo,'ci95_upper_bb100':hi,'margin_bb100':-20.0,'bootstrap_repetitions':BOOTSTRAP_REPS,'bootstrap_seed':BOOTSTRAP_SEED,'audit_sha256':sha256_file(audit),'official_hands':0};write_new(out,json.dumps(x,indent=2,sort_keys=True)+'\n');return x
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='mode',required=True)
 q=s.add_parser('prepare');q.add_argument('--out',required=True)
 q=s.add_parser('run-arm');q.add_argument('--manifest',required=True);q.add_argument('--endpoint',required=True);q.add_argument('--arm',choices=['control','treatment'],required=True);q.add_argument('--out',required=True);q.add_argument('--device',choices=['cpu'],default='cpu');q.add_argument('--priority',choices=['below-normal'],default='below-normal');q.add_argument('--torch-threads',type=int,choices=[1],default=1);q.add_argument('--torch-interop-threads',type=int,choices=[1],default=1);q.add_argument('--measurement-lock',required=True);q.add_argument('--expected-lock-sha256',required=True)
 q=s.add_parser('audit');q.add_argument('--manifest',required=True);q.add_argument('--control',required=True);q.add_argument('--treatment',required=True);q.add_argument('--out',required=True);q.add_argument('--measurement-lock',required=True);q.add_argument('--expected-lock-sha256',required=True)
 q=s.add_parser('judge');q.add_argument('--manifest',required=True);q.add_argument('--control',required=True);q.add_argument('--treatment',required=True);q.add_argument('--audit',required=True);q.add_argument('--out',required=True);q.add_argument('--measurement-lock',required=True);q.add_argument('--expected-lock-sha256',required=True)
 a=p.parse_args()
 if a.mode=='prepare':x=prepare(Path(a.out))
 elif a.mode=='run-arm':
  runtime=configure_runtime(a);x=run_arm(Path(a.manifest),Path(a.endpoint),a.arm,Path(a.out),a.device,Path(a.measurement_lock),a.expected_lock_sha256,runtime)
 elif a.mode=='audit':x=audit_bundle(Path(a.manifest),Path(a.control),Path(a.treatment),Path(a.out),Path(a.measurement_lock),a.expected_lock_sha256)
 else:x=judge(Path(a.manifest),Path(a.control),Path(a.treatment),Path(a.audit),Path(a.out),Path(a.measurement_lock),a.expected_lock_sha256)
 print(json.dumps(x,indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
