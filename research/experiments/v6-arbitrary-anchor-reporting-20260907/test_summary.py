import copy
import random
import pytest
from paired_summary import summarize, severe

def rows(anchors=('new_a','new_b','new_c','new_d'),pairs=4):
    rng=random.Random(71); out=[]
    for a in anchors:
        for i in range(pairs):
            deck=list(range(52)); rng.shuffle(deck)
            out.append(dict(anchor=a,pair_index=i,deck=deck,control_rewards_bb=[0.,0.],treatment_rewards_bb=[-1.,-1.],treatment_minus_control_rewards_bb=[-1.,-1.],treatment_minus_control_pair_mean_bb=-1.))
    return out

def test_new_names_and_gate():
    names=('new_a','new_b','new_c','new_d'); r=summarize(rows(),anchors=names,pairs_per_anchor=4)
    assert tuple(r['by_anchor'])==names and all(v['samples']==4 for v in r['by_anchor'].values())
    assert r['pooled']['bb100']==-100 and severe(r,minimum_bad_anchors=3)

@pytest.mark.parametrize('n',[1,4,5,8])
def test_explicit_panel_sizes(n):
    names=tuple(f'a{i}' for i in range(n)); r=summarize(rows(names),anchors=names,pairs_per_anchor=4)
    assert len(r['by_anchor'])==n and r['pooled']['samples']==n*4

@pytest.mark.parametrize('mutation',['missing','extra','duplicate','nan','bad_delta','bad_mean','bad_deck','same_deck'])
def test_fail_closed(mutation):
    r=rows(); names=('new_a','new_b','new_c','new_d')
    if mutation=='missing': r.pop()
    elif mutation=='extra': r[0]['anchor']='unknown'
    elif mutation=='duplicate': r.append(copy.deepcopy(r[0]))
    elif mutation=='nan': r[0]['treatment_rewards_bb'][0]=float('nan')
    elif mutation=='bad_delta': r[0]['treatment_minus_control_rewards_bb'][0]=2
    elif mutation=='bad_mean': r[0]['treatment_minus_control_pair_mean_bb']=2
    elif mutation=='bad_deck': r[0]['deck']=[0]*52
    elif mutation=='same_deck': r[0]['deck']=r[1]['deck']
    with pytest.raises(ValueError): summarize(r,anchors=names,pairs_per_anchor=4)

def test_empty_legacy_gate_rejected():
    with pytest.raises(ValueError): severe(dict(by_anchor={'a':{'samples':0}},by_seat={}),minimum_bad_anchors=1)

def test_wrong_declared_panel_rejected():
    with pytest.raises(ValueError): summarize(rows(),anchors=('standard10','cfr4','legacy_iter16','legacy_mixed65k'),pairs_per_anchor=4)
