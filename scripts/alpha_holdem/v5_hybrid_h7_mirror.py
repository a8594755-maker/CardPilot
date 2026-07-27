#!/usr/bin/env python3
"""Frozen H7 40k common-deal mirror evaluator; runs only after both endpoints."""
from __future__ import annotations

import argparse, hashlib, json, random, sys, time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np, torch

THIS_DIR = Path(__file__).resolve().parent; REPO = THIS_DIR.parents[1]
sys.path.insert(0, str(THIS_DIR)); sys.path.insert(0, str(REPO / "scripts"))
from alpha_holdem.environment_v55 import HUNLEnvironmentV55
from v5_h1_calibration import ACTIVE_POOL_IDS, SOURCE_SHA, load_source_and_pool, play_trace
from v5_mirror_eval import configure_runtime, load_policy, sha256_file, shuffled_deck

PAIRS=40000;SEED=2026071701;REPS=10000;BOOTSTRAP_SEED=2026071701
PREREG_SHA='45b57f4fe817f1b98e7267a8e482d46b8121fb41d4e432a8af25a1857c6cb4b7'
SOURCE=Path(r'C:\Users\a8594\CardPilot\models\alpha_holdem_v5_from_zero\v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709\v5_exp005_cutover_gate31400_checkpoint.pt')
TOOL=Path(__file__).resolve()

