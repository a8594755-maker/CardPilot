"""Real retained Adam updates from complete traces; diagnostic, not production resume."""
import copy
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(BASE.parent/'v6-regularized-full-hand-adapter-20260908'))
import importlib.util
spec=importlib.util.spec_from_file_location('full_hand_capture',BASE.parent/'v6-regularized-full-hand-adapter-20260908/qualify.py')
capture=importlib.util.module_from_spec(spec); spec.loader.exec_module(capture)
from alpha_holdem.train_mp3_hybrid_h1 import trinal_clip_ppo_update,compute_gae


def equal(a,b):
    if torch.is_tensor(a): return torch.equal(a.cpu(),b.cpu())
    if isinstance(a,dict): return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)): return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b


def transitions(trace,hero,model,eta):
    """Compress complete chronology onto hero decisions without losing future costs.

    Requires gamma=1,lambda=1 at update: target differences telescope exactly.
    Reward/value input units are raw bb; critic_v2 updater divides by200 once.
    """
    result=capture.transformed_returns([r['actor'] for r in trace['rows']],
        [r['log_policy'] for r in trace['rows']],[r['log_reference'] for r in trace['rows']],
        trace['terminal_bb'],eta)
    chosen=[i for i,r in enumerate(trace['rows']) if r['actor']==hero]
    targets=[result['returns_bb'][i][hero] for i in chosen]
    rewards=[targets[j]-(targets[j+1] if j+1<len(targets) else 0) for j in range(len(targets))]
    state=capture.ev.ChipState.new(trace['deck']); output=[]
    for i,row in enumerate(trace['rows']):
        obs,table=capture.ev._observation(model,state,'legacy_v4')
        assert state.actor==row['actor']
        if state.actor==hero:
            args=[torch.as_tensor(obs[k],dtype=torch.float32).unsqueeze(0)
                  for k in ('card_info','action_info','extra_info','legal_mask')]
            with torch.no_grad(): _,value=model(*args)
            j=len(output)
            output.append(tuple(obs[k].copy() for k in ('card_info','action_info','extra_info','legal_mask'))+
                (row['slot'],row['log_policy'],rewards[j],float(value.reshape(-1)[0])*200,
                 float(j==len(chosen)-1),200.0,200.0))
        state=capture.ev.apply_incr(state,table[row['slot']])
    assert state.terminal
    if output:
        _,actual=compute_gae([r[6]/200 for r in output],[r[7]/200 for r in output],[r[8] for r in output],gamma=1,lam=1)
        assert np.allclose(actual,np.array(targets)/200,rtol=0,atol=1e-7)
    return output


def main():
    torch.set_num_threads(1)
    source=BASE.parent/'v6-regularized-full-hand-adapter-20260908'
    raw=source/'hands.jsonl'
    assert capture.sha(raw)==json.loads((source/'result.json').read_text())['raw_sha256']
    traces=[json.loads(line)['trace'] for line in raw.read_text().splitlines()]
    old=json.loads((BASE.parent/'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    reports=[]
    for seed in ('1','3'):
        path=Path(old['parents'][seed]['path']); digest=capture.sha(path)
        assert digest==old['parents'][seed]['sha256']
        parent=capture.read_checkpoint(path)
        for eta in (0.0,0.1):
            model=capture.init_model(parent,'cpu').eval()
            model.requires_grad_(True)
            optimizer=torch.optim.Adam(model.parameters(),lr=1e-4)
            optimizer.load_state_dict(copy.deepcopy(parent['optimizer']))
            assert equal(optimizer.state_dict(),parent['optimizer'])
            data=[]; selected=0
            for trace in traces:
                if digest not in trace['bindings']['policy_sha256']: continue
                hero=trace['bindings']['policy_sha256'].index(digest)
                data.extend(transitions(trace,hero,model,eta)); selected+=1
            assert selected==8 and len(data)>1
            before=copy.deepcopy(model.state_dict())
            torch.manual_seed(202609081234)
            stats=trinal_clip_ppo_update(model,optimizer,data,'cpu',epochs=1,mini_batch_size=16384,
                gamma=1,gae_lambda=1,critic_contract='critic_v2',effective_stack_divisor=200,
                entropy_coef=.005,entropy_floor=.05,value_coef=1)
            changed=[k for k,v in model.state_dict().items() if not torch.equal(v,before[k])]
            assert changed and all(torch.isfinite(v).all() for v in model.state_dict().values())
            steps=[]
            for k,state in optimizer.state_dict()['state'].items():
                delta=float(state['step'])-float(parent['optimizer']['state'][k]['step'])
                assert delta in (0,1); steps.append(delta)
            assert max(steps)==1
            out=BASE/f'seed{seed}_eta{eta}_diagnostic.pt'
            assert not out.exists()
            torch.save(dict(model=model.state_dict(),optimizer=optimizer.state_dict(),parent_sha256=digest,
                diagnostic_only_not_production_resume=True,offline_rows=len(data),eta_bb=eta),out)
            restored=torch.load(out,map_location='cpu',weights_only=False)
            assert equal(restored['model'],model.state_dict()) and equal(restored['optimizer'],optimizer.state_dict())
            reports.append(dict(seed=seed,eta_bb=eta,rows=len(data),changed_tensors=len(changed),
                adam_states_advanced=sum(x==1 for x in steps),checkpoint_sha256=capture.sha(out),
                policy_loss=stats['policy_loss'],value_loss=stats['value_loss']))
        assert capture.sha(path)==digest
    with (BASE/'result.json').open('x') as handle:
        json.dump(dict(passed=True,reports=reports,training_hands=0,
            trace_reconstruction_executions=32,distinct_existing_decks=16,
            limitations='Diagnostic offline updates only; gamma/lambda1 and fixed clip bounds200 are explicit qualification settings, not unchanged parent recipe or production resume proof. Original counters/replay/pool remain in untouched parent artifacts.'),handle,indent=2)
    print(json.dumps(dict(passed=True,reports=reports)))


if __name__=='__main__': main()
