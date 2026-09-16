"""Outcome-free roots, explicit panel, namespace and future-deck qualification."""
from pathlib import Path
import hashlib
import random
import sys
import unittest
import torch
import run_trial as t
import test_contract

def weights(state):
    h=hashlib.sha256()
    for k,v in sorted(state.items()):
        v=v.detach().cpu().contiguous()
        h.update(k.encode());h.update(str(v.dtype).encode());h.update(str(tuple(v.shape)).encode());h.update(v.numpy().tobytes())
    return h.hexdigest()

def main():
    o=t.old; torch.set_num_threads(1)
    o.require(not (t.BASE/'qualification.json').exists(),'preserve qualification')
    tests=unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(test_contract))
    o.require(tests.wasSuccessful() and tests.testsRun==4,'controller tests')
    review=o.read(t.SMOKE/'terminal_review.json')
    o.require(review['passed'] and o.read(t.SMOKE/'experiment.json')['status']=='COMPLETED','worker smoke')
    o.ctl.execution.check_hashes(review['input_sha256'])
    hashes=dict(review['input_sha256']); hashes[str(t.SMOKE/'terminal_review.json')]=o.sha(t.SMOKE/'terminal_review.json')
    parents={}; boundary=set(); external=set(); known=set()
    for seed in (1,3):
        p=t.parent_path(seed,'control',1); digest=o.sha(p)
        o.require(digest==o.EXPECTED[seed],'wrong root')
        c=torch.load(p,map_location='cpu',weights_only=False)
        o.require(c['environment_hand_accounting']['completed_hands']==o.INITIAL[seed] and len(c['pool_snapshots'])==9 and len(c['ppo_replay_entries'])==2,'root contract')
        o.ctl.route_audit(c,True,c); boundary.add(weights(c['model']))
        for snap in c['pool_snapshots']:boundary.add(weights(snap['state_dict']))
        for item in c['pool_candidate_history']+c['pool_active_metadata']:
            h=item.get('score_components',{}).get('checkpoint_sha256')
            if h:external.add(h)
        known.add(c['fixed_deal_attempt']['receipt']['namespace'])
        for arm in ('control','expanded'):parents[f'{seed}_{arm}']=digest
        for name in ('latest.pt','command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl','mixture_runtime.json'):hashes[str(p.parent/name)]=o.sha(p.parent/name)
        del c
    transfer={
      'mixture_s1':t.BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907/seed1_mixture_stage2/latest.pt',
      'mixture_s3':t.BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907/seed3_mixture_stage2/latest.pt',
      'heads_s1':t.BASE.parent/'v6-current-kl-representation-pilot-20260905/seed1_heads_stage2/latest.pt',
      'heads_s3':t.BASE.parent/'v6-current-kl-representation-pilot-20260905/seed3_heads_stage2/latest.pt'}
    sys.path.insert(0,str(o.ROOT/'scripts'))
    from alpha_holdem.v5_mirror_eval import init_model
    candidates={}; unique=set()
    for name,p in transfer.items():
        o.require(o.read(p.parent.parent/'experiment.json')['status']=='COMPLETED','candidate incomplete')
        c=torch.load(p,map_location='cpu',weights_only=False); digest=o.sha(p); w=weights(c['model'])
        o.require(w not in boundary and w not in unique and digest not in external,'candidate pool overlap')
        o.require(all(torch.isfinite(v).all() for v in c['model'].values()),'candidate finite')
        init_model(c,'cpu').eval(); unique.add(w); hashes[str(p)]=digest
        candidates[name]=dict(path=str(p),sha256=digest,model_tensor_sha256=w)
        del c
    anchors={k:str(v) for k,v in o.ctl.execution.ANCHORS.items()}
    for k,v in anchors.items():o.require(o.sha(Path(v))==o.ctl.execution.ANCHOR_SHA256[k],'preservation anchor')
    anchors.update({k:str(v) for k,v in transfer.items()})
    for p in anchors.values():hashes[p]=o.sha(Path(p))
    for p in (o.ROOT/'research/experiments').rglob('attempt-*.json'):
        r=o.read(p)
        if r.get('schema')=='cardpilot.fixed_deal_attempt.v1':known.add(r['namespace'])
    corpus={str(p):o.sha(p) for p in (o.ROOT/'research/experiments').rglob('common_deck_pairs.jsonl.gz') if not p.is_relative_to(t.BASE)}
    decks=[]
    for seed in o.EVAL_SEEDS.values():
        for i in range(8):
            rng=random.Random(seed+1000003*i)
            for _ in range(1024):
                deck=list(range(52));rng.shuffle(deck);decks.append({'deck':deck})
    o.require(len({tuple(r['deck']) for r in decks})==32768,'future duplicates')
    freshness=o.ctl.evidence.check_prior_decks(decks,corpus)
    for root in (t.BASE,t.SMOKE,t.REPORTER,o.ROOT/'scripts/alpha_holdem'):
        for p in root.rglob('*.py'):hashes[str(p)]=o.sha(p)
    for module in list(sys.modules.values()):
        path=getattr(module,'__file__',None)
        if path:
            p=Path(path).resolve()
            if p.is_file() and p.suffix=='.py' and p.is_relative_to(o.ROOT):hashes[str(p)]=o.sha(p)
    hashes[str(t.BASE/'protocol.md')]=o.sha(t.BASE/'protocol.md')
    o.ctl.execution.check_hashes(hashes)
    report=dict(passed=True,tests_passed=4,real_worker_smoke_passed=True,input_sha256=hashes,parent_sha256=parents,anchors=anchors,transfer_candidates=candidates,transfer_scope='Distinct from two current root model/pool tensor sets and recorded external source hashes; shared ancestry, not lifetime non-exposure or universal diversity.',known_namespaces=sorted(known),prior_corpus=corpus,planned_deck_freshness=freshness,training_hands=0,evaluation_hands=0)
    o.write_new(t.BASE/'qualification.json',report)
    print('Qualified four controller tests, both original parents, four distinct transfer candidates, and32768 fresh future decks; zero poker executions.')

if __name__=='__main__':main()
