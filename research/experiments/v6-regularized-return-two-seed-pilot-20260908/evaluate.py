"""Freeze and evaluate fixed three-policy endpoints; never train from these hands."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time
import numpy as np
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
sys.path.insert(0,str(BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908'))
import sampled_eval as ev
from alpha_holdem.v5_mirror_eval import read_checkpoint,init_model


def read(p): return json.loads(Path(p).read_text())
def sha(p):
    with Path(p).open('rb') as h: return hashlib.file_digest(h,'sha256').hexdigest()
def write(p,x):
    with Path(p).open('x') as h: json.dump(x,h,indent=2)
def deals(stage,seed,anchor):
    for index in range(512):
        text=f'regularized-return-pilot-20260908-eval:{stage}:{seed}:{anchor}:{index}'
        key=int.from_bytes(hashlib.sha256(text.encode()).digest()[:16],'big')
        deck=list(range(52)); random.Random(key).shuffle(deck)
        yield index,key,deck
def verify(contract):
    for name,digest in contract['hashes'].items(): assert sha(name)==digest,name


def prepare(stage):
    assert read(BASE/f'stage{stage}_training_terminal.json')['status']=='FROZEN_EVALUATION_REQUIRED'
    old=read(BASE/'inputs.json')['inputs']
    policies={}
    for seed in ('1','3'):
        policies[seed]={'parent':old['parents'][seed]}
        for label in ('control','regularized'):
            policies[seed][label]=read(BASE/f'stage{stage}_seed{seed}_{label}.json')
    planned={tuple(d) for seed in ('1','3') for a in old['anchors'] for _,_,d in deals(stage,seed,a)}
    assert len(planned)==8192
    # Existing inventory covers earlier research; add subsequent trace corpora and
    # all current training batches. Missing required evidence is an error.
    previous=read(BASE.parent/'v6-current-sampled-endpoint-eval-20260908/contract.json')
    files={Path(p):gzip.open for p in previous['prior_gzip']}
    files.update({Path(p):open for p in previous['prior_plain']})
    for folder in BASE.parent.glob('v6-*20260908'):
        for p in folder.rglob('*hands.jsonl'): files[p]=open
    count=0; deck_rows=0
    for path,opener in files.items():
        with opener(path,'rt',encoding='utf-8') as h:
            for line in h:
                row=json.loads(line); count+=1
                trace=row.get('trace',row)
                if 'deck' in trace:
                    assert tuple(trace['deck']) not in planned,(str(path),'overlap')
                    deck_rows+=1
    hashes={str(p):sha(p) for p in (ROOT/'scripts/alpha_holdem').glob('*.py')}
    for p in (Path(__file__),Path(ev.__file__),BASE/'protocol.md'): hashes[str(p)]=sha(p)
    for item in [*old['anchors'].values(),*[v for ps in policies.values() for v in ps.values()]]:
        assert sha(item['path'])==item['sha256']
        hashes[item['path']]=item['sha256']
    write(BASE/f'stage{stage}_evaluation_contract.json',dict(stage=stage,policies=policies,
        anchors=old['anchors'],hashes=hashes,planned_decks=8192,hands=49152,
        prior_files=len(files),prior_rows=count,prior_deck_rows=deck_rows,
        scope='No overlap in inventoried available deck-bearing raw rows; not a universal inventory of unrecorded history.'))


def run(stage):
    contract=read(BASE/f'stage{stage}_evaluation_contract.json'); verify(contract)
    torch.set_num_threads(1); started=time.perf_counter(); last=started; count=0
    write(BASE/f'stage{stage}_evaluation_owner.json',dict(pid=os.getpid(),started_at=time.time()))
    raw_path=BASE/f'stage{stage}_evaluation_hands.jsonl'
    with raw_path.open('x') as raw:
        for seed,policies in contract['policies'].items():
            parent=read_checkpoint(Path(policies['parent']['path']))
            models={}
            for label,item in policies.items():
                model=init_model(parent,'cuda').eval()
                if label!='parent': model.load_state_dict(torch.load(item['path'],map_location='cpu',weights_only=False)['model'])
                models[label]=model
            for name,item in contract['anchors'].items():
                opponent=init_model(read_checkpoint(Path(item['path'])),'cuda').eval()
                for index,key,deck in deals(stage,seed,name):
                    for label,model in models.items():
                        for seat in (0,1):
                            reward,decisions=ev.play_hand(model,opponent,deck,candidate_seat=seat,
                                action_seed=key,pair_index=0,device='cuda')
                            raw.write(json.dumps(dict(seed=seed,anchor=name,index=index,key=key,deck=deck,
                                policy=label,seat=seat,reward_bb=reward,decisions=decisions))+'\n')
                            raw.flush(); count+=1
                    if time.perf_counter()-last>=60:
                        os.fsync(raw.fileno())
                        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
                            '--count',f'evaluation_hands={(stage-1)*49152+count}'],check=True,capture_output=True)
                        last=time.perf_counter()
                print(json.dumps(dict(stage=stage,seed=seed,anchor=name,hands=count)),flush=True)
        os.fsync(raw.fileno())
    assert count==49152; verify(contract)
    write(BASE/f'stage{stage}_evaluation_terminal.json',dict(hands=count,raw_sha=sha(raw_path),
        wall_seconds=time.perf_counter()-started,status='RAW_REVIEW_REQUIRED'))


def interval(values):
    a=np.array(values,dtype=float)*100; mean=float(a.mean())
    half=1.96*float(a.std(ddof=1))/len(a)**.5
    return dict(bb100=mean,ci95=[mean-half,mean+half],paired_decks=len(a))


def review(stage):
    contract=read(BASE/f'stage{stage}_evaluation_contract.json'); verify(contract)
    raw=BASE/f'stage{stage}_evaluation_hands.jsonl'; terminal=read(BASE/f'stage{stage}_evaluation_terminal.json')
    assert sha(raw)==terminal['raw_sha']; count=0; reports={}
    with raw.open() as h:
        for seed in contract['policies']:
            contrasts={label:{} for label in ('regularized_minus_control','control_minus_parent','regularized_minus_parent')}
            for anchor in contract['anchors']:
                bucket={k:[] for k in contrasts}
                for index,key,deck in deals(stage,seed,anchor):
                    cells={}
                    for label in ('parent','control','regularized'):
                        for seat in (0,1):
                            row=json.loads(next(h)); count+=1
                            assert all(row[k]==v for k,v in dict(seed=seed,anchor=anchor,index=index,key=key,deck=deck,policy=label,seat=seat).items())
                            assert np.isfinite(row['reward_bb']) and abs(row['reward_bb'])<=200
                            assert isinstance(row['decisions'],int) and row['decisions']>0
                            cells[label,seat]=row['reward_bb']
                    for k in bucket:
                        a,b=k.split('_minus_')
                        bucket[k].append([(cells[a,s]-cells[b,s]) for s in (0,1)])
                for k in bucket: contrasts[k][anchor]=bucket[k]
            reports[seed]={}
            for k,anchors in contrasts.items():
                all_rows=[r for rows in anchors.values() for r in rows]
                names=list(anchors)
                reports[seed][k]=dict(pooled=interval([sum(r)/2 for r in all_rows]),
                    preservation=interval([sum(r)/2 for a in names[:4] for r in anchors[a]]),
                    transfer=interval([sum(r)/2 for a in names[4:] for r in anchors[a]]),
                    seats=[interval([r[s] for r in all_rows]) for s in (0,1)],
                    per_anchor={a:interval([sum(r)/2 for r in rows]) for a,rows in anchors.items()})
            assert all(len(v)==8 for v in contrasts.values())
        assert not h.read().strip()
    assert count==49152
    write(BASE/f'stage{stage}_evaluation_review.json',dict(passed=True,hands=count,reports=reports,
        limitations='Conditional unadjusted paired-deck normal95% intervals; known related anchors; descriptive developmental evidence, not Slumbot or causal long-run rejection. Ordered raw audit is not full decision replay.'))


if __name__=='__main__':
    {'prepare':prepare,'run':run,'review':review}[sys.argv[1]](int(sys.argv[2]))
