"""Isolated actual-checkpoint pool qualification, zero training or evaluation."""
import ast
import hashlib
import json
import math
from pathlib import Path
import sys
from datetime import datetime, timezone
import torch
from anchor_recent import retained_snapshots, pool_class

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
TRAIN=ROOT/'research/experiments/v6-preflop-actor-route-2m-continuation-20260906'
SOURCE=ROOT/'research/experiments/v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts/alpha_holdem/train_v5.py'
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def require(ok,msg):
    if not ok: raise ValueError(msg)
def main():
    out=BASE/'qualification.json'
    require(not out.exists(),'preserve qualification')
    require(sha(SOURCE)=='bcce947477fdcf6593b7a88ce6845bf5638ce6698b9462deeecf4133b05472e6','trainer changed')
    tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
    node=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='OpponentPool')
    scope={'math':math}
    exec(compile(ast.Module(body=[node],type_ignores=[]),str(SOURCE),'exec'),scope)
    original=scope['OpponentPool']; candidate=pool_class(original)
    # Deterministic synthetic edge cases, no runtime imports or poker requests.
    anchors=[{'id':i,'score_components':{'kind':'initial_external_opponent'}} for i in range(3)]
    learned=[{'id':i,'score_components':{},'selection_score':-i} for i in range(3,10)]
    require([s['id'] for s in retained_snapshots(anchors+learned,5)]==[0,1,2,9,8],'wrong selection')
    require(retained_snapshots(anchors+learned[:2],5)==anchors+learned[:2],'load ordering changed')
    for snaps,k in ((anchors,2),(anchors,0),(anchors+[anchors[0]],5)):
        try: retained_snapshots(snaps,k)
        except ValueError: pass
        else: raise ValueError('invalid pool admitted')
    report=json.loads((TRAIN/'post_terminal_review.json').read_text())
    inputs={str(SOURCE):sha(SOURCE),str(BASE/'anchor_recent.py'):sha(BASE/'anchor_recent.py'),str(Path(__file__)):sha(Path(__file__))}
    results={}
    for seed in (1,3):
        path=TRAIN/f'seed{seed}_connected_stage3/latest.pt'
        digest=sha(path); require(report['input_sha256'][str(path)]==digest,'checkpoint changed')
        inputs[str(path)]=digest
        checkpoint=torch.load(path,map_location='cpu',weights_only=False)
        pool=candidate(k=5,history_limit=200)
        pool.load_from_checkpoint(checkpoint['pool_snapshots'],checkpoint['pool_candidate_history'])
        old_ids=[s['id'] for s in checkpoint['pool_snapshots']]
        require(pool.active_ids()==old_ids,'restored pool order changed')
        for old,new in zip(checkpoint['pool_snapshots'],pool.snapshots):
            require(all(torch.equal(v,new['state_dict'][k]) for k,v in old['state_dict'].items()),'pool tensors changed')
        initial_next=pool.next_id
        anchor_ids=[s['id'] for s in pool.snapshots if s['score_components'].get('kind')=='initial_external_opponent']
        for offset in range(3):
            # Tiny synthetic candidate payload tests inherited cloning/history and
            # selection; it is never a poker model or a training checkpoint.
            snap=pool.add({'fixture':torch.tensor([offset])},iteration=3000+offset,selection_loss=9999)
            require(snap['id']==initial_next+offset and snap['id'] in pool.active_ids(),'fresh candidate excluded')
            require(all(i in pool.active_ids() for i in anchor_ids),'anchor dropped')
        require(pool.active_ids()==anchor_ids+[initial_next+2,initial_next+1],'recent slots wrong')
        restored=candidate(k=5,history_limit=200)
        restored.load_from_checkpoint(pool.snapshots,pool.candidate_history)
        require(restored.active_ids()==pool.active_ids() and restored.next_id==pool.next_id,'resume identity changed')
        results[str(seed)]={'original_ids':old_ids,'anchors':anchor_ids,'initial_next_id':initial_next,
            'after_three_synthetic_candidates':pool.active_ids(),'retained_initial_pool_tensors_exact':True,
            'load_preserves_slot_order':True,'next_id_roundtrip':True}
        del checkpoint,pool,restored
    for p,h in inputs.items(): require(sha(Path(p))==h,'input changed')
    with out.open('x',encoding='utf-8') as f:
        json.dump({'passed':True,'created_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv,
            'input_sha256':inputs,'actual_parent_pool_fixtures':results,'synthetic_edge_cases':5,
            'new_training_hands':0,'evaluation_hands':0,'optimizer_updates':0,
            'scope':'Pool component only. No trainer CLI/config integration, actual trainer resume or new rollout is qualified yet.'},f,indent=2)
    print(json.dumps(results))
if __name__=='__main__': main()
