#!/usr/bin/env python3
"""Build/verify the immutable HYBRID H1 same-start design lock (no launch)."""
from __future__ import annotations
import argparse, base64, hashlib, json, os, stat
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT=Path(__file__).resolve().parents[2]
PREREG=ROOT/'reports/v5_hybrid_h1_preregistration_20260711.json'
PREREG_SHA='bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab'
SOURCE=ROOT/'models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709/v5_exp005_cutover_gate31400_checkpoint.pt'
SOURCE_SHA='bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e'
CAL=ROOT/'reports/h1_cal_001_attempt2_20260712'
CAL_FILES=['manifest.json','summary.json','decisions.jsonl','hands.jsonl','audit.json','audit.md']
TOOLS=['scripts/alpha_holdem/train_v5_hybrid_h1.py','scripts/alpha_holdem/train_mp3_hybrid_h1.py','scripts/alpha_holdem/network_hybrid_h1.py','scripts/alpha_holdem/v5_hybrid_h1_critic.py','scripts/alpha_holdem/v5_h1_calibration.py','scripts/alpha_holdem/v5_hybrid_h1_source_preflight.py','scripts/alpha_holdem/v5_continue_after_gate.ps1','scripts/alpha_holdem/v5_rearm_watchers.ps1','scripts/alpha_holdem/v5_monitor.py','scripts/alpha_holdem/v5_health_watch.py','scripts/alpha_holdem/v5_hybrid_h1_design_lock.py','scripts/alpha_holdem/v5_hybrid_h1_endpoint_watch.py','scripts/alpha_holdem/v5_hybrid_h1_judge.py','scripts/alpha_holdem/test_v5_hybrid_h1_orchestration.py']

def sha(p:Path)->str:
 h=hashlib.sha256();
 with p.open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''): h.update(b)
 return h.hexdigest()
def ro(p:Path)->bool:
 a=getattr(p.stat(),'st_file_attributes',0); flag=getattr(stat,'FILE_ATTRIBUTE_READONLY',0)
 return bool(a&flag) if flag else not bool(p.stat().st_mode&stat.S_IWUSR)
def ab(p:Path)->str:return str(p.resolve())
def common(run_id:str, run_dir:Path, critic:str)->dict[str,Any]:
 migration=run_dir/'h1_critic_migration.json' if critic=='critic_v2' else Path('')
 return {'device':'cuda','workers':22,'hands_per_iter':16384,'total_hands':535989661,'starting_stack':200.0,'env_version':'v55','lr':0.0003,'ppo_epochs':4,'mini_batch_size':1024,'epsilon':0.0,'seed':20260703,'worker_seed_base':73000,'fixed_training_deal_stream':True,'gamma':0.999,'delta1':3.0,'entropy_coef':0.05,'entropy_floor':0.3,'postflop_action_prior_coef':0.02,'postflop_action_prior_target':'0.15,0.30,0.52,0.03','preflop_action_prior_coef':0.01,'preflop_action_prior_target':'0.24,0.36,0.38,0.02','preflop_sb_open_action_prior_coef':0.0,'preflop_sb_open_action_prior_target':'0.15,0.20,0.63,0.02','preflop_bb_vs_open_action_prior_coef':0.0,'preflop_bb_vs_open_action_prior_target':'0.25,0.55,0.18,0.02','k_best':5,'pool_strategy':'loss-kbest','pool_history_limit':200,'self_play_fraction':0.2,'opponent_assignment':'per-iteration','opponent_groups':5,'snapshot_every':200,'save_interval':1,'rollout_mode':'multi','rollout_envs_per_worker':16,'inference_min_batch_slots':256,'inference_batch_deadline_us':1000,'mirror_self_play_deals':True,'allin_runout_ev':True,'allin_runout_ev_max_runouts':200,'reset_optimizer':False,'assignment_provenance_schema':'v5.opponent_assignment_provenance.v1','critic_contract':critic,'h1_effective_stack_divisor':200.0,'h1_critic_init_seed':2026071102,'value_coef':1.0 if critic=='critic_v2' else 0.5,'h1_preregistration':ab(PREREG),'h1_preregistration_sha256':PREREG_SHA,'h1_migration_report':ab(migration) if critic=='critic_v2' else ''}
