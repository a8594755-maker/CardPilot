"""Exclusive expanded parents with original raw prefixes and explicit derivation."""
from pathlib import Path
import hashlib
import json
import shutil
import sys
import torch
BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
QUAL=BASE.parent/'v6-expanded-family-pool-qualification-20260907'
sys.path.insert(0,str(QUAL))
import real_parent_check as r
from expand import expand,FIELDS
def main():
    torch.set_num_threads(1)
    r.require(not (BASE/'derived').exists(),'preserve prior derivation')
    boundary=r.read(BASE.parent/'v6-expanded-assignment-boundary-20260907/report.json')
    r.require(boundary['passed'],'boundary unqualified')
    for p,h in boundary['input_sha256'].items(): r.require(r.sha(Path(p))==h,'input changed')
    hashes=dict(boundary['input_sha256']); parents={}
    panel=r.read(BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    adds=[{**panel['candidates'][n],'checkpoint':torch.load(panel['candidates'][n]['path'],map_location='cpu',weights_only=False)} for n in ('moving_s1','moving_s3','half_lr_s1','half_lr_s3')]
    for seed in (1,3):
        source=r.TRIAL/f'seed{seed}_control_stage2/latest.pt'
        parent=torch.load(source,map_location='cpu',weights_only=False); derived=expand(parent,adds)
        folder=BASE/f'derived/seed{seed}_recent_stage2'; folder.mkdir(parents=True)
        target=folder/'latest.pt'
        with target.open('xb') as f: torch.save(derived,f)
        restored=torch.load(target,map_location='cpu',weights_only=False)
        r.require(r.equal(derived,restored),'serialized derivation mismatch')
        r.require(all(r.equal(parent[k],restored[k]) for k in parent if k not in FIELDS),'nonpool changed')
        for name in ('h1_training_metrics.jsonl','opponent_assignments.jsonl','command.json','mixture_runtime.json'):
            shutil.copy2(source.parent/name,folder/name)
            r.require(r.sha(source.parent/name)==r.sha(folder/name),'prefix copy')
            hashes[str(folder/name)]=r.sha(folder/name)
        parents[str(seed)]={'path':str(target),'sha256':r.sha(target),'original_path':str(source),'original_sha256':r.sha(source),
            'new_capacity':9,'expansion':derived['expanded_family_pool_contract'],
            'runtime_binding_required':True,'note':'Trainer saves may omit expansion marker; this external derivation contract remains mandatory for later resume.'}
        hashes[str(target)]=r.sha(target)
        del parent,derived,restored
    for p in BASE.glob('*.py'): hashes[str(p)]=r.sha(p)
    for p in (BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907').glob('train_candidate.py'): hashes[str(p)]=r.sha(p)
    with (BASE/'preparation.json').open('x',encoding='utf-8') as f: json.dump({'passed':True,'command':sys.orig_argv,'parents':parents,'input_sha256':hashes},f,indent=2)
    print('Two exclusive derived parents serialized and verified; no training hands.')
if __name__=='__main__': main()
