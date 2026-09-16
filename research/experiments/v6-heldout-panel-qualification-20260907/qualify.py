"""Outcome-free candidate-panel identity qualification; no poker execution."""
import hashlib
import json
from pathlib import Path
import sys
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
TRIAL=BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def weights(state):
    h=hashlib.sha256()
    for k,v in sorted(state.items()):
        t=v.detach().cpu().contiguous()
        h.update(k.encode()); h.update(str(t.dtype).encode()); h.update(str(tuple(t.shape)).encode()); h.update(t.numpy().tobytes())
    return h.hexdigest()
def require(v,m):
    if not v: raise ValueError(m)
def main():
    require(not (BASE/'qualification.json').exists(),'preserve evidence')
    torch.set_num_threads(1)
    sys.path.insert(0,str(ROOT/'scripts'))
    from alpha_holdem.v5_mirror_eval import init_model
    paths={
      'moving_s1':BASE.parent/'v6-phase-held-reference-control-20260904/moving256_stage2/latest.pt',
      'moving_s3':BASE.parent/'v6-phase-held-reference-seed3-replication-20260905/moving256_stage2/latest.pt',
      'half_lr_s1':BASE.parent/'v6-full-step-size-1m-continuation-20260905/seed1_half_stage2/latest.pt',
      'half_lr_s3':BASE.parent/'v6-full-step-size-1m-continuation-20260905/seed3_half_stage2/latest.pt'}
    hashes={str(Path(__file__)):sha(Path(__file__))}; candidates={}
    for name,p in paths.items():
        require(read(p.parent.parent/'experiment.json')['status']=='COMPLETED','candidate incomplete')
        c=torch.load(p,map_location='cpu',weights_only=False)
        require(all(torch.isfinite(t).all() for t in c['model'].values()),'nonfinite candidate')
        init_model(c,'cpu').eval()
        digest=sha(p); hashes[str(p)]=digest
        candidates[name]={'path':str(p),'sha256':digest,'model_tensor_sha256':weights(c['model']),
          'family':'moving_reference' if name.startswith('moving') else 'half_learning_rate',
          'iteration':c['iteration'],'env_version':c.get('env_version')}
        del c
    require(len({v['model_tensor_sha256'] for v in candidates.values()})==4,'duplicate candidate')
    review=read(TRIAL/'post_terminal_review.json'); require(review['passed'],'unreviewed parents')
    boundary_weights=set(); external=set(); checked=0
    for stage in (1,2):
      for seed in (1,3):
       for arm in ('control','mixture'):
        for filename in ('initial_resumed_state.pt','latest.pt'):
          p=TRIAL/f'seed{seed}_{arm}_stage{stage}'/filename
          digest=sha(p); require(review['input_sha256'][str(p)]==digest,'unbound boundary')
          hashes[str(p)]=digest; c=torch.load(p,map_location='cpu',weights_only=False)
          boundary_weights.add(weights(c['model']))
          for snap in c['pool_snapshots']:
            boundary_weights.add(weights(snap['state_dict'])); checked+=1
          for entry in c['pool_candidate_history']+c['pool_active_metadata']:
            h=entry.get('score_components',{}).get('checkpoint_sha256')
            if h: external.add(h)
          del c
    for c in candidates.values():
        require(c['sha256'] not in external and c['model_tensor_sha256'] not in boundary_weights,'candidate overlap')
    require(all(sha(Path(p))==h for p,h in hashes.items()),'source changed')
    result={'passed':True,'command':sys.orig_argv,'candidates':candidates,'input_sha256':hashes,
      'boundary_pool_snapshots_checked':checked,'distinct_boundary_weight_sets':len(boundary_weights),
      'known_external_checkpoint_hashes':sorted(external),'evaluation_hands':0,'training_hands':0,
      'scope':'Distinct from 16 retained trial-boundary model/pool weight sets and recorded external source hashes; CPU model loading qualified. Does not prove lifetime non-exposure or strategic diversity.',
      'limitations':['Intermediate discarded snapshots were not all reconstructed.',
         'Sibling lineages share ancestors; candidate families do not represent universal opponent diversity.',
         'No forward-action parity or full evaluator execution is certified by CPU loading alone.'],
      'next':'Freeze candidate/source identities and evaluate all four endpoints versus own parents, Standard10 separately from four candidate transfer results. Qualify forward contract and fresh-deck exclusion before poker.'}
    with (BASE/'qualification.json').open('x',encoding='utf-8') as f: json.dump(result,f,indent=2)
    print(json.dumps({k:result[k] for k in ('passed','boundary_pool_snapshots_checked','distinct_boundary_weight_sets','scope')}))
if __name__=='__main__': main()