def verify(lock:dict[str,Any],lock_path:Path|None=None,expected_sha:str|None=None,planned:dict|None=None,arm:str|None=None)->dict:
 cs=[]
 def ck(n,c,d=''):cs.append({'name':n,'status':'PASS' if c else 'FAIL','detail':d})
 ck('schema',lock.get('schema_version')=='v5.hybrid.h1.design_lock.v1'); ck('status',lock.get('status')=='LOCKED')
 if lock_path and expected_sha:
  ck('lock_sha',sha(lock_path)==expected_sha.lower())
  ledger=(ROOT/'reports/v5_experiment_ledger.md').read_bytes(); binding=lock.get('ledger_binding',{}); n=int(binding.get('prefix_bytes',0))
  ck('ledger_prefix',n<=len(ledger) and hashlib.sha256(ledger[:n]).hexdigest()==binding.get('prefix_sha256'))
  text=ledger.decode('utf-8',errors='replace'); marker='[event_id='+str(binding.get('event_id'))+']'
  ck('ledger_event_chain',marker in text and expected_sha.lower() in text.lower())
 ck('prereg',sha(PREREG)==PREREG_SHA and lock.get('preregistration',{}).get('sha256')==PREREG_SHA)
 ck('source',sha(SOURCE)==SOURCE_SHA and lock.get('source_checkpoint',{}).get('sha256')==SOURCE_SHA)
 cal=lock.get('calibration',{}); aud=json.loads((CAL/'audit.json').read_text(encoding='utf-8'))
 ck('calibration_audit',aud.get('status')=='PASS_IMMUTABLE_HOLDOUT' and cal.get('status')=='PASS_IMMUTABLE_HOLDOUT')
 for name in CAL_FILES: ck('cal_'+name,sha(CAL/name)==cal.get('files',{}).get(name) and ro(CAL/name))
 for item in lock.get('tools',[]): ck('tool_'+item['path'],sha(ROOT/item['path'])==item['sha256'])
 arms=lock.get('arms',{}); c=arms.get('control',{}).get('expected_config',{}); t=arms.get('treatment',{}).get('expected_config',{})
 dif=sorted(k for k in set(c)|set(t) if c.get(k)!=t.get(k)); ck('atomic_package',dif==['critic_contract','h1_migration_report','value_coef'],str(dif))
 ck('contracts',c.get('critic_contract')=='critic_v1' and c.get('value_coef')==.5 and t.get('critic_contract')=='critic_v2' and t.get('value_coef')==1.0 and t.get('h1_effective_stack_divisor')==200.0)
 ck('budget',lock.get('arm_budget')=={'actual_hands_each':20000000,'minimum_endpoint_hands':535989661,'maximum_single_arm_overshoot_hands':50000,'sequential_order':['control','treatment']})
 ck('official_block',lock.get('authority',{}).get('official_slumbot_hands')==0 and lock.get('authority',{}).get('slumbot_paths')=='TERMINAL_BLOCKED')
 if planned is not None and arm: ck('planned_config',planned==arms.get(arm,{}).get('expected_config'))
 return {'checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS' if all(x['status']=='PASS' for x in cs) else 'FAIL','checks':cs}
