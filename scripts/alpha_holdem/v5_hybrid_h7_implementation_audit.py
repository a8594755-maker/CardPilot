#!/usr/bin/env python3
"""Offline audit that H7 reuses validated KL semantics and adds identity only."""
from __future__ import annotations
import argparse,copy,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
import torch
from v5_hybrid_h6_implementation_audit import TinyPolicy,equal_state,run_update,transitions
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--trainer',type=Path,required=True);p.add_argument('--ppo',type=Path,required=True);p.add_argument('--preregistration',type=Path,required=True);p.add_argument('--expected-preregistration-sha256',required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args();checks={};errors=[]
 def ck(name,value):checks[name]=bool(value);errors.append(name) if not value else None
 try:
  ck('preregistration',sha(a.preregistration)==a.expected_preregistration_sha256.lower())
  source=a.trainer.read_text(encoding='utf-8');ck('h7_cli_identity',all(token in source for token in ('--h7-window-arm','--h7-preregistration','--h7-design-lock')));ck('arm_target_contract',"expected_target = 0.03 if args.h7_window_arm == 'treatment' else 0.0" in source);ck('mutual_exclusion','H7 must not bundle or reopen H2/H6' in source);ck('exact_source_contract','H7 arms require --resume --allow-resume with optimizer reset' in source)
  torch.manual_seed(17);initial=TinyPolicy();data=transitions(initial);disabled_model,disabled=run_update(initial,data,0.);high_model,high=run_update(initial,data,1e9);ck('disabled_bitwise_equivalence',equal_state(disabled_model,high_model) and disabled['ppo_epochs_completed']==high['ppo_epochs_completed']==4 and not disabled['kl_early_stop_triggered'])
  torch.manual_seed(18);initial=TinyPolicy();data=transitions(initial);before=copy.deepcopy(initial);model,stats=run_update(initial,data,1e-12);ck('forced_trigger_after_completed_epoch',stats['kl_early_stop_triggered'] and 1<=stats['kl_early_stop_epoch']==stats['ppo_epochs_completed']<4 and not equal_state(model,before))
  result={'schema_version':'v5.hybrid.h7.implementation_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'PASS_H7_IMPLEMENTATION' if not errors else 'FAIL_CLOSED','checks':checks,'errors':errors,'source_sha256':{'trainer':sha(a.trainer),'ppo':sha(a.ppo),'preregistration':sha(a.preregistration)},'behavior_semantics':'UNCHANGED_FROM_H6_VALIDATED_IMPLEMENTATION','identity_change':'H7 fresh control/treatment immutable binding only','official_hands':0,'strength_claim':'FORBIDDEN'};rc=0 if not errors else 2
 except Exception as exc:result={'schema_version':'v5.hybrid.h7.implementation_audit.v1','checked_at':datetime.now(timezone.utc).isoformat(),'overall':'FAIL_CLOSED','errors':errors+[f'{type(exc).__name__}: {exc}'],'official_hands':0};rc=2
 a.out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8');print(json.dumps(result,indent=2,sort_keys=True));return rc
if __name__=='__main__':raise SystemExit(main())
