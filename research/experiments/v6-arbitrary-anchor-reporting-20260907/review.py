"""Retained evidence only. Exclusive audit output, no poker simulation."""
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys
import time
from paired_summary import summarize, severe

BASE=Path(__file__).resolve().parent
TRIAL=BASE.parent/'v6-family-allocation-two-seed-geometric-20260907'

def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
    if not ok: raise ValueError(msg)
def check(actual,prior):
    for level in ('pooled','by_anchor','by_seat'):
        a={'pooled':actual[level]} if level=='pooled' else actual[level]
        b={'pooled':prior[level]} if level=='pooled' else prior[level]
        require(a.keys()==b.keys(),'buckets')
        for k,v in a.items():
            target=b[k]
            require(v['samples']==target['paired_decks'],'sample count')
            require(math.isclose(v['bb100'],target['bb100'],abs_tol=1e-8) and all(math.isclose(v[n],target['ci95'][i],abs_tol=1e-8) for i,n in enumerate(('ci95_low_bb100','ci95_high_bb100'))),'raw CI mismatch')

def empty_buckets(obj,path='$'):
    if isinstance(obj,dict):
        if isinstance(obj.get('by_anchor'),dict):
            bad=[k for k,v in obj['by_anchor'].items() if isinstance(v,dict) and v.get('samples',v.get('paired_decks',1))==0]
            if bad: yield dict(location=path,zero_sample_anchors=bad)
        for k,v in obj.items(): yield from empty_buckets(v,path+'.'+k)
    elif isinstance(obj,list):
        for i,v in enumerate(obj): yield from empty_buckets(v,f'{path}[{i}]')

def main():
    start=time.monotonic(); out=BASE/'review.json'; require(not out.exists(),'preserve output')
    hashes={str(p):sha(p) for p in BASE.glob('*.py')}
    correction=read(TRIAL/'post_terminal_review.json'); hashes[str(TRIAL/'post_terminal_review.json')]=sha(TRIAL/'post_terminal_review.json')
    anchors=read(TRIAL/'qualification.json')['anchors']; names=list(anchors)
    groups={'preservation':names[:4],'adaptation':names[4:]}; checks=[]
    for stage in (1,2):
        for seed in (1,3):
            arms={}
            for arm in ('control','expanded'):
                p=TRIAL/f'eval_seed{seed}_{arm}_stage{stage}/common_deck_pairs.jsonl.gz'
                hashes[str(p)]=sha(p)
                with gzip.open(p,'rt',encoding='utf-8') as f: arms[arm]=[json.loads(x) for x in f]
            right={(r['anchor'],r['anchor_seed'],r['pair_index']):r for r in arms['expanded']}
            joined=[]
            for r in arms['control']:
                t=right[(r['anchor'],r['anchor_seed'],r['pair_index'])]
                require(r['deck']==t['deck'] and r['control_rewards_bb']==t['control_rewards_bb'],'pairing')
                delta=[b-a for a,b in zip(r['treatment_rewards_bb'],t['treatment_rewards_bb'])]
                joined.append({**r,'control_rewards_bb':r['treatment_rewards_bb'],'treatment_rewards_bb':t['treatment_rewards_bb'],'treatment_minus_control_rewards_bb':delta,'treatment_minus_control_pair_mean_bb':sum(delta)/2})
            for group,panel in groups.items():
                prior=correction['stages'][str(stage)][str(seed)][group]
                summaries=[]
                for rows,target in ((joined,prior['connected_minus_detached']),(arms['control'],prior['endpoint_minus_parent']['detached']),(arms['expanded'],prior['endpoint_minus_parent']['connected'])):
                    s=summarize([r for r in rows if r['anchor'] in panel],anchors=panel,pairs_per_anchor=1024)
                    check(s,target); summaries.append(s)
                gate=any(severe(s,minimum_bad_anchors=3) for s in summaries)
                require(gate==prior['broad_collapse'],'gate')
                checks.append(dict(stage=stage,seed=seed,panel=group,summary_comparisons=3,severe_gate=gate))
    inventory=[]; suspect=[]; errors=[]
    patterns=('stage*_analysis.json','raw_review.json','controller_result.json')
    for folder in sorted(BASE.parent.iterdir()):
        if not folder.is_dir() or folder==BASE: continue
        for p in sorted({p for pattern in patterns for p in folder.glob(pattern)}):
            digest=sha(p); hashes[str(p)]=digest
            inventory.append(str(p))
            try: bad=list(empty_buckets(read(p)))
            except (ValueError,UnicodeError) as e: errors.append(dict(path=str(p),error=str(e))); continue
            if bad: suspect.append(dict(path=str(p),buckets=bad))
    require(all(sha(p)==h for p,h in hashes.items()),'evidence changed')
    report=dict(passed=True,command=sys.orig_argv,real_panel_checks=checks,summary_comparisons=sum(x['summary_comparisons'] for x in checks),historical_scope=inventory,suspect_reports=suspect,parse_errors=errors,input_sha256=hashes,training_hands=0,evaluation_hands=0,final_qualification_hands=0,wall_seconds=time.monotonic()-start,scope='Top-level stage*_analysis.json/raw_review.json/controller_result.json in retained experiment directories only. Zero-sample buckets are suspect, not automatic causal/strength invalidation. Nested, archived and other-named summaries excluded; no exhaustive historical clean claim. Candidate is opt-in, frozen historical imports unchanged.')
    with out.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(dict(passed=True,summary_comparisons=report['summary_comparisons'],reports_scanned=len(inventory),suspect_reports=[x['path'] for x in suspect],parse_errors=errors,wall_seconds=report['wall_seconds'])))

if __name__=='__main__': main()