def canonical(x):return json.dumps(x,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()
def payload_sha(x,field):y=dict(x);y.pop(field,None);return hashlib.sha256(canonical(y)).hexdigest()
def write_new(path,x):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('x',encoding='utf-8',newline='\n') as f:f.write(json.dumps(x,indent=2,sort_keys=True)+'\n')
def load_lock(path,expected,manifest):
 if sha256_file(path)!=expected.lower():raise ValueError('measurement lock SHA mismatch')
 x=json.loads(path.read_text(encoding='utf-8'))
 if x.get('design_id')!='H7-MIRROR-001' or x.get('status')!='LOCKED':raise ValueError('measurement lock identity/status')
 if x.get('tool_sha256')!=sha256_file(TOOL) or x.get('manifest_sha256')!=sha256_file(manifest):raise ValueError('measurement lock tool/manifest binding')
 return x
def prepare(out):
 if out.exists():raise FileExistsError(out)
 _,_,ident=load_source_and_pool(SOURCE,'cpu');rng=random.Random(SEED);stream=hashlib.sha256();deals=[]
 for i in range(PAIRS):
  deck=shuffled_deck(rng);raw=bytes(deck);dh=hashlib.sha256(raw).hexdigest();stream.update(i.to_bytes(8,'big'));stream.update(raw);deals.append({'index':i,'deal_id':f'h7mirror-{SEED}-{i:05d}-{dh[:16]}','deck_sha256':dh,'opponent_pool_id':ACTIVE_POOL_IDS[i%5]})
 x={'schema_version':'v5.hybrid.h7.mirror_manifest.v1','design_id':'H7','created_at':datetime.now(timezone.utc).isoformat(),'preregistration_sha256':PREREG_SHA,'pairs':PAIRS,'hands_per_arm':PAIRS*2,'seed':SEED,'seat_order':[0,1],'starting_stack_bb':200.0,'policy_mode':'greedy_argmax_both_sides','source_checkpoint_sha256':SOURCE_SHA,'active_pool_ids':ACTIVE_POOL_IDS,'identities':ident,'deal_stream_sha256':stream.hexdigest(),'cluster':'whole common deal pair','adaptive_extension_allowed':False,'training_use':'FORBIDDEN_HOLDOUT_ONLY','deals':deals};x['manifest_payload_sha256']=payload_sha(x,'manifest_payload_sha256');write_new(out,x);return x
def audit_manifest(x):
 e=[]
 if x.get('schema_version')!='v5.hybrid.h7.mirror_manifest.v1' or x.get('preregistration_sha256')!=PREREG_SHA:e+=['manifest identity']
 if x.get('pairs')!=PAIRS or x.get('seed')!=SEED or x.get('active_pool_ids')!=ACTIVE_POOL_IDS:e+=['manifest fixed fields']
 if x.get('manifest_payload_sha256')!=payload_sha(x,'manifest_payload_sha256'):e+=['manifest payload hash']
 ds=x.get('deals',[])
 if len(ds)!=PAIRS or len({d.get('deal_id') for d in ds})!=PAIRS:e+=['deal coverage/uniqueness']
 if any(d.get('index')!=i or d.get('opponent_pool_id')!=ACTIVE_POOL_IDS[i%5] for i,d in enumerate(ds)):e+=['deal order/panel assignment']
 return e
def checkpoint_identity(path,arm):
 c=torch.load(path,map_location='cpu',weights_only=False);cfg=c.get('config') or {};target=.03 if arm=='treatment' else 0.
 if c.get('h7_window_arm')!=arm or abs(float(c.get('ppo_target_kl',-1))-target)>1e-12:raise ValueError('endpoint H7 arm identity')
 if cfg.get('h7_preregistration_sha256')!=PREREG_SHA:raise ValueError('endpoint prereg identity')
 if not 535989661<=int(c.get('total_hands',-1))<=536039661:raise ValueError('endpoint hands')
 return {'path':str(path.resolve()),'sha256':sha256_file(path),'iteration':int(c['iteration']),'hands':int(c['total_hands']),'arm':arm,'ppo_target_kl':target}
def run_arm(manifest_path,endpoint,arm,out,device,lock_path,lock_sha,runtime):
 if out.exists():raise FileExistsError(out)
 load_lock(lock_path,lock_sha,manifest_path);m=json.loads(manifest_path.read_text(encoding='utf-8'));e=audit_manifest(m)
 if e:raise ValueError('; '.join(e))
 identity=checkpoint_identity(endpoint,arm);candidate=load_policy(arm,endpoint,device);_,pool,_=load_source_and_pool(SOURCE,device);env=HUNLEnvironmentV55(starting_stack=200.0);rng=random.Random(SEED);started=time.monotonic();ood=decisions=0
 with out.open('x',encoding='utf-8',newline='\n') as f:
  for expected in m['deals']:
   deck=shuffled_deck(rng);dh=hashlib.sha256(bytes(deck)).hexdigest()
   if dh!=expected['deck_sha256']:raise RuntimeError('deal replay mismatch')
   opp=pool[int(expected['opponent_pool_id'])];rewards=[]
   for seat in (0,1):
    hand=play_trace(env,deck,candidate,opp,seat);rewards.append(float(hand['reward_bb']));ood+=int(hand['source_ood']);decisions+=int(hand['source_decisions'])
   f.write(json.dumps({'schema_version':'v5.hybrid.h7.mirror_pair.v1','arm':arm,'deal_id':expected['deal_id'],'index':expected['index'],'deck_sha256':dh,'opponent_pool_id':expected['opponent_pool_id'],'candidate_rewards_bb':rewards,'pair_mean_bb_per_hand':sum(rewards)/2},sort_keys=True)+'\n')
 s={'schema_version':'v5.hybrid.h7.mirror_arm_summary.v1','arm':arm,'endpoint':identity,'manifest_sha256':sha256_file(manifest_path),'measurement_lock_sha256':sha256_file(lock_path),'tool_sha256':sha256_file(TOOL),'pairs':PAIRS,'hands':PAIRS*2,'rows_sha256':sha256_file(out),'ood_rate':ood/max(decisions,1),'elapsed_seconds':time.monotonic()-started,'runtime':runtime,'official_hands':0};write_new(out.with_suffix('.summary.json'),s);return s
def read_rows(path,arm,m):
 with path.open(encoding='utf-8') as f:values=[json.loads(line) for line in f if line.strip()]
 e=[]
 if len(values)!=PAIRS:return values,['row count']
 for i,row in enumerate(values):
  ex=m['deals'][i];rewards=row.get('candidate_rewards_bb')
  if row.get('schema_version')!='v5.hybrid.h7.mirror_pair.v1' or row.get('arm')!=arm or row.get('index')!=i or row.get('deal_id')!=ex['deal_id'] or row.get('deck_sha256')!=ex['deck_sha256']:e+=[f'row alignment {i}'];break
  if not isinstance(rewards,list) or len(rewards)!=2 or abs(float(row.get('pair_mean_bb_per_hand'))-sum(map(float,rewards))/2)>1e-12:e+=[f'row numeric {i}'];break
 return values,e
def audit_bundle(manifest,control,treatment,out,lock_path,lock_sha):
 load_lock(lock_path,lock_sha,manifest);m=json.loads(manifest.read_text(encoding='utf-8'));e=audit_manifest(m);cr,ce=read_rows(control,'control',m);tr,te=read_rows(treatment,'treatment',m);e+=ce+te
 for arm,path in [('control',control),('treatment',treatment)]:
  sp=path.with_suffix('.summary.json');s=json.loads(sp.read_text(encoding='utf-8')) if sp.is_file() else {};rt=s.get('runtime',{});priority=rt.get('priority',{})
  if not(s.get('rows_sha256')==sha256_file(path) and s.get('pairs')==PAIRS and s.get('ood_rate',1)<=.15 and s.get('measurement_lock_sha256')==sha256_file(lock_path) and s.get('tool_sha256')==sha256_file(TOOL) and rt.get('torch_threads')==1 and rt.get('torch_interop_threads')==1 and priority.get('requested')=='below-normal' and priority.get('applied') is True):e+=[f'{arm} summary/hash/OOD/lock/runtime']
 x={'schema_version':'v5.hybrid.h7.mirror_audit.v1','overall':'PASS_IMMUTABLE_H7_MIRROR' if not e else 'FAIL_CLOSED','errors':e,'manifest_sha256':sha256_file(manifest),'measurement_lock_sha256':sha256_file(lock_path),'tool_sha256':sha256_file(TOOL),'control_sha256':sha256_file(control),'treatment_sha256':sha256_file(treatment),'pairs':len(cr) if not e else None,'official_hands':0};write_new(out,x);return x
def judge(manifest,control,treatment,audit,out,lock_path,lock_sha):
 load_lock(lock_path,lock_sha,manifest);a=json.loads(audit.read_text(encoding='utf-8'));m=json.loads(manifest.read_text(encoding='utf-8'))
 if a.get('overall')!='PASS_IMMUTABLE_H7_MIRROR':raise ValueError('mirror audit not PASS')
 cr,_=read_rows(control,'control',m);tr,_=read_rows(treatment,'treatment',m);d=np.array([(float(t['pair_mean_bb_per_hand'])-float(c['pair_mean_bb_per_hand']))*100 for c,t in zip(cr,tr)]);point=float(d.mean());rng=np.random.default_rng(BOOTSTRAP_SEED);means=np.empty(REPS)
 for i in range(REPS):means[i]=float(d[rng.integers(0,PAIRS,PAIRS)].mean())
 lo,hi=map(float,np.quantile(means,[.025,.975]));status='PASS' if lo>=-20 else ('FAIL' if hi < -20 else 'INCONCLUSIVE');x={'schema_version':'v5.hybrid.h7.mirror_judgment.v1','status':status,'pairs':PAIRS,'treatment_minus_control_bb100':point,'ci95_lower_bb100':lo,'ci95_upper_bb100':hi,'margin_bb100':-20.,'bootstrap_repetitions':REPS,'bootstrap_seed':BOOTSTRAP_SEED,'audit_sha256':sha256_file(audit),'official_hands':0};write_new(out,x);return x
def main():
 p=argparse.ArgumentParser();s=p.add_subparsers(dest='mode',required=True);q=s.add_parser('prepare');q.add_argument('--out',type=Path,required=True);q=s.add_parser('run-arm');q.add_argument('--manifest',type=Path,required=True);q.add_argument('--endpoint',type=Path,required=True);q.add_argument('--arm',choices=['control','treatment'],required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--device',choices=['cpu'],default='cpu');q.add_argument('--priority',choices=['below-normal'],default='below-normal');q.add_argument('--torch-threads',type=int,choices=[1],default=1);q.add_argument('--torch-interop-threads',type=int,choices=[1],default=1);q.add_argument('--measurement-lock',type=Path,required=True);q.add_argument('--expected-lock-sha256',required=True)
 for mode in ('audit','judge'):
  q=s.add_parser(mode);q.add_argument('--manifest',type=Path,required=True);q.add_argument('--control',type=Path,required=True);q.add_argument('--treatment',type=Path,required=True);q.add_argument('--out',type=Path,required=True);q.add_argument('--measurement-lock',type=Path,required=True);q.add_argument('--expected-lock-sha256',required=True)
  if mode=='judge':q.add_argument('--audit',type=Path,required=True)
 a=p.parse_args()
 if a.mode=='prepare':x=prepare(a.out)
 elif a.mode=='run-arm':x=run_arm(a.manifest,a.endpoint,a.arm,a.out,a.device,a.measurement_lock,a.expected_lock_sha256,configure_runtime(a))
 elif a.mode=='audit':x=audit_bundle(a.manifest,a.control,a.treatment,a.out,a.measurement_lock,a.expected_lock_sha256)
 else:x=judge(a.manifest,a.control,a.treatment,a.audit,a.out,a.measurement_lock,a.expected_lock_sha256)
 print(json.dumps(x,indent=2,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
