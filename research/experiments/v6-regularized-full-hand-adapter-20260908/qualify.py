"""Complete-hand capture and fail-closed replay, frozen policies, no updates."""
import copy
import hashlib
import json
from pathlib import Path
import random
import sys
import time

import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908'))
sys.path.insert(0,str(BASE.parent/'v6-regularized-return-kernel-20260908'))
import sampled_eval as ev
from regularized_return import transformed_returns
from alpha_holdem.v5_mirror_eval import init_model,read_checkpoint


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


@torch.no_grad()
def distribution(model,state):
    obs,table=ev._observation(model,state,'legacy_v4')
    args=[torch.as_tensor(obs[k],dtype=torch.float32).unsqueeze(0)
          for k in ('card_info','action_info','extra_info','legal_mask')]
    logits,_=model(*args)
    logs=logits[0].double().masked_fill(args[-1][0]<=0,-torch.inf).log_softmax(-1)
    return logs,obs['legal_mask'],table


def capture(models,reference,deck,key,bindings):
    state=ev.ChipState.new(deck); rows=[]; counts=[0,0]
    while not state.terminal:
        actor=state.actor
        logs,mask,table=distribution(models[actor],state)
        ref,_,_=distribution(reference,state)
        uniform=ev.action_uniform(key,0,actor,counts[actor])
        slot=ev.legal_slot(logs.numpy(),mask,uniform)
        rows.append(dict(index=len(rows),actor=actor,slot=slot,uniform=uniform,
                         log_policy=float(logs[slot]),log_reference=float(ref[slot])))
        counts[actor]+=1; state=ev.apply_incr(state,table[slot])
    return dict(schema='complete-regularized-hand-v1',deck=deck,key=key,bindings=bindings,
                epsilon=0.0,temperature=1.0,replay=False,rows=rows,
                terminal_bb=[float(x)/100 for x in state.payoffs()])


def validate(trace,models,reference,bindings):
    assert trace['schema']=='complete-regularized-hand-v1'
    assert trace['bindings']==bindings
    assert trace['epsilon']==0 and trace['temperature']==1 and trace['replay'] is False
    assert len(trace['deck'])==52 and set(trace['deck'])==set(range(52))
    state=ev.ChipState.new(trace['deck']); counts=[0,0]
    for index,row in enumerate(trace['rows']):
        assert not state.terminal and row['index']==index and row['actor']==state.actor
        actor=state.actor
        logs,mask,table=distribution(models[actor],state)
        ref,_,_=distribution(reference,state)
        uniform=ev.action_uniform(trace['key'],0,actor,counts[actor])
        assert row['uniform']==uniform
        assert row['slot']==ev.legal_slot(logs.numpy(),mask,uniform)
        assert row['log_policy']==float(logs[row['slot']])
        assert row['log_reference']==float(ref[row['slot']])
        counts[actor]+=1; state=ev.apply_incr(state,table[row['slot']])
    assert state.terminal,'incomplete hand chronology'
    assert trace['terminal_bb']==[float(x)/100 for x in state.payoffs()]
    output=transformed_returns([r['actor'] for r in trace['rows']],
        [r['log_policy'] for r in trace['rows']],[r['log_reference'] for r in trace['rows']],
        trace['terminal_bb'],0.1)
    assert all(abs(sum(x))<1e-9 for x in output['returns_bb'])
    return output


def main():
    assert not (BASE/'hands.jsonl').exists()
    started=time.perf_counter(); torch.set_num_threads(1)
    old=json.loads((BASE.parent/'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    paths={s:Path(x['path']) for s,x in old['parents'].items()}
    paths['ref']=Path(old['anchors']['standard10']['path'])
    hashes={str(p):sha(p) for p in paths.values()}
    for s in ('1','3'): assert hashes[str(paths[s])]==old['parents'][s]['sha256']
    assert hashes[str(paths['ref'])]==old['anchors']['standard10']['sha256']
    models={s:init_model(read_checkpoint(p),'cpu').eval() for s,p in paths.items()}
    sources={str(p):sha(p) for p in [Path(__file__),BASE.parent/'v6-regularized-return-kernel-20260908/regularized_return.py',BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908/sampled_eval.py']}
    with (BASE/'inputs.json').open('x') as handle: json.dump(dict(hashes=hashes,sources=sources),handle,indent=2)
    hands=0; decisions=0; guard_cases=0
    with (BASE/'hands.jsonl').open('x',encoding='utf-8') as handle:
        for s in ('1','3'):
            for seat in (0,1):
                for index in range(4):
                    key=202609089000+int(s)*100+seat*10+index
                    deck=list(range(52)); random.Random(key).shuffle(deck)
                    pair=[models['ref'],models['ref']]; pair[seat]=models[s]
                    bindings=dict(policy_sha256=[hashes[str(paths[s])] if p==seat else hashes[str(paths['ref'])] for p in (0,1)],reference_sha256=hashes[str(paths['ref'])])
                    trace=capture(pair,models['ref'],deck,key,bindings); hands+=1
                    returns=validate(trace,pair,models['ref'],bindings); hands+=1
                    decisions+=len(trace['rows'])
                    handle.write(json.dumps(dict(trace=trace,targets=returns))+'\n'); handle.flush()
                    # Each mutation must fail before completing another hand.
                    for field,value in [('epsilon',0.1),('replay',True),('temperature',0.5),('bindings',{})]:
                        bad=copy.deepcopy(trace); bad[field]=value
                        try: validate(bad,pair,models['ref'],bindings)
                        except AssertionError: guard_cases+=1
                        else: raise AssertionError('unsupported trace accepted')
                    bad=copy.deepcopy(trace); bad['rows']=bad['rows'][:-1]
                    try: validate(bad,pair,models['ref'],bindings)
                    except AssertionError: guard_cases+=1
                    else: raise AssertionError('truncated chronology accepted')
    for name,digest in {**hashes,**sources}.items(): assert sha(Path(name))==digest
    result=dict(passed=True,collection_hands=16,replay_validation_hands=16,
        completed_fixture_hands=hands,unique_decks=16,decisions=decisions,guard_cases=guard_cases,
        wall_seconds=time.perf_counter()-started,raw_sha256=sha(BASE/'hands.jsonl'),
        scope='Complete-hand on-policy capture and deterministic replay only; no optimizer, training integration or strength claim. Rejected truncated validation prefixes are not completed hands.')
    with (BASE/'result.json').open('x') as handle: json.dump(result,handle,indent=2)
    print(json.dumps(result))


if __name__=='__main__': main()
