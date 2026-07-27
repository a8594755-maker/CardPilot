#!/usr/bin/env python3
"""Fail-closed terminal H7 judgment using fresh contemporaneous arms."""
from __future__ import annotations

import argparse, hashlib, json, statistics
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from v5_h1_calibration import endpoint_predictions
from v5_h6_ppo_stability_readiness import parse_rows

REPS=10000;MSE_SEED=2026071702;PREREG_SHA='45b57f4fe817f1b98e7267a8e482d46b8121fb41d4e432a8af25a1857c6cb4b7';TOOL=Path(__file__).resolve()
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(8<<20),b''):h.update(block)
 return h.hexdigest()
def load(path):return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def rows(path):
 with Path(path).open(encoding='utf-8') as f:return [json.loads(line) for line in f if line.strip()]
def effective(values,first60=False):
 sample=values[1:61] if first60 else values[1:]
 if len(sample)<2:return None
 elapsed=(datetime.fromisoformat(sample[-1]['recorded_at'])-datetime.fromisoformat(sample[0]['recorded_at'])).total_seconds()
 return (int(sample[-1]['hands'])-int(sample[0]['hands']))/elapsed if elapsed>0 else None
def endpoint(status_path,arm):
 status=load(status_path)
 if status.get('overall')!='PASS' or status.get('state')!='ARM_ENDPOINT_FROZEN' or status.get('arm')!=arm:raise ValueError(f'{arm} endpoint status')
 checkpoint=Path(status['checkpoint_path'])
 if not checkpoint.is_file() or sha(checkpoint)!=status.get('checkpoint_sha256'):raise ValueError(f'{arm} endpoint hash')
 return status,checkpoint
def mse(control,treatment,holdout,device):
 values=rows(holdout/'decisions.jsonl');c=endpoint_predictions(control,values,device);t=endpoint_predictions(treatment,values,device);deals=sorted(set(c)&set(t))
 if len(deals)!=10000:raise ValueError('MSE holdout deal coverage')
 ca=np.array([c[d] for d in deals]);ta=np.array([t[d] for d in deals]);point=float(ta.mean()/ca.mean()-1);rng=np.random.default_rng(MSE_SEED);samples=np.empty(REPS)
 for i in range(REPS):
  idx=rng.integers(0,len(deals),len(deals));samples[i]=float(ta[idx].mean()/ca[idx].mean()-1)
 lo,hi=map(float,np.quantile(samples,[.025,.975]));return {'deal_clusters':len(deals),'control_normalized_mse':float(ca.mean()),'treatment_normalized_mse':float(ta.mean()),'relative_degradation':point,'ci95_lower':lo,'ci95_upper':hi,'bootstrap_repetitions':REPS,'bootstrap_seed':MSE_SEED}
def verify_lock(path,expected):
 if sha(path)!=expected.lower():raise ValueError('design lock SHA')
 lock=load(path)
 if lock.get('design_id')!='H7' or lock.get('status')!='LOCKED' or lock.get('preregistration',{}).get('sha256')!=PREREG_SHA:raise ValueError('design lock identity')
 if lock.get('tools',{}).get('scripts/alpha_holdem/v5_hybrid_h7_judge.py')!=sha(TOOL):raise ValueError('judge tool binding')
 for item in lock.get('frozen_files',[]):
  path=Path(item['path'])
  if not path.is_file() or sha(path)!=item['sha256']:raise ValueError('frozen artifact '+str(path))
 return lock
