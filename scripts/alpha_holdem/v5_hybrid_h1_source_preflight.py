#!/usr/bin/env python3
"""Offline source-bound preflight for HYBRID H1 critic-v2; never starts workers."""
from __future__ import annotations
import argparse, copy, hashlib, io, json, math, sys
from pathlib import Path
import numpy as np
import torch

THIS_DIR=Path(__file__).resolve().parent
sys.path.insert(0,str(THIS_DIR))
sys.path.insert(0,str(THIS_DIR.parent))
from alpha_holdem.network_hybrid_h1 import AlphaHoldemNet,CRITIC_V1,CRITIC_V2
from alpha_holdem.train_mp3_hybrid_h1 import compute_gae,prepare_h1_critic_arrays,trinal_clip_ppo_update
from v5_hybrid_h1_critic import actor_key,initialize_model,migrate_v1_checkpoint_to_v2

SOURCE_SHA='bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e'
PREREG_SHA='bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab'

def sha(path:Path)->str:
    d=hashlib.sha256();
    with path.open('rb') as h:
        for chunk in iter(lambda:h.read(1024*1024),b''): d.update(chunk)
    return d.hexdigest()

def fixed_inputs(batch=8):
    g=torch.Generator().manual_seed(2026071103)
    return torch.randn(batch,6,4,13,generator=g),torch.randn(batch,25,4,5,generator=g),torch.randn(batch,2,generator=g),torch.ones(batch,9)

def optimizer_name_state(model,optimizer):
    return {name:copy.deepcopy(optimizer.state.get(param,{})) for name,param in model.named_parameters()}

def equal_value(left,right):
    if type(left) is not type(right): return False
    if isinstance(left,torch.Tensor): return torch.equal(left.detach().cpu(),right.detach().cpu())
    if isinstance(left,dict): return left.keys()==right.keys() and all(equal_value(left[k],right[k]) for k in left)
    if isinstance(left,(list,tuple)): return len(left)==len(right) and all(equal_value(a,b) for a,b in zip(left,right))
    return left==right

def synthetic_transitions(model):
    model.eval(); rows=[]
    for i in range(8):
        card=np.zeros((6,4,13),np.float32); action=np.zeros((25,4,5),np.float32); extra=np.array([1,1],np.float32); mask=np.ones(9,np.float32)
        with torch.no_grad(): logits,value=model(torch.tensor(card).unsqueeze(0),torch.tensor(action).unsqueeze(0),torch.tensor(extra).unsqueeze(0),torch.tensor(mask).unsqueeze(0)); lp=torch.log_softmax(logits,dim=-1)[0,1].item()
        done=1.0 if i in (3,7) else 0.0; reward=(20.0 if i==3 else (-10.0 if i==7 else 0.0)); raw_value=float(value.item()*200.0)
        rows.append((card,action,extra,mask,1,lp,reward,raw_value,done,200.0,200.0,1.0 if done else 0.0))
    return rows

