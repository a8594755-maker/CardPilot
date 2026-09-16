"""Independent terminal raw/accounting/Adam checks; zero new environment hands."""
import hashlib
import json
from pathlib import Path
import random
import sys
import torch

BASE=Path(__file__).resolve().parent
def read(p): return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as h: return hashlib.file_digest(h,'sha256').hexdigest()


def main(stage):
    inputs=read(BASE/'inputs.json'); reports=[]; decks=set(); total=0
    assert sha(BASE/'train.py')==inputs['train_sha']
    assert sha(BASE/'protocol.md')==inputs['protocol_sha']
    for path,digest in inputs['sources'].items(): assert sha(Path(path))==digest
    target={1:16384,2:65536}[stage]
    for seed in ('1','3'):
        parent_info=inputs['inputs']['parents'][seed]; parent_path=Path(parent_info['path'])
        assert sha(parent_path)==parent_info['sha256']
        parent=torch.load(parent_path,map_location='cpu',weights_only=False)
        matched=None
        for label in ('control','regularized'):
            folder=BASE/f'seed{seed}_{label}'; manifest=read(folder/'manifest.json')
            previous=sha(folder/'initial.pt'); assert previous==manifest['initial_sha']
            cursor=0; transitions=0; rows=0; keys=[]; wall=0
            for index in range(target//2048):
                update=folder/f'update-{index:06d}'
                intent=read(update/'intent.json'); commit=read(update/'commit.json')
                assert intent==dict(start=cursor,hands=2048,parent_checkpoint_sha=previous)
                assert commit['intent_sha']==sha(update/'intent.json')
                assert commit['raw_sha']==sha(update/'hands.jsonl')
                raw=[json.loads(line) for line in (update/'hands.jsonl').read_text().splitlines()]
                assert len(raw)==2048
                for j,trace in enumerate(raw):
                    namespace=f'regularized-return-pilot-20260908-train-seed{seed}'
                    key=int.from_bytes(hashlib.sha256(f'{namespace}:{cursor+j}'.encode()).digest()[:16],'big')
                    deck=list(range(52)); random.Random(key).shuffle(deck)
                    assert trace['key']==key and trace['deck']==deck and trace['hero']==(cursor+j)%2
                    assert abs(sum(trace['terminal_bb']))<1e-9 and all(abs(x)<=200 for x in trace['terminal_bb'])
                    hero_rows=sum(r['actor']==trace['hero'] for r in trace['rows'])
                    transitions+=bool(hero_rows); rows+=hero_rows
                    keys.append(key); decks.add(tuple(deck))
                cursor+=2048; assert commit['cursor']==cursor and commit['hands']==2048
                previous=sha(update/'checkpoint.pt'); assert previous==commit['checkpoint_sha']
                wall+=commit['wall_seconds']
            endpoint=read(BASE/f'stage{stage}_seed{seed}_{label}.json')
            assert endpoint['sha256']==previous and endpoint['hands']==target
            state=torch.load(endpoint['path'],map_location='cpu',weights_only=False)
            assert state['cursor']==cursor and state['updates']==target//2048
            assert state['transition_hands']==transitions and state['transition_rows']==rows
            assert state['optimizer']['param_groups']==parent['optimizer']['param_groups']
            deltas=[float(s['step'])-float(parent['optimizer']['state'][k]['step']) for k,s in state['optimizer']['state'].items()]
            assert len(deltas)==86 and set(deltas)=={target//2048}
            assert all(torch.isfinite(v).all() for v in state['model'].values())
            if matched is None: matched=keys
            else: assert keys==matched
            reports.append(dict(seed=seed,arm=label,hands=cursor,transition_hands=transitions,
                rows=rows,adam_states_advanced=86,adam_step_delta=target//2048,update_wall_seconds=wall))
            total+=cursor
    assert total==4*target and len(decks)==2*target
    with (BASE/f'stage{stage}_training_review.json').open('x') as h:
        json.dump(dict(passed=True,reports=reports,physical_hands=total,unique_decks=len(decks),
            limitations='Raw identity, transaction, terminal ranges and retained Adam accounting audit, not full decision replay or strength proof.'),h,indent=2)
    print(json.dumps(dict(passed=True,hands=total,unique_decks=len(decks))))


if __name__=='__main__': main(int(sys.argv[1]))
