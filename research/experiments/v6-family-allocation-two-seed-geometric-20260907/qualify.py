"""Frozen parent/source/future-deck qualification; no training or evaluation."""
from pathlib import Path
import random
import sys
import unittest
import torch
import run_trial as t
import test_contract

def main():
    o = t.old
    torch.set_num_threads(1)
    tests = unittest.TextTestRunner().run(unittest.defaultTestLoader.loadTestsFromModule(test_contract))
    o.require(tests.wasSuccessful() and tests.testsRun == 4, 'tests')
    review = o.read(t.QUAL / 'terminal_family_review.json')
    o.require(review['passed'] and o.read(t.QUAL/'experiment.json')['status']=='COMPLETED','smoke not reviewed')
    o.ctl.execution.check_hashes(review['input_sha256'])
    hashes = dict(review['input_sha256'])
    hashes[str(t.QUAL/'terminal_family_review.json')] = o.sha(t.QUAL/'terminal_family_review.json')
    parents, known = {}, set()
    for p in (o.ROOT/'research/experiments').rglob('attempt-*.json'):
        receipt = o.read(p)
        if receipt.get('schema') == 'cardpilot.fixed_deal_attempt.v1': known.add(receipt['namespace'])
    for seed in (1,3):
        report = o.read(t.QUAL/f'real_resume_seed{seed}.json')['seeds'][str(seed)]
        a,b = t.parent_path(seed,'control',1),t.parent_path(seed,'expanded',1)
        o.require(o.sha(a)==report['source_sha256'] and o.sha(b)==report['derived_sha256'],'root hash')
        p,q = [torch.load(path,map_location='cpu',weights_only=False) for path in (a,b)]
        o.require(p.keys()==q.keys() and all(o.state_equal(p[k],q[k]) for k in p if k!='adaptive_opponent_weights'),'nonallocation state')
        for arm,path,ckpt in (('control',a,p),('expanded',b,q)):
            o.require(ckpt['environment_hand_accounting']['completed_hands']==o.INITIAL[seed] and ckpt['iteration']==3116,'root counters')
            o.require(len(ckpt['pool_snapshots'])==9,'capacity')
            o.ctl.route_audit(ckpt,True,ckpt)
            parents[f'{seed}_{arm}'] = hashes[str(path)] = o.sha(path)
            known.add(ckpt['fixed_deal_attempt']['receipt']['namespace'])
            for name in ('command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl'):
                hashes[str(path.parent/name)] = o.sha(path.parent/name)
                o.require(o.sha(a.parent/name)==o.sha(b.parent/name),'paired prefixes')
        del p,q
    anchors = {k:str(v) for k,v in o.ctl.execution.ANCHORS.items()}
    panel = o.read(t.BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    for k in ('moving_s1','moving_s3','half_lr_s1','half_lr_s3'):
        r = panel['candidates'][k]
        o.require(o.sha(Path(r['path']))==r['sha256'],'sibling anchor')
        anchors[k]=r['path']
    for k,v in anchors.items():
        if k in o.ctl.execution.ANCHOR_SHA256:
            o.require(o.sha(Path(v))==o.ctl.execution.ANCHOR_SHA256[k],'original anchor')
        hashes[str(v)] = o.sha(Path(v))
    corpus = {str(p):o.sha(p) for p in (o.ROOT/'research/experiments').rglob('common_deck_pairs.jsonl.gz') if not p.is_relative_to(t.BASE)}
    decks = []
    for seed in o.EVAL_SEEDS.values():
        for i in range(8):
            rng = random.Random(seed+1000003*i)
            for _ in range(1024):
                deck=list(range(52)); rng.shuffle(deck); decks.append({'deck':deck})
    o.require(len({tuple(r['deck']) for r in decks})==32768,'future duplicates')
    freshness = o.ctl.evidence.check_prior_decks(decks,corpus)
    for root in (t.BASE,t.QUAL,o.ROOT/'scripts/alpha_holdem'):
        for p in root.rglob('*.py'): hashes[str(p)] = o.sha(p)
    for module in list(sys.modules.values()):
        file = getattr(module,'__file__',None)
        if file:
            p=Path(file).resolve()
            if p.is_relative_to(o.ROOT) and p.is_file() and p.suffix=='.py': hashes[str(p)]=o.sha(p)
    hashes[str(t.BASE/'protocol.md')] = o.sha(t.BASE/'protocol.md')
    o.ctl.execution.check_hashes(hashes)
    o.write_new(t.BASE/'qualification.json',{'passed':True,'tests_passed':4,'real_worker_smoke_passed':True,
        'input_sha256':hashes,'parent_sha256':parents,'anchors':anchors,'known_namespaces':sorted(known),
        'prior_corpus':corpus,'planned_deck_freshness':freshness,'training_hands':0,'evaluation_hands':0})
    print('Qualification passed; zero new hands.')

if __name__=='__main__': main()
