"""Terminal-only raw reconstruction; fixed-family stratified paired intervals."""
import gzip
import json
import math
import random
import statistics as st
import sys
import time
import psutil
import run_eval as t

def live(p,ct):
    try: return abs(psutil.Process(int(p)).create_time()-ct)<.001
    except psutil.NoSuchProcess: return False
def estimate(groups):
    n=len(groups); means=[st.mean(x) for x in groups]
    se=math.sqrt(sum(st.variance(x)/len(x) for x in groups))/n
    m=st.mean(means)*100; h=1.96*se*100
    return {'bb100':m,'ci95_low':m-h,'ci95_high':m+h,'pairs':sum(map(len,groups))}
def main():
    started=time.perf_counter(); out=t.BASE/'raw_review.json'
    t.require(not out.exists(),'preserve review')
    owner=t.read(t.BASE/'ownership.json')
    t.require(owner['pid']==6964 and abs(owner['create_time']-1788796848.2704518)<.001 and not live(owner['pid'],owner['create_time']),'owner not terminal')
    result=t.read(t.BASE/'controller_result.json')
    t.require(result['phase']=='COMPLETE_REQUIRES_RAW_REVIEW' and not (t.BASE/'controller_error.json').exists(),'bad terminal')
    q=t.read(t.BASE/'preflight.json'); hashes=dict(q['input_sha256']); t.ex.check_hashes(hashes)
    for p in (t.Path(__file__),t.BASE/'preflight.json',t.BASE/'controller_result.json',t.BASE/'ownership.json'): hashes[str(p)]=t.sha(p)
    t.require(estimate([[1,1],[3,3]])['bb100']==200 and estimate([[1,1],[3,3]])['ci95_low']==200,'estimator selfcheck')
    seen=set(); output={}; jobwall=0
    for seed in (1,3):
        arms={}
        for arm in ('control','mixture'):
            folder=t.BASE/f'eval_seed{seed}_{arm}'; job=t.BASE/f'job_seed{seed}_{arm}'
            term=t.read(job/'termination.json'); process=t.read(job/'process.json')
            t.require(term['exit_code']==0 and not term['observer_errors'] and not term['remaining_observed_child_pids'],'unclean job')
            t.require(not live(process['pid'],process['create_time']) and all(not live(p,ct) for p,ct in term['observed_children'].items()),'live child')
            t.require(t.read(job/'command.json')==t.command(seed,arm,q),'changed command'); jobwall+=term['wall_seconds']
            s=t.read(folder/'summary.json'); raw=folder/'common_deck_pairs.jsonl.gz'
            t.require(s['evaluation_hands']==20480 and s['policy_mode']=='greedy' and s['observation_style']=='legacy_v4' and s['starting_stack_bb']==200,'contract')
            t.require(t.sha(raw)==s['raw_pairs_sha256'],'raw hash')
            t.require(all(t.sha(t.Path(p))==s['input_sha256'][k]==hashes[p] for k,p in s['input_paths'].items()),'weight binding')
            with gzip.open(raw,'rt',encoding='utf-8') as f: rows=[json.loads(x) for x in f]
            t.require(len(rows)==5120,'count'); mapping={}
            for ai,name in enumerate(q['anchors']):
                rr=[r for r in rows if r['anchor']==name]; rng=random.Random(20265901+10*seed+1000003*ai)
                t.require([r['pair_index'] for r in rr]==list(range(1024)),'pair coverage')
                for r in rr:
                    deck=list(range(52)); rng.shuffle(deck); t.require(r['deck']==deck,'deck schedule')
                    for k in ('control_rewards_bb','treatment_rewards_bb'):
                        t.require(len(r[k])==2 and all(math.isfinite(v) and -200<=v<=200 for v in r[k]),'rewards')
                    for seat in (0,1): t.require(abs(r['treatment_rewards_bb'][seat]-r['control_rewards_bb'][seat]-r['treatment_minus_control_rewards_bb'][seat])<1e-9,'delta')
                    for k in ('control','treatment','treatment_minus_control'):
                        t.require(abs(st.mean(r[k+'_rewards_bb'])-r[k+'_pair_mean_bb'])<1e-9,'pair mean')
                    mapping[(name,r['pair_index'])]=r
                    if arm=='control': t.require(tuple(deck) not in seen,'duplicate planned deck'); seen.add(tuple(deck))
            pooled=[r['treatment_minus_control_pair_mean_bb'] for r in rows]
            t.require(abs(st.mean(pooled)*100-s['pooled_treatment_minus_control_bb100'])<1e-8,'summary mean')
            t.require(abs(1.96*st.stdev(pooled)/math.sqrt(len(pooled))*100-s['pooled_treatment_minus_control_ci95_bb100'])<1e-8,'summary CI')
            arms[arm]=mapping
            for p in (raw,folder/'summary.json',job/'command.json',job/'process.json',job/'termination.json'): hashes[str(p)]=t.sha(p)
        a,b=arms['control'],arms['mixture']; t.require(a.keys()==b.keys(),'matched keys')
        for k in a: t.require(a[k]['deck']==b[k]['deck'] and a[k]['control_rewards_bb']==b[k]['control_rewards_bb'],'parent pairing')
        groups={'transfer':['moving_s1','moving_s3','half_lr_s1','half_lr_s3'],
                'moving_family':['moving_s1','moving_s3'],'half_lr_family':['half_lr_s1','half_lr_s3'],'standard10':['standard10']}
        contrasts={}
        for mode in ('control_minus_parent','mixture_minus_parent','mixture_minus_control'):
            def values(name,seat):
                def val(r,k): return r[k+'_pair_mean_bb'] if seat is None else r[k+'_rewards_bb'][seat]
                return [(val(b[k],'treatment')-val(a[k],'treatment') if mode=='mixture_minus_control' else
                         val((a if mode.startswith('control') else b)[k],'treatment_minus_control')) for k in a if k[0]==name]
            contrasts[mode]={g:{label:estimate([values(name,seat) for name in names]) for label,seat in [('pooled',None),('seat0',0),('seat1',1)]} for g,names in groups.items()}
        output[str(seed)]=contrasts
    t.require(len(seen)==10240,'unique count'); prior_rows=0
    for p,h in q['prior_corpus'].items():
        t.require(t.sha(p)==h,'prior changed')
        with gzip.open(p,'rt',encoding='utf-8') as f:
            for line in f: t.require(tuple(json.loads(line)['deck']) not in seen,'prior overlap'); prior_rows+=1
        hashes[p]=h
    t.ex.check_hashes(hashes)
    report={'passed':True,'command':sys.orig_argv,'input_sha256':hashes,'evaluation_hands':81920,'unique_decks':10240,
        'prior_rows':prior_rows,'overlap':0,'contrasts':output,'job_wall_seconds':jobwall,'controller_wall_seconds':result['wall_seconds'],
        'review_wall_seconds':time.perf_counter()-started,'final_qualification_hands':0,
        'scope':'Fixed-anchor stratified paired normal95CI; conditional on policies, not training-seed population. Standard10 excluded from transfer. Sibling relatedness and lifetime exposure remain limitations.'}
    t.write_new(out,report)
    print(json.dumps({'passed':True,'contrasts':output}))
if __name__=='__main__': main()
