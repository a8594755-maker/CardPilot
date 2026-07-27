#!/usr/bin/env python3
"""Fail-closed terminal H2 judgment. Reporting only; launches nothing."""
from __future__ import annotations
import argparse, hashlib, json, statistics
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
import numpy as np
from v5_h1_calibration import endpoint_predictions

TOOL=Path(__file__).resolve(); PREREG_SHA='aaf8bf30db6e757e15c1b9ae1bdd0b5e3eed379ec1dadbd23b2d8a70b1f2fa2f'; REPS=10000; MSE_SEED=2026071405
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(8<<20),b''):h.update(b)
 return h.hexdigest()
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def rows(p):
 with Path(p).open(encoding='utf-8') as f:return [json.loads(x) for x in f if x.strip()]
def effective(xs,first60=False):
 ys=xs[1:61] if first60 else xs[1:]
 if len(ys)<2:return None
 dt=(datetime.fromisoformat(ys[-1]['recorded_at'])-datetime.fromisoformat(ys[0]['recorded_at'])).total_seconds()
 return (int(ys[-1]['hands'])-int(ys[0]['hands']))/dt if dt>0 else None
def mse_comparison(control_cp:Path,treatment_cp:Path,holdout:Path,device:str)->dict[str,Any]:
 rs=rows(holdout/'decisions.jsonl');c=endpoint_predictions(control_cp,rs,device);t=endpoint_predictions(treatment_cp,rs,device);deals=sorted(set(c)&set(t))
 if len(deals)!=10000:raise ValueError('MSE holdout deal coverage mismatch')
 ca=np.array([c[d] for d in deals]);ta=np.array([t[d] for d in deals]);point=float(ta.mean()/ca.mean()-1);rng=np.random.default_rng(MSE_SEED);s=np.empty(REPS)
 for i in range(REPS):
  idx=rng.integers(0,len(deals),len(deals));s[i]=float(ta[idx].mean()/ca[idx].mean()-1)
 lo,hi=map(float,np.quantile(s,[.025,.975]));return {'deal_clusters':len(deals),'control_normalized_mse':float(ca.mean()),'treatment_normalized_mse':float(ta.mean()),'relative_degradation':point,'ci95_lower':lo,'ci95_upper':hi,'bootstrap_repetitions':REPS,'bootstrap_seed':MSE_SEED}
def verify_lock(path:Path,expected:str)->dict[str,Any]:
 if sha(path)!=expected.lower():raise ValueError('judgment lock SHA mismatch')
 x=load(path)
 if x.get('design_id')!='H2-JUDGMENT-001' or x.get('status')!='LOCKED' or x.get('tool_sha256')!=sha(TOOL):raise ValueError('judgment lock identity/tool binding')
 for item in x.get('frozen_files',[]):
  if not Path(item['path']).is_file() or sha(item['path'])!=item['sha256']:raise ValueError('judgment frozen file mismatch '+item['path'])
 return x
def endpoint(status_path:Path,arm:str):
 s=load(status_path)
 if s.get('overall')!='PASS' or s.get('state')!='ARM_ENDPOINT_FROZEN' or s.get('arm')!=arm:raise ValueError(f'{arm} endpoint status invalid')
 cp=Path(s['checkpoint_path'])
 if not cp.is_file() or sha(cp)!=s.get('checkpoint_sha256'):raise ValueError(f'{arm} endpoint checkpoint hash')
 return s,cp
def classify(checks:dict[str,bool],mse:dict,mirror:dict)->tuple[str,str]:
 if not checks['throughput_first60']:return 'FAIL','H2_FAIL_PROTOCOL_ABORT_FIRST60_THROUGHPUT'
 fail=(not checks['endpoint_mse_point'] or not checks['endpoint_mse_ci_upper'] or not checks['throughput_full'] or not checks['entropy_floor'] or not checks['entropy_noninferior'] or mirror.get('status')=='FAIL')
 if fail:return 'FAIL','H2_FAIL_REGISTERED_GUARD'
 if all(checks.values()) and mirror.get('status')=='PASS':return 'PASS','H2_PASS_ALL_REGISTERED_GATES'
 return 'INCONCLUSIVE','H2_INCONCLUSIVE_FIXED_SAMPLE'