def main():
 p=argparse.ArgumentParser();p.add_argument('--design-lock',type=Path,required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--control-status',type=Path,required=True);p.add_argument('--treatment-status',type=Path,required=True);p.add_argument('--control-protocol',type=Path,required=True);p.add_argument('--treatment-protocol',type=Path,required=True);p.add_argument('--mirror-judgment',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--device',choices=['cpu','cuda'],default='cuda');a=p.parse_args()
 try:
  lock=verify_lock(a.design_lock,a.expected_lock_sha256);cp=load(a.control_protocol) if a.control_protocol.is_file() else {};tp=load(a.treatment_protocol) if a.treatment_protocol.is_file() else {}
  terminal=next((x for x in (cp,tp) if x.get('overall')=='FAIL'),None)
  if terminal:
   state=str(terminal.get('state',''))
   if 'RESOURCE_ISOLATION' in state:verdict,classification='INCONCLUSIVE','H7_INCONCLUSIVE_RESOURCE_ISOLATION_VIOLATION'
   elif state.startswith('H7_FAIL_PROTOCOL_ABORT_'):verdict,classification='FAIL',state
   else:raise ValueError('unrecognized protocol terminal')
   result={'schema_version':'v5.hybrid.h7.judgment.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':verdict,'classification':classification,'protocol_terminal':terminal,'design_lock_sha256':sha(a.design_lock),'official_hands':0,'strength_claim':'FORBIDDEN','route_review_required':True};rc=0
  else:
   expected_control='PASS_CONTROL_BASELINE_FROZEN'
   if cp.get('overall')!='PASS' or cp.get('first60',{}).get('status')!=expected_control or tp.get('overall')!='PASS' or tp.get('first60',{}).get('status')!='PASS':raise ValueError('protocol statuses not terminal PASS')
   cs,cc=endpoint(a.control_status,'control');ts,tc=endpoint(a.treatment_status,'treatment');mirror=load(a.mirror_judgment)
   if mirror.get('schema_version')!='v5.hybrid.h7.mirror_judgment.v1':raise ValueError('mirror identity')
   m=mse(cc,tc,Path(lock['measurement']['holdout_dir']),a.device);cr=rows(lock['arms']['control']['metrics_path']);tr=rows(lock['arms']['treatment']['metrics_path']);c60=effective(cr,True);t60=effective(tr,True);cf=effective(cr);tf=effective(tr);r60=t60/c60 if c60 and t60 else None;rf=tf/cf if cf and tf else None;ce=statistics.median(float(x['entropy']) for x in cr[-200:]);te=statistics.median(float(x['entropy']) for x in tr[-200:])
   ckl=np.asarray([float(x['approx_kl']) for x in parse_rows(Path(lock['arms']['control']['train_log_path']).read_text(encoding='utf-8-sig',errors='replace'))]);tkl=np.asarray([float(x['approx_kl']) for x in parse_rows(Path(lock['arms']['treatment']['train_log_path']).read_text(encoding='utf-8-sig',errors='replace'))])
   if len(ckl)!=len(cr) or len(tkl)!=len(tr):raise ValueError('KL row coverage')
   control_frac=float((ckl>.03).mean());treat_frac=float((tkl>.03).mean());frac_max=min(.5*control_frac,.06044407894736842);triggers=sum(bool(x.get('kl_early_stop_triggered')) for x in tr);trigger_frac=triggers/len(tr)
   kl={'control_rows':len(ckl),'treatment_rows':len(tkl),'control_p95':float(np.quantile(ckl,.95)),'treatment_p95':float(np.quantile(tkl,.95)),'control_fraction_above_0_03':control_frac,'treatment_fraction_above_0_03':treat_frac,'registered_treatment_fraction_max':frac_max,'early_stop_triggers':triggers,'early_stop_trigger_fraction':trigger_frac}
   checks={'kl_p95':kl['treatment_p95']<=.03,'kl_excursion_fraction':treat_frac<=frac_max,'early_stop_trigger_fraction':trigger_frac>=.05,'endpoint_mse_point':m['relative_degradation']<=.05,'endpoint_mse_ci_upper':m['ci95_upper']<=.10,'mirror_noninferiority':mirror.get('status')=='PASS','throughput_first60':r60 is not None and r60>=.85,'throughput_full':rf is not None and rf>=.85,'entropy_floor':te>=.3,'entropy_noninferior':te>=ce-.10,'resource_isolation':cp.get('resource_isolation_violations')==[] and tp.get('resource_isolation_violations')==[]}
   if mirror.get('status')=='FAIL' or any(not v for k,v in checks.items() if k!='mirror_noninferiority'):verdict,classification='FAIL','H7_FAIL_REGISTERED_GATE'
   elif all(checks.values()) and mirror.get('status')=='PASS':verdict,classification='PASS','H7_PASS_ALL_REGISTERED_GATES'
   else:verdict,classification='INCONCLUSIVE','H7_INCONCLUSIVE_FIXED_SAMPLE'
   result={'schema_version':'v5.hybrid.h7.judgment.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':verdict,'classification':classification,'checks':checks,'kl_stability':kl,'endpoint_mse':m,'mirror':mirror,'control_effective_hps_first60':c60,'treatment_effective_hps_first60':t60,'throughput_ratio_first60':r60,'control_effective_hps_full':cf,'treatment_effective_hps_full':tf,'throughput_ratio_full':rf,'control_entropy_median_last200':ce,'treatment_entropy_median_last200':te,'control_endpoint':cs,'treatment_endpoint':ts,'design_lock_sha256':sha(a.design_lock),'official_hands':0,'strength_claim':'FORBIDDEN','route_review_required':verdict in {'FAIL','INCONCLUSIVE'}};rc=0
 except Exception as exc:
  result={'schema_version':'v5.hybrid.h7.judgment.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'INCONCLUSIVE','classification':'FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE','errors':[f'{type(exc).__name__}: {exc}'],'official_hands':0,'strength_claim':'FORBIDDEN'};rc=2
 a.out.parent.mkdir(parents=True,exist_ok=True);a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2,sort_keys=True));return rc
if __name__=='__main__':raise SystemExit(main())