def build()->dict:
 aud=json.loads((CAL/'audit.json').read_text(encoding='utf-8')); assert aud['status']=='PASS_IMMUTABLE_HOLDOUT'
 arms={}
 for name,critic in [('control','critic_v1'),('treatment','critic_v2')]:
  rid=({'control':'v5_hybrid_h1_control_criticv1_same31400_20m_r1_20260711','treatment':'v5_hybrid_h1_treatment_criticv2_same31400_20m_r1_20260711'}[name]); rd=ROOT/'models/alpha_holdem_v5_hybrid'/rid
  arms[name]={'run_id':rid,'run_dir':ab(rd),'provenance_path':ab(rd/'opponent_assignment_provenance.jsonl'),'expected_config':common(rid,rd,critic)}
 ledger=(ROOT/'reports/v5_experiment_ledger.md').read_bytes()
 return {'schema_version':'v5.hybrid.h1.design_lock.v1','design_id':'H1','lock_revision':3,'status':'LOCKED','revision_scope':'WATCHER_ONLY_CONTROL_PLANE_REPAIR_BEHAVIOR_AND_ARM_CONFIGS_UNCHANGED','supersedes':{'path':'reports/v5_hybrid_h1_design_lock_v2_20260712.json','sha256':'dea7a470d2a30e1b93060feae67d7c86a6c2dce2056435ef1c063506cf711a26'},'active_control_rebind_authority':'SAME_RUN_ID_CONFIG_AND_SOURCE_ONLY','locked_at':datetime.now(timezone.utc).isoformat(),'preregistration':{'path':ab(PREREG),'sha256':PREREG_SHA},'source_checkpoint':{'path':ab(SOURCE),'sha256':SOURCE_SHA,'iteration':31400,'hands':515989661},'calibration':{'path':ab(CAL),'status':aud['status'],'training_use':'FORBIDDEN_HOLDOUT_ONLY','files':{n:sha(CAL/n) for n in CAL_FILES}},'trainer_sha256':sha(ROOT/'scripts/alpha_holdem/train_v5_hybrid_h1.py'),'tools':[{'path':p,'sha256':sha(ROOT/p)} for p in TOOLS],'arm_budget':{'actual_hands_each':20000000,'minimum_endpoint_hands':535989661,'maximum_single_arm_overshoot_hands':50000,'sequential_order':['control','treatment']},'arms':arms,'gates':{'mse_point_min':.15,'bootstrap_lower_min':.10,'bootstrap_repetitions':10000,'bootstrap_seed':2026071112,'throughput_ratio_min':.85,'throughput_first_rows':60,'entropy_window_rows':200,'entropy_treatment_min':.3,'entropy_median_drop_max':.10},'authority':{'official_slumbot_hands':0,'slumbot_paths':'TERMINAL_BLOCKED','launch_order':'CONTROL_THEN_TREATMENT_AFTER_CONTROL_ENDPOINT_PASS'},'ledger_binding':{'prefix_bytes':len(ledger),'prefix_sha256':hashlib.sha256(ledger).hexdigest(),'event_id':'v5-hybrid-h1-design-lock-v3-published-20260712'}}
def main()->int:
 p=argparse.ArgumentParser(); sub=p.add_subparsers(dest='cmd',required=True); b=sub.add_parser('build'); b.add_argument('--out',required=True); v=sub.add_parser('verify'); v.add_argument('--lock',required=True);v.add_argument('--expected-sha');v.add_argument('--planned-config-base64');v.add_argument('--arm',choices=['control','treatment']);v.add_argument('--out')
 a=p.parse_args()
 if a.cmd=='build':
  out=Path(a.out); payload=build(); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(sha(out)); return 0
 lockp=Path(a.lock); planned=json.loads(base64.b64decode(a.planned_config_base64)) if a.planned_config_base64 else None; r=verify(json.loads(lockp.read_text(encoding='utf-8')),lockp,a.expected_sha,planned,a.arm)
 if a.out:Path(a.out).write_text(json.dumps(r,indent=2,sort_keys=True)+'\n',encoding='utf-8')
 print(json.dumps(r,indent=2)); return 0 if r['overall']=='PASS' else 1
if __name__=='__main__':raise SystemExit(main())