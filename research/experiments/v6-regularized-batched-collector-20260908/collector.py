"""Complete chronology with batched inference; no terminal replay forwards."""
import importlib.util
import json
from pathlib import Path
import random
import time
import numpy as np
import torch

BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('online_engine',BASE.parent/'v6-regularized-online-resume-20260908/online.py')
online=importlib.util.module_from_spec(spec); spec.loader.exec_module(online)
c=online.c


@torch.no_grad()
def forward(model, observations, device):
    args=[torch.as_tensor(np.stack([o[k] for o in observations]),device=device)
          for k in ('card_info','action_info','extra_info','legal_mask')]
    logits,value=model(*args)
    logs=logits.double().masked_fill(args[-1]<=0,-torch.inf).log_softmax(-1)
    return logs.cpu().numpy(),value.flatten().cpu().numpy()*200


@torch.no_grad()
def collect(model,reference,namespace,start,hands,eta,device='cpu'):
    assert hands>0 and start>=0
    states=[]; traces=[]; observations=[[] for _ in range(hands)]; values=[[] for _ in range(hands)]
    for i in range(hands):
        cursor=start+i; deal_key=online.key(namespace,cursor)
        deck=list(range(52)); random.Random(deal_key).shuffle(deck)
        states.append(c.ev.ChipState.new(deck))
        traces.append(dict(deck=deck,key=deal_key,hero=cursor%2,rows=[]))
    while True:
        active=[i for i,s in enumerate(states) if not s.terminal]
        if not active: break
        obs={}; tables={}
        for i in active: obs[i],tables[i]=c.ev._observation(model,states[i],'legacy_v4')
        refs,_=forward(reference,[obs[i] for i in active],device)
        ref_by={i:refs[j] for j,i in enumerate(active)}
        heroes=[i for i in active if states[i].actor==traces[i]['hero']]
        hero_by={}; val_by={}
        if heroes:
            logs,vals=forward(model,[obs[i] for i in heroes],device)
            hero_by={i:logs[j] for j,i in enumerate(heroes)}
            val_by={i:float(vals[j]) for j,i in enumerate(heroes)}
        for i in active:
            actor=states[i].actor; trace=traces[i]
            logs=hero_by[i] if i in hero_by else ref_by[i]
            count=sum(r['actor']==actor for r in trace['rows'])
            u=c.ev.action_uniform(trace['key'],0,actor,count)
            slot=c.ev.legal_slot(logs,obs[i]['legal_mask'],u)
            trace['rows'].append(dict(index=len(trace['rows']),actor=actor,slot=slot,
                uniform=u,log_policy=float(logs[slot]),log_reference=float(ref_by[i][slot])))
            if i in hero_by:
                observations[i].append(obs[i]); values[i].append(val_by[i])
            states[i]=c.ev.apply_incr(states[i],tables[i][slot])
    data=[]
    for i,trace in enumerate(traces):
        state=states[i]; hero=trace['hero']; rs=trace['rows']
        trace['terminal_bb']=[x/100 for x in state.payoffs()]
        committed=[(state.initial[p]-state.stacks[p])/100 for p in (0,1)]
        trace['terminal_commitments_bb']=committed
        targets=c.transformed_returns([r['actor'] for r in rs],[r['log_policy'] for r in rs],
            [r['log_reference'] for r in rs],trace['terminal_bb'],eta)['returns_bb']
        indices=[j for j,r in enumerate(rs) if r['actor']==hero]
        for j,index in enumerate(indices):
            target=targets[index][hero]
            reward=target-(targets[indices[j+1]][hero] if j+1<len(indices) else 0)
            shift=target-trace['terminal_bb'][hero]
            bounds=(committed[hero]-shift,committed[1-hero]+shift)
            assert -bounds[0]-1e-8<=target<=bounds[1]+1e-8
            obs=observations[i][j]
            data.append(tuple(obs[k] for k in ('card_info','action_info','extra_info','legal_mask'))+
                (rs[index]['slot'],rs[index]['log_policy'],reward,values[i][j],float(j+1==len(indices)))+bounds)
    return traces,data


def main():
    torch.set_num_threads(1)
    inputs=json.loads((BASE.parent/'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    reports=[]
    with (BASE/'hands.jsonl').open('x') as raw:
        for seed in ('1','3'):
            e=online.Engine(inputs['parents'][seed]['path'],inputs['anchors']['standard10']['path'],
                f'batched-collector-20260908-seed{seed}',.1)
            assert e.parent_sha==inputs['parents'][seed]['sha256']
            started=time.perf_counter()
            batch,data=collect(e.model,e.reference,e.contract['namespace'],0,64,.1)
            batch_seconds=time.perf_counter()-started
            started=time.perf_counter(); max_log_difference=0
            for trace in batch:
                pair=[e.reference,e.reference]; pair[trace['hero']]=e.model
                serial=c.capture(pair,e.reference,trace['deck'],trace['key'],{})
                assert serial['terminal_bb']==trace['terminal_bb']
                assert len(serial['rows'])==len(trace['rows'])
                for a,b in zip(serial['rows'],trace['rows']):
                    assert all(a[k]==b[k] for k in ('actor','slot','index','uniform'))
                    for k in ('log_policy','log_reference'):
                        difference=abs(a[k]-b[k]); max_log_difference=max(max_log_difference,difference)
                        assert difference<2e-4
            serial_seconds=time.perf_counter()-started
            for trace in batch: raw.write(json.dumps(dict(seed=seed,trace=trace))+'\n')
            raw.flush()
            # Verify real retained Adam update from the collected arrays.
            stats=online.adapter.trinal_clip_ppo_update(e.model,e.optimizer,data,'cpu',
                epochs=1,mini_batch_size=16384,gamma=1,gae_lambda=1,critic_contract='critic_v2',
                effective_stack_divisor=200,entropy_coef=.005,entropy_floor=.05,value_coef=1)
            assert all(torch.isfinite(v).all() for v in e.model.state_dict().values())
            reports.append(dict(seed=seed,batch_seconds=batch_seconds,serial_capture_seconds=serial_seconds,
                batch_hands_per_second=64/batch_seconds,rows=len(data),max_log_difference=max_log_difference,
                update_finite=True,policy_loss=stats['policy_loss']))
    with (BASE/'result.json').open('x') as handle:
        json.dump(dict(passed=True,reports=reports,live_batch_hands=128,serial_comparison_hands=128,
            unique_decks=128,training_updates=2,raw_sha=c.sha(BASE/'hands.jsonl')) ,handle,indent=2)
    print(json.dumps(reports))


if __name__=='__main__': main()
