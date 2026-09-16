"""Zero-hand real retained-buffer checks. No checkpoint mutation or trainer main."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import sys
import time
import torch
from hook import install

BASE=Path(__file__).resolve().parent
PARENT=BASE.parent/'v6-family-allocation-two-seed-geometric-20260907'
WRAPPER=BASE.parent/'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def require(ok,msg):
    if not ok: raise ValueError(msg)

def main():
    start=time.monotonic(); out=BASE/'real_parent_check.json'
    require(not out.exists(),'preserve report')
    spec=importlib.util.spec_from_file_location('fresh_replay_wrapper',WRAPPER)
    wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
    trainer,binding=wrapper.install(); hook=install(trainer)
    torch.set_num_threads(1)
    inputs={str(p):sha(p) for p in BASE.glob('*.py')}
    inputs[str(WRAPPER)]=sha(WRAPPER); inputs[str(Path(trainer.__file__))]=sha(trainer.__file__)
    inputs[str(PARENT/'post_terminal_review.json')]=sha(PARENT/'post_terminal_review.json')
    prior=read(PARENT/'post_terminal_review.json'); reports={}
    for seed in (1,3):
        p=PARENT/f'seed{seed}_control_stage2/latest.pt'; digest=sha(p)
        require(digest==prior['input_sha256'][str(p)],'parent hash')
        inputs[str(p)]=digest
        ckpt=torch.load(p,map_location='cpu',weights_only=False)
        entries=ckpt['ppo_replay_entries']
        require(len(entries)==2 and len(ckpt['optimizer']['state'])==86,'retained buffer/Adam')
        require(entries[-1]['iteration']==ckpt['iteration'],'buffer checkpoint boundary')
        def replay_digest():
            h=hashlib.sha256()
            for e in entries:
                h.update(str(e['iteration']).encode())
                for block in e['blocks']:
                    h.update(str(len(block)).encode())
                    for t in block: h.update(trainer.transition_digest(t).encode())
            return h.hexdigest()
        before=replay_digest()
        rng=random.Random(); rng.setstate(ckpt['ppo_replay_rng_state']); state=rng.getstate()
        zero,zi=trainer.sample_replay_hand_blocks(entries,0,rng)
        require(zero==[] and zi['rows']==zi['hands']==0 and rng.getstate()==state,'zero target consumed replay/RNG')
        control,ci=trainer.sample_replay_hand_blocks(entries,4096,rng)
        require(ci['rows']==len(control)>=4096 and rng.getstate()!=state,'positive target no sampling')
        require(before==replay_digest(),'sampler mutated retained entries')
        require(sha(p)==digest,'checkpoint changed')
        reports[str(seed)]=dict(parent=str(p),parent_sha256=digest,iteration=ckpt['iteration'],physical_hands=ckpt['environment_hand_accounting']['completed_hands'],transition_hands=ckpt['total_hands'],historical_replay_rows=ckpt['ppo_replay_cumulative_rows'],replay_digest=before,buffer_entries=len(entries),zero_sampling=zi,positive_sampling=ci,zero_sampling_preserves_rng=True,sampler_preserves_buffer=True)
        del ckpt,entries,control
    require(all(sha(p)==h for p,h in inputs.items()),'inputs changed')
    report=dict(passed=True,command=sys.orig_argv,hook=hook,seeds=reports,input_sha256=inputs,training_hands=0,evaluation_hands=0,wall_seconds=time.monotonic()-start,scope='Parser/main binding and actual saved-buffer sampling qualified; not an actual resumed worker/optimizer update or poker strength test. Production requires real-worker smoke and terminal review.')
    with out.open('x',encoding='utf-8') as f: json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps(dict(passed=True,seeds=reports,wall_seconds=report['wall_seconds'])))

if __name__=='__main__': main()
