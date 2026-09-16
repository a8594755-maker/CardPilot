"""Reuse qualified frozen evaluator with outcome-independent sibling panel."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import random
from statistics import NormalDist
import sys

BASE=Path(__file__).resolve().parent
PILOT=BASE.parent/'v6-regularized-return-two-seed-pilot-20260908'
spec=importlib.util.spec_from_file_location('frozen_evaluator',PILOT/'evaluate.py')
ev=importlib.util.module_from_spec(spec); spec.loader.exec_module(ev)
ev.BASE=BASE


def deals(stage,seed,anchor):
    assert stage==1
    for index in range(512):
        text=f'regularized-sibling-confirmation-20260908:{seed}:{anchor}:{index}'
        key=int.from_bytes(hashlib.sha256(text.encode()).digest()[:16],'big')
        deck=list(range(52)); random.Random(key).shuffle(deck)
        yield index,key,deck


ev.deals=deals


def prepare():
    original=ev.read(PILOT/'stage2_evaluation_contract.json')
    ev.verify(original)
    assert ev.read(PILOT/'stage2_evaluation_review.json')['passed']
    assert ev.read(PILOT/'stage2_training_review.json')['passed']
    qualification=ev.read(BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    assert qualification['passed']
    anchors={k:original['anchors'][k] for k in ('standard10','cfr4','legacy_iter16','legacy_mixed65k')}
    anchors.update(qualification['candidates'])
    assert len(anchors)==8
    planned={tuple(deck) for seed in ('1','3') for a in anchors for _,_,deck in deals(1,seed,a)}
    assert len(planned)==8192
    previous=ev.read(BASE.parent/'v6-current-sampled-endpoint-eval-20260908/contract.json')
    files={Path(p):gzip.open for p in previous['prior_gzip']}
    files.update({Path(p):open for p in previous['prior_plain']})
    for folder in BASE.parent.glob('v6-*20260908'):
        for path in folder.rglob('*hands.jsonl'): files[path]=open
    prior=0
    for path,opener in files.items():
        with opener(path,'rt',encoding='utf-8') as h:
            for line in h:
                row=json.loads(line); trace=row.get('trace',row)
                if 'deck' in trace:
                    assert tuple(trace['deck']) not in planned,str(path)
                    prior+=1
    hashes=dict(original['hashes'])
    for path in (Path(__file__),BASE/'protocol.md',PILOT/'evaluate.py',PILOT/'evaluator_test_result.json'):
        hashes[str(path)]=ev.sha(path)
    for item in anchors.values():
        assert ev.sha(item['path'])==item['sha256']
        hashes[item['path']]=item['sha256']
    contract=dict(stage=1,policies=original['policies'],anchors=anchors,hashes=hashes,
        hands=49152,planned_decks=8192,prior_files=len(files),prior_deck_rows=prior,
        limitations='Sibling families share ancestry; inventory only covers available recorded decks.')
    ev.write(BASE/'stage1_evaluation_contract.json',contract)
    print(json.dumps(dict(prepared=True,decks=8192,prior_deck_rows=prior)))


def review():
    ev.review(1)
    report=ev.read(BASE/'stage1_evaluation_review.json')
    z=NormalDist().inv_cdf(1-.05/(2*4)); primary={}
    for seed,contrasts in report['reports'].items():
        primary[seed]={}
        for name in ('regularized_minus_control','regularized_minus_parent'):
            pooled=contrasts[name]['pooled']; mean=pooled['bb100']
            se=(pooled['ci95'][1]-pooled['ci95'][0])/(2*1.96)
            primary[seed][name]=dict(**pooled,bonferroni95_family4=[mean-z*se,mean+z*se])
    confirmed=all(report['reports'][s]['regularized_minus_control']['pooled']['ci95'][0]>0
        and report['reports'][s]['regularized_minus_control']['transfer']['bb100']>0 for s in ('1','3'))
    parent_regression=all(report['reports'][s]['regularized_minus_parent']['pooled']['ci95'][1]<0 for s in ('1','3'))
    ev.write(BASE/'confirmation.json',dict(primary=primary,confirmed=confirmed and not parent_regression,
        parent_regression=parent_regression,scope='Frozen independent mixed preservation/sibling panel, not Slumbot.'))


if __name__=='__main__':
    {'prepare':prepare,'run':lambda:ev.run(1),'review':review}[sys.argv[1]]()