def main():
 p=argparse.ArgumentParser();p.add_argument('--judgment-lock',required=True);p.add_argument('--expected-lock-sha256',required=True);p.add_argument('--control-status',required=True);p.add_argument('--treatment-status',required=True);p.add_argument('--mirror-judgment',required=True);p.add_argument('--out',required=True);p.add_argument('--device',choices=['cpu','cuda'],default='cuda');a=p.parse_args();outp=Path(a.out)
 try:
  lock=verify_lock(Path(a.judgment_lock),a.expected_lock_sha256);cs,ccp=endpoint(Path(a.control_status),'control');ts,tcp=endpoint(Path(a.treatment_status),'treatment');mirror=load(a.mirror_judgment)
  if mirror.get('schema_version')!='v5.hybrid.h2.mirror_judgment.v1':raise ValueError('mirror judgment identity')
  holdout=Path(lock['holdout_dir']);mse=mse_comparison(ccp,tcp,holdout,a.device);cr=rows(lock['control_metrics']);tr=rows(lock['treatment_metrics']);c60=effective(cr,True);t60=effective(tr,True);cf=effective(cr);tf=effective(tr);r60=t60/c60 if c60 and t60 else None;rf=tf/cf if cf and tf else None;ce=statistics.median(float(x['entropy']) for x in cr[-200:]);te=statistics.median(float(x['entropy']) for x in tr[-200:])
  var=load(lock['h2_var_summary']);checks={'offline_variance_point':float(var['variance_reduction_point'])>=.30,'offline_variance_ci_lower':float(var['variance_reduction_ci95_lower'])>=.20,'offline_bias_point':float(var['mean_bias_abs_point'])<=.01,'offline_bias_ci_upper':float(var['mean_bias_abs_ci95_upper'])<=.02,'endpoint_mse_point':mse['relative_degradation']<=.05,'endpoint_mse_ci_upper':mse['ci95_upper']<=.10,'mirror_noninferiority':mirror.get('status')=='PASS','throughput_first60':r60 is not None and r60>=.85,'throughput_full':rf is not None and rf>=.85,'entropy_floor':te>=.3,'entropy_noninferior':te>=ce-.10}
  verdict,classification=classify(checks,mse,mirror);out={'schema_version':'v5.hybrid.h2.judgment.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':verdict,'classification':classification,'checks':checks,'endpoint_mse':mse,'mirror':mirror,'control_effective_hps_first60':c60,'treatment_effective_hps_first60':t60,'throughput_ratio_first60':r60,'control_effective_hps_full':cf,'treatment_effective_hps_full':tf,'throughput_ratio_full':rf,'control_entropy_median_last200':ce,'treatment_entropy_median_last200':te,'control_endpoint':cs,'treatment_endpoint':ts,'judgment_lock_sha256':sha(a.judgment_lock),'official_hands':0,'strength_claim':'FORBIDDEN','route_review_required':verdict in ('FAIL','INCONCLUSIVE')};rc=0
 except Exception as exc:
  out={'schema_version':'v5.hybrid.h2.judgment.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'INCONCLUSIVE','classification':'FAIL_CLOSED_MISSING_OR_INVALID_EVIDENCE','errors':[f'{type(exc).__name__}: {exc}'],'official_hands':0,'strength_claim':'FORBIDDEN'};rc=2
 outp.parent.mkdir(parents=True,exist_ok=True);outp.write_text(json.dumps(out,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(out,indent=2,sort_keys=True));return rc
if __name__=='__main__':raise SystemExit(main())
