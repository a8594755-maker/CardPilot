"""Read-only preflight plus exclusive qualification artifact, no poker execution."""
import json
from pathlib import Path
import random
import sys
import unittest
import subprocess
import xml.etree.ElementTree as ET
import torch
import run_trial as t
import test_trial
from expand import FIELDS

def main():
    torch.set_num_threads(1)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(test_trial))
    t.require(result.wasSuccessful() and result.testsRun == 4,'tests failed')
    review=t.read(t.SMOKE/'terminal_review.json')
    t.require(t.read(t.SMOKE/'experiment.json')['status']=='COMPLETED' and review['passed'],'smoke incomplete')
    t.ctl.execution.check_hashes(review['input_sha256'])
    hashes=dict(review['input_sha256'])
    hashes[str(t.SMOKE/'terminal_review.json')]=t.sha(t.SMOKE/'terminal_review.json')
    prior=t.read(t.PARENTS/'qualification.json')
    for p,h in prior['input_sha256'].items():
        if p.endswith('.py'):
            t.require(t.sha(Path(p))==h,'prior runtime changed: '+p)
            hashes[p]=h
    parent_hashes={}
    for p in t.BASE.glob('*.py'): hashes[str(p)]=t.sha(p)
    for p in (t.ROOT/'scripts/alpha_holdem').rglob('*.py'): hashes[str(p)]=t.sha(p)
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if filename:
            path=Path(filename).resolve()
            if path.is_relative_to(t.ROOT) and path.suffix=='.py' and path.is_file(): hashes[str(path)]=t.sha(path)
    known=set()
    for path in (t.ROOT/'research/experiments').rglob('attempt-*.json'):
        receipt=t.read(path)
        if receipt.get('schema')=='cardpilot.fixed_deal_attempt.v1': known.add(receipt['namespace'])
    for seed in (1,3):
        path=t.parent_path(seed,'control',1)
        ckpt=torch.load(path,map_location='cpu',weights_only=False)
        t.require(t.sha(path)==t.EXPECTED[seed] and ckpt['environment_hand_accounting']['completed_hands']==t.INITIAL[seed],'parent mismatch')
        t.ctl.route_audit(ckpt,True,ckpt)
        t.require(len(ckpt['optimizer']['param_groups'][0]['params'])==86 and
            ckpt['optimizer']['param_groups'][0]['lr']==9.999999999999996e-05,'optimizer scope/LR')
        known.add(ckpt['fixed_deal_attempt']['receipt']['namespace'])
        for name in ('command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl'):
            hashes[str(path.parent/name)]=t.sha(path.parent/name)
        parent_hashes[f'{seed}_control']=t.sha(path)
        expanded_path=t.parent_path(seed,'expanded',1)
        expanded=torch.load(expanded_path,map_location='cpu',weights_only=False)
        t.require(t.sha(expanded_path)==review['input_sha256'][str(expanded_path)],'derived parent changed')
        t.require(set(ckpt)-FIELDS==set(expanded)-FIELDS,'nonpool key set')
        for key in set(ckpt)-FIELDS:
            t.require(t.state_equal(ckpt[key],expanded[key]),'nonpool state changed: '+key)
        t.require(len(expanded['pool_snapshots'])==9,'expanded size')
        for name in ('command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl'):
            t.require(t.sha(expanded_path.parent/name)==t.sha(path.parent/name),'derived evidence mismatch')
        parent_hashes[f'{seed}_expanded']=t.sha(expanded_path)
        hashes[str(path)]=t.sha(path)
        hashes[str(expanded_path)]=t.sha(expanded_path)
        del expanded
        del ckpt
    for name,path in t.ctl.execution.ANCHORS.items():
        t.require(t.sha(path)==t.ctl.execution.ANCHOR_SHA256[name],'anchor changed')
        hashes[str(path)]=t.sha(path)
    corpus={str(p):t.sha(p) for p in (t.ROOT/'research/experiments').rglob('common_deck_pairs.jsonl.gz')
        if not p.is_relative_to(t.BASE)}
    # Exact evaluator RNG schedule, without playing any hands.
    decks=[]
    for seed in t.EVAL_SEEDS.values():
        for index in range(4):
            rng=random.Random(seed+1000003*index)
            for _ in range(2048):
                deck=list(range(52)); rng.shuffle(deck); decks.append({'deck':deck})
    t.require(len({tuple(r['deck']) for r in decks})==32768,'planned deck reuse')
    freshness=t.ctl.evidence.check_prior_decks(decks,corpus)
    t.write_new(t.BASE/'qualification.json',{'passed':True,'tests_passed':result.testsRun,
        'input_sha256':hashes,'real_worker_smoke_passed':True,'parent_sha256':parent_hashes,
        'command':sys.orig_argv,
        'prior_corpus':corpus,'known_namespaces':sorted(known),
        'planned_deck_freshness':freshness,'training_hands':0,'evaluation_hands':0,
        'scope':'Controller tests and exact known-parent/future evaluation deck preflight; actual per-run gates still mandatory.'})

if __name__=='__main__': main()
