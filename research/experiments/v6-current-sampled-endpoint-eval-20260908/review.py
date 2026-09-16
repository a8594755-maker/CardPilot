"""Independent ordered raw-evidence review; no evaluator import or poker execution."""
import hashlib
import json
import math
from pathlib import Path
import random
import statistics

BASE = Path(__file__).resolve().parent


def sha(path):
    with path.open('rb') as handle: return hashlib.file_digest(handle,'sha256').hexdigest()


def stats(values):
    assert len(values)>1 and all(math.isfinite(x) for x in values)
    mean=statistics.mean(values)*100
    half=1.96*statistics.stdev(values)*100/math.sqrt(len(values))
    return dict(bb100=mean,ci95_low_bb100=mean-half,ci95_high_bb100=mean+half,samples=len(values))


def validate_row(row,seed,name,a,index,deck,label,seat,action_seed):
    for key,value in dict(seed=seed,anchor=name,anchor_index=a,pair_index=index,
        deck=deck,policy=label,seat=seat,action_seed=action_seed).items():
        assert row[key]==value,(key,row.get(key),value)
    reward=row['reward_bb']
    assert isinstance(reward,(int,float)) and not isinstance(reward,bool)
    assert math.isfinite(reward) and -200 <= reward <= 200
    assert isinstance(row['decisions'],int) and not isinstance(row['decisions'],bool) and row['decisions']>0


def summarize(rows):
    output={'pooled':stats([(x['delta'][0]+x['delta'][1])/2 for x in rows]),
            'by_seat':{str(s):stats([x['delta'][s] for x in rows]) for s in (0,1)}}
    for panel,predicate in (('preservation',lambda x:x['a']<4),('transfer',lambda x:x['a']>=4)):
        subset=[x for x in rows if predicate(x)]
        output[panel]=stats([(x['delta'][0]+x['delta'][1])/2 for x in subset])
    output['by_anchor']={str(a):stats([(x['delta'][0]+x['delta'][1])/2 for x in rows if x['a']==a]) for a in range(8)}
    return output


def main():
    terminal=json.loads((BASE/'terminal.json').read_text())
    assert terminal['status']=='RAW_REVIEW_REQUIRED' and terminal['hands']==65536
    contract=json.loads((BASE/'contract.json').read_text())
    assert contract['expected_hands']==65536 and contract['planned_decks']==16384 and contract['overlap']==0
    for name,digest in contract['hashes'].items(): assert sha(Path(name))==digest,name
    assert sha(BASE/'hands.jsonl')==terminal['raw_sha256']
    assert list(contract['anchors'])==['standard10','cfr4','legacy_iter16','legacy_mixed65k','mixture_s1','mixture_s3','heads_s1','heads_s3']
    results={}; seen=set(); count=0
    with (BASE/'hands.jsonl').open(encoding='utf-8') as handle:
        for seed in (1,3):
            pairs=[]
            for a,name in enumerate(contract['anchors']):
                rng=random.Random({1:202609087101,3:202609087301}[seed]+a*1000003)
                action_seed={1:202609088101,3:202609088301}[seed]+a*1000003
                for index in range(1024):
                    deck=list(range(52)); rng.shuffle(deck)
                    assert tuple(deck) not in seen; seen.add(tuple(deck))
                    rewards={}
                    for label in ('parent','endpoint'):
                        for seat in (0,1):
                            row=json.loads(next(handle))
                            validate_row(row,seed,name,a,index,deck,label,seat,action_seed)
                            rewards[label,seat]=row['reward_bb']; count+=1
                    pairs.append(dict(a=a,delta=[rewards['endpoint',s]-rewards['parent',s] for s in (0,1)]))
            results[str(seed)]=summarize(pairs)
        assert not handle.read().strip(),'unexpected extra raw evidence'
    assert count==65536 and len(seen)==16384
    positive=all(results[s][p]['bb100']>0 for s in ('1','3') for p in ('pooled','preservation','transfer'))
    negative_seat=any(all(results[s]['by_seat'][seat]['bb100']<0 for s in ('1','3')) for seat in ('0','1'))
    output=dict(passed=True,evaluation_hands=count,unique_decks=len(seen),by_seed=results,
        directional_support=positive and not negative_seat,
        raw_sha256=terminal['raw_sha256'],contract_sha256=sha(BASE/'contract.json'),
        reviewer_sha256=sha(Path(__file__)),
        scope='Prescribed raw sequence, deck/action keys, counts, finite bounded rewards and immutable inputs; not full decision-level replay or unseen-opponent/external strength.',
        ci_scope='Conditional unadjusted normal 95 percent intervals on paired deck seat averages.')
    with (BASE/'raw_review.json').open('x',encoding='utf-8') as handle: json.dump(output,handle,indent=2)
    print(json.dumps(dict(passed=True,directional_support=output['directional_support'],
        contrasts={s:v['pooled'] for s,v in results.items()})))


if __name__=='__main__': main()
