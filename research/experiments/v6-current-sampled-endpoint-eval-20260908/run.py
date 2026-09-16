"""Prepare or execute the frozen sampled endpoint comparison."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PREV = BASE.parent/'v6-independent-critic-two-seed-geometric-20260908'
QUAL = BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908'
sys.path.insert(0,str(QUAL))
import sampled_eval as ev
import torch
from alpha_holdem.v5_mirror_eval import init_model, read_checkpoint


def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()
def write(path,value):
    with path.open('x',encoding='utf-8') as handle: json.dump(value,handle,indent=2)
def decks(seed,anchor):
    rng=random.Random({1:202609087101,3:202609087301}[seed]+1000003*anchor)
    for i in range(1024):
        deck=list(range(52)); rng.shuffle(deck)
        yield i,deck
def verify(contract):
    for name,digest in contract['hashes'].items(): assert sha(Path(name))==digest,name


def prepare():
    assert read(QUAL/'qualification.json')['passed']
    for name,digest in read(QUAL/'qualification.json')['source_hashes'].items():
        assert sha(Path(name))==digest,name
    old=read(PREV/'input_contract.json')
    endpoints={}
    for seed in (1,3):
        folder=PREV/f'seed{seed}_control_stage2'
        review=read(folder/'independent_review.json')
        assert review['passed']
        endpoints[str(seed)]={'path':str(folder/'latest.pt'),'sha256':review['checkpoint_sha256']}
    planned={tuple(deck) for seed in (1,3) for a in range(8) for _,deck in decks(seed,a)}
    assert len(planned)==16384
    corpus=dict(old['prior_gzip'])
    corpus.update({str(p):sha(p) for p in PREV.glob('eval_*/common_deck_pairs.jsonl.gz')})
    count=0
    for inventory,opener in ((corpus,gzip.open),(old['prior_plain'],open)):
        for name,digest in inventory.items():
            assert sha(Path(name))==digest,name
            with opener(name,'rt',encoding='utf-8') as handle:
                for line in handle:
                    assert tuple(json.loads(line)['deck']) not in planned
                    count+=1
    for row in read(QUAL/'qualification.json')['rows']:
        assert tuple(row['outcome']['deck']) not in planned
    hashes={str(p.resolve()):sha(p) for p in (ROOT/'scripts/alpha_holdem').glob('*.py')}
    for p in (BASE/'run.py',BASE/'protocol.md',QUAL/'sampled_eval.py',QUAL/'qualification.json'):
        hashes[str(p)]=sha(p)
    for item in [*old['parents'].values(),*endpoints.values(),*old['anchors'].values()]:
        assert sha(Path(item['path']))==item['sha256']
        hashes[item['path']]=item['sha256']
    contract=dict(parents=old['parents'],endpoints=endpoints,anchors=old['anchors'],
        hashes=hashes,prior_gzip=corpus,prior_plain=old['prior_plain'],prior_rows=count,
        planned_decks=16384,expected_hands=65536,overlap=0)
    write(BASE/'contract.json',contract)
    print(json.dumps(dict(preflight=True,prior_rows=count,planned_decks=16384)))


def update(count):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
                    '--count',f'evaluation_hands={count}'],cwd=ROOT,check=True,capture_output=True)


def run():
    contract=read(BASE/'contract.json'); verify(contract)
    assert len(contract['anchors'])==8
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started=time.perf_counter(); last=started; count=0
    write(BASE/'owner.json',dict(pid=os.getpid(),started_at=time.time(),command=sys.argv))
    with (BASE/'hands.jsonl').open('x',encoding='utf-8') as raw:
        for seed in (1,3):
            parent=init_model(read_checkpoint(Path(contract['parents'][str(seed)]['path'])),'cuda').eval()
            endpoint=init_model(read_checkpoint(Path(contract['endpoints'][str(seed)]['path'])),'cuda').eval()
            for a,(name,item) in enumerate(contract['anchors'].items()):
                anchor=init_model(read_checkpoint(Path(item['path'])),'cuda').eval()
                action_seed={1:202609088101,3:202609088301}[seed]+1000003*a
                for index,deck in decks(seed,a):
                    for label,model in (('parent',parent),('endpoint',endpoint)):
                        for seat in (0,1):
                            reward,decisions=ev.play_hand(model,anchor,deck,candidate_seat=seat,
                                action_seed=action_seed,pair_index=index,device='cuda')
                            row=dict(seed=seed,anchor=name,anchor_index=a,pair_index=index,
                                deck=deck,policy=label,seat=seat,reward_bb=reward,
                                decisions=decisions,action_seed=action_seed)
                            raw.write(json.dumps(row,separators=(',',':'))+'\n'); raw.flush()
                            count+=1
                    if time.perf_counter()-last>=60:
                        os.fsync(raw.fileno()); update(count); last=time.perf_counter()
                print(json.dumps(dict(seed=seed,anchor=name,hands=count)),flush=True)
            update(count)
        os.fsync(raw.fileno())
    verify(contract); assert count==65536
    write(BASE/'terminal.json',dict(hands=count,wall_seconds=time.perf_counter()-started,
        raw_sha256=sha(BASE/'hands.jsonl'),status='RAW_REVIEW_REQUIRED'))


if __name__=='__main__':
    if sys.argv[1:] == ['prepare']: prepare()
    elif sys.argv[1:] == ['run']: run()
    else: raise SystemExit('expected prepare or run')