def run(source:Path,prereg:Path)->dict:
    checks=[]
    def add(name,passed,detail=''): checks.append({'name':name,'pass':bool(passed),'detail':detail})
    add('source_sha',sha(source)==SOURCE_SHA,sha(source)); add('prereg_sha',sha(prereg)==PREREG_SHA,sha(prereg))
    ckpt=torch.load(source,map_location='cpu',weights_only=False)
    add('source_identity',ckpt.get('iteration')==31400 and ckpt.get('total_hands')==515989661 and ckpt.get('env_version')=='v55' and ckpt.get('obs_version')=='v55','gate31400')
    control=AlphaHoldemNet(critic_contract=CRITIC_V1); initialize_model(control); control.load_state_dict(ckpt['model']); control_optimizer=torch.optim.Adam(control.parameters(),lr=3e-4); control_optimizer.load_state_dict(ckpt['optimizer'])
    treatment=AlphaHoldemNet(critic_contract=CRITIC_V2,critic_init_seed=2026071102); initialize_model(treatment); treatment_optimizer=torch.optim.Adam(treatment.parameters(),lr=3e-4)
    migration=migrate_v1_checkpoint_to_v2(model=treatment,optimizer=treatment_optimizer,checkpoint=ckpt,device='cpu'); add('migration',migration.get('status')=='PASS' and migration.get('new_critic_optimizer_state_count')==0,json.dumps(migration,sort_keys=True))
    control.eval(); treatment.eval(); values=fixed_inputs()
    with torch.no_grad(): c_logits,_=control(*values); t_logits,_=treatment(*values)
    delta=float((c_logits-t_logits).abs().max().item()); add('policy_logits_bitwise',torch.equal(c_logits,t_logits) and delta==0.0,str(delta))
    actor_exact=all(torch.equal(treatment.state_dict()[name],ckpt['model'][name]) for name in treatment.state_dict() if actor_key(name)); add('actor_state_bitwise',actor_exact)
    source_opt=optimizer_name_state(control,control_optimizer); target_opt=optimizer_name_state(treatment,treatment_optimizer)
    actor_opt_exact=all(equal_value(source_opt[name],target_opt[name]) for name in target_opt if actor_key(name)); critic_empty=all(not target_opt[name] for name in target_opt if not actor_key(name)); add('actor_optimizer_bitwise',actor_opt_exact); add('critic_optimizer_empty',critic_empty)
    treatment.zero_grad(set_to_none=True); _,v=treatment(*values); v.square().mean().backward(); isolated=all(param.grad is None for name,param in treatment.named_parameters() if actor_key(name)) and any(param.grad is not None for name,param in treatment.named_parameters() if not actor_key(name)); add('critic_gradient_isolation',isolated)
    duplicate=AlphaHoldemNet(critic_contract=CRITIC_V2,critic_init_seed=2026071102); initialize_model(duplicate); deterministic=all(torch.equal(a,b) for a,b in zip(treatment.value_head.state_dict().values(),duplicate.value_head.state_dict().values())); add('deterministic_critic_init',deterministic)
    buffer=io.BytesIO(); torch.save({'model':treatment.state_dict(),'critic_contract':CRITIC_V2},buffer); buffer.seek(0); loaded=torch.load(buffer,map_location='cpu',weights_only=False); restored=AlphaHoldemNet(critic_contract=CRITIC_V2); initialize_model(restored); restored.load_state_dict(loaded['model']); add('checkpoint_roundtrip',all(torch.equal(a,b) for a,b in zip(treatment.state_dict().values(),restored.state_dict().values())))
    rewards=np.array([0.,0.,80.]); old=np.array([2.,3.,4.]); done=np.array([0.,0.,1.]); chips=np.array([200.,200.,200.]); raw_adv,raw_ret=compute_gae(rewards,old,done); r,vv,d2,d3,scale=prepare_h1_critic_arrays(rewards,old,chips,chips,critic_contract=CRITIC_V2,effective_stack_divisor=200.); norm_adv,norm_ret=compute_gae(r,vv,done); add('scaling_gae_bounds',np.allclose(norm_adv,raw_adv/200) and np.allclose(norm_ret,raw_ret/200) and np.allclose(d2,1) and np.allclose(d3,1) and scale==200)
    smoke=AlphaHoldemNet(critic_contract=CRITIC_V2); initialize_model(smoke); smoke_opt=torch.optim.Adam(smoke.parameters(),lr=3e-4); stats=trinal_clip_ppo_update(smoke,smoke_opt,synthetic_transitions(smoke),'cpu',epochs=1,mini_batch_size=4,critic_contract=CRITIC_V2,effective_stack_divisor=200.,value_coef=1.,entropy_coef=0.,action_prior_coef=0.,preflop_action_prior_coef=0.); finite=all(math.isfinite(float(stats[k])) for k in ('policy_loss','value_loss','value_loss_raw_bb_equivalent','entropy','approx_kl')); add('cpu_ppo_smoke',finite and stats['critic_contract']==CRITIC_V2,json.dumps({k:stats[k] for k in ('policy_loss','value_loss','value_loss_raw_bb_equivalent','entropy')},sort_keys=True))
    failed=[row for row in checks if not row['pass']]; return {'schema_version':'v5.hybrid.h1.source_preflight.v1','status':'PASS_NO_LAUNCH' if not failed else 'FAIL_CLOSED','checks':checks,'passed':len(checks)-len(failed),'failed':len(failed),'failed_checks':[row['name'] for row in failed],'source_sha256':sha(source),'preregistration_sha256':sha(prereg),'migration':migration,'policy_logits_max_abs_delta':delta,'launch_authority':'NONE','official_hands_authorized':0}

def main():
    p=argparse.ArgumentParser(); p.add_argument('--source',required=True); p.add_argument('--preregistration',required=True); p.add_argument('--out-json',required=True); a=p.parse_args(); result=run(Path(a.source),Path(a.preregistration)); Path(a.out_json).write_text(json.dumps(result,indent=2,sort_keys=True)+'\n',encoding='utf-8'); print(json.dumps(result,indent=2)); return 0 if result['status'].startswith('PASS_') else 2
if __name__=='__main__': raise SystemExit(main())