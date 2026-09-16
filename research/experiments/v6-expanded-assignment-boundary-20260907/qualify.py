"""Replay real preserved assignment chains; fail closed on pending old-pool work."""
from pathlib import Path
import importlib.util
import json
import random
import sys
import torch

BASE=Path(__file__).resolve().parent
QUAL=BASE.parent/'v6-expanded-family-pool-qualification-20260907'
sys.path.insert(0,str(QUAL))
import real_parent_check as r
from expand import expand

def main():
    r.require(not (BASE/'report.json').exists(),'preserve report')
    torch.set_num_threads(1)
    prior=r.read(QUAL/'real_parent_report.json'); r.require(prior['passed'],'qualification')
    for p,h in prior['input_sha256'].items(): r.require(r.sha(Path(p))==h,'changed qualified source')
    panel=r.read(BASE.parent/'v6-heldout-panel-qualification-20260907/qualification.json')
    adds=[{**panel['candidates'][n],'checkpoint':torch.load(panel['candidates'][n]['path'],map_location='cpu',weights_only=False)} for n in ('moving_s1','moving_s3','half_lr_s1','half_lr_s3')]
    wrapper=BASE.parent/'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
    spec=importlib.util.spec_from_file_location('boundary_integration',wrapper); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    trainer,binding=m.install(); reports={}; hashes={str(Path(__file__)):r.sha(Path(__file__)),**prior['input_sha256']}
    for seed in (1,3):
        folder=r.TRIAL/f'seed{seed}_control_stage2'
        p=torch.load(folder/'latest.pt',map_location='cpu',weights_only=False); q=expand(p,adds)
        with (folder/'opponent_assignments.jsonl').open(encoding='utf-8') as f: records=[json.loads(x) for x in f if x.strip()]
        with (folder/'h1_training_metrics.jsonl').open(encoding='utf-8') as f: metrics=[json.loads(x) for x in f if x.strip()]
        argv=r.read(folder/'command.json')
        def option(flag): return argv[argv.index(flag)+1]
        kwargs={'seed':int(option('--seed')),'worker_count':int(option('--workers')),
            'group_count':int(option('--opponent-groups')),'self_play_fraction':float(option('--self-play-fraction')),
            'checkpoint_iteration':p['iteration'],'checkpoint_total_hands':p['total_hands'],'replay_origin':p['assignment_replay_origin']}
        oldrng,newrng=random.Random(0),random.Random(1)
        old=trainer.restore_group_assignment_rng_from_evidence(records,metrics,rng=oldrng,pool_size=5,pool_snapshot_ids=[s['id'] for s in p['pool_snapshots']],**kwargs)
        r.require(old['pending_assignments'] is None,'pending old-pool work requires separate explicit segment; do not discard or rewrite')
        new=trainer.restore_group_assignment_rng_from_evidence(records,metrics,rng=newrng,pool_size=9,pool_snapshot_ids=[s['id'] for s in q['pool_snapshots']],**kwargs)
        r.require(new==old and newrng.getstate()==oldrng.getstate(),'reconstruction changed')
        origin=newrng.getstate()
        draw={'worker_count':kwargs['worker_count'],'pool_size':9,'group_count':kwargs['group_count'],
            'self_play_fraction':kwargs['self_play_fraction'],'pool_weights':q['adaptive_opponent_weights']}
        assignment,summary=trainer.build_group_opponent_assignments(rng=newrng,**draw)
        check=random.Random(); check.setstate(origin)
        again,_=trainer.build_group_opponent_assignments(rng=check,**draw)
        r.require(assignment.tolist()==again.tolist() and check.getstate()==newrng.getstate(),'redraw not deterministic')
        for name in ('latest.pt','command.json','opponent_assignments.jsonl','h1_training_metrics.jsonl'): hashes[str(folder/name)]=r.sha(folder/name)
        reports[str(seed)]={'records_verified':old['records_verified'],'tail_iteration':old['tail_iteration'],
            'checkpoint_iteration':p['iteration'],'tail_sha256':old['tail_sha256'],'pending_old_assignment':False,
            'restored_rng_identical':True,'first_nine_slot_assignment':assignment.tolist(),
            'next_iteration':p['iteration']+1,'no_prefix_rewrite_needed':True}
        del p,q,records,metrics
    for p,h in hashes.items(): r.require(r.sha(Path(p))==h,'input changed')
    value={'passed':True,'command':sys.orig_argv,'input_sha256':hashes,'parents':reports,'binding':binding,
        'new_training_hands':0,'evaluation_hands':0,'scope':'Both actual parents end at consumed assignment tails. Existing trainer replay already restores RNG and draws next nine-slot assignment without editing old evidence. No live-worker qualification yet.'}
    with (BASE/'report.json').open('x',encoding='utf-8') as f: json.dump(value,f,indent=2)
    print(json.dumps({'passed':True,'parents':reports}))
if __name__=='__main__': main()
