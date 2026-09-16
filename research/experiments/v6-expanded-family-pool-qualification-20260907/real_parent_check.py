"""Read-only real retained-parent qualification; no checkpoints or hands written."""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import struct
import numpy as np
import torch
from expand import expand,FIELDS

BASE=Path(__file__).resolve().parent
TRIAL=BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def equal(a,b):
    if type(a)!=type(b): return False
    if isinstance(a,torch.Tensor): return a.dtype==b.dtype and a.shape==b.shape and torch.equal(a.detach().cpu().contiguous().reshape(-1).view(torch.uint8),b.detach().cpu().contiguous().reshape(-1).view(torch.uint8))
    if isinstance(a,np.ndarray): return a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
    if isinstance(a,float): return struct.pack('d',a)==struct.pack('d',b)
    if isinstance(a,dict): return a.keys()==b.keys() and all(equal(a[k],b[k]) for k in a)
    if isinstance(a,(list,tuple)): return len(a)==len(b) and all(equal(x,y) for x,y in zip(a,b))
    return a==b
def require(v,m):
    if not v: raise ValueError(m)
def main():
    require(not (BASE/'real_parent_report.json').exists(),'preserve report')
    torch.set_num_threads(1)
    require(equal(np.array([float('nan')]),np.array([float('nan')])), 'preserved sentinel comparator')
    require(not equal(np.array([float('nan')]),np.array([0.])), 'changed sentinel comparator')
    panel=read(BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    review=read(TRIAL/'post_terminal_review.json')
    require(panel['passed'] and review['passed'],'parent reviews')
    hashes={str(p):sha(p) for p in BASE.glob('*.py')}; additions=[]
    for name in ('moving_s1','moving_s3','half_lr_s1','half_lr_s3'):
        a=panel['candidates'][name]; p=Path(a['path']); require(sha(p)==a['sha256'],'candidate changed')
        hashes[str(p)]=a['sha256']; additions.append({**a,'checkpoint':torch.load(p,map_location='cpu',weights_only=False)})
    wrapper=BASE.parent/'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
    spec=importlib.util.spec_from_file_location('integration',wrapper); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    trainer,binding=module.install(); hashes[str(wrapper)]=sha(wrapper)
    reports={}
    for seed in (1,3):
        p=TRIAL/f'seed{seed}_control_stage2/latest.pt'; digest=sha(p)
        require(digest==review['input_sha256'][str(p)],'retained parent changed'); hashes[str(p)]=digest
        parent=torch.load(p,map_location='cpu',weights_only=False); derived=expand(parent,additions)
        preserved=[k for k in parent if k not in FIELDS]
        unequal=[k for k in preserved if not equal(parent[k],derived[k])]
        require(not unequal,'nonpool state changed: '+str(unequal))
        require(equal(parent['pool_snapshots'],derived['pool_snapshots'][:5]),'old slots changed')
        pool=trainer.OpponentPool(k=9,strategy='anchor-latest',history_limit=200)
        pool.load_from_checkpoint(derived['pool_snapshots'],candidate_history=derived['pool_candidate_history'])
        for loaded,saved in zip(pool.snapshots,derived['pool_snapshots']):
            require(equal(dict(loaded['state_dict']),dict(saved['state_dict'])),'pool weight bytes changed')
            require(equal({k:v for k,v in loaded.items() if k!='state_dict'}, {k:v for k,v in saved.items() if k!='state_dict'}),'pool metadata changed')
        require(pool.active_ids()==[s['id'] for s in derived['pool_snapshots']],'slot reorder')
        old_ids=set(pool.active_ids()); new=pool.add(parent['model'],hands=parent['total_hands'],iteration=parent['iteration']+1,selection_loss=0.0,score_components={})
        anchors={s['id'] for s in derived['pool_snapshots'] if s['score_components'].get('kind')=='initial_external_opponent'}
        require(anchors.issubset(set(pool.active_ids())) and len(pool.active_ids())==9,'anchor discard')
        require(new['id']>max(old_ids),'ID collision')
        reports[str(seed)]={'parent_sha256':digest,'preserved_top_level_fields':preserved,
            'parent_physical_hands':parent['environment_hand_accounting']['completed_hands'],
            'new_external_ids':derived['expanded_family_pool_contract']['new_ids'],
            'first_subsequent_id':new['id'],'seven_anchors_retained':True,'initial_pool_order_preserved':True,
            'model_optimizer_replay_rng_counter_preserved':True}
        del parent,derived,pool
    require(all(sha(Path(p))==h for p,h in hashes.items()),'source changed')
    value={'passed':True,'command':sys.orig_argv,'input_sha256':hashes,'seeds':reports,'binding':binding,
        'training_hands':0,'evaluation_hands':0,'checkpoint_written':False,
        'scope':'Pure derivation and actual pool load/admission on two real parents; worker assignment replay boundary and serialized training continuation NOT yet qualified.'}
    with (BASE/'real_parent_report.json').open('x',encoding='utf-8') as f: json.dump(value,f,indent=2)
    print(json.dumps({'passed':True,'seeds':list(reports),'checkpoint_written':False}))
if __name__=='__main__': main()
