"""Matched native-only target relabeling; no model, optimizer or external data."""
import hashlib
import importlib.util
from pathlib import Path
import numpy as np

ROOT=Path(__file__).resolve().parents[3]
REFERENCE=ROOT/'research/experiments/v6-realization-average-fidelity-20260831/mixture.py'
REFERENCE_SHA='2a40888852ebfddb29a71c63529543655f5c829523654e91dcc7b9515f2e506c'
if hashlib.sha256(REFERENCE.read_bytes()).hexdigest()!=REFERENCE_SHA:
    raise ValueError('Qualified posterior implementation changed')
spec=importlib.util.spec_from_file_location('qualified_reach_posterior',REFERENCE)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
Posterior=module.Posterior

def relabel_hand(teacher_probabilities,actors,slots):
    p=np.asarray(teacher_probabilities,dtype=np.float64)
    actors,slots=np.asarray(actors),np.asarray(slots)
    if p.ndim!=3 or p.shape[0]!=3 or p.shape[2]!=9 or p.shape[1]<1:
        raise ValueError('Three teachers and positive fixed hand sequence required')
    if actors.shape!=(p.shape[1],) or slots.shape!=actors.shape or actors.dtype.kind not in 'iu' or slots.dtype.kind not in 'iu':
        raise ValueError('Integer actor/slot sequence required')
    if not np.isin(actors,[0,1]).all() or (slots<0).any() or (slots>8).any():
        raise ValueError('Invalid actor/action')
    posteriors=[Posterior(),Posterior()]
    targets,weights=[],[]
    for step,actor in enumerate(actors):
        teacher=p[:,step,:]
        target,weight=posteriors[int(actor)].before(teacher)
        targets.append(target);weights.append(weight)
        posteriors[int(actor)].observe_own_action(teacher,int(slots[step]))
    return np.asarray(targets),np.asarray(weights)

def reservoir_index(identities):
    ids=np.asarray(identities)
    if ids.ndim!=2 or ids.shape[1]!=2 or ids.dtype.kind not in 'iu' or (ids<0).any():
        raise ValueError('Invalid reservoir identities')
    result={tuple(map(int,pair)):i for i,pair in enumerate(ids)}
    if len(result)!=len(ids):raise ValueError('Duplicate reservoir identities')
    return result

def scatter_hand(hand,targets,index,output,seen):
    if type(hand) is not int or hand<0:raise ValueError('Invalid hand identity')
    n=0
    for decision,target in enumerate(targets):
        slot=index.get((hand,decision))
        if slot is not None:
            if seen[slot]:raise ValueError('Retained row assigned twice')
            output[slot]=target
            seen[slot]=True
            n+=1
    return n

