"""Terminal-only independent smoke verification; preserves all original evidence."""
from pathlib import Path
import hashlib
import importlib.util
import json
import random
import sys
import time
import psutil
import torch

BASE=Path(__file__).resolve().parents[1]
WRAPPER=BASE.parent/'v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
spec=importlib.util.spec_from_file_location('fresh_review_wrapper',WRAPPER)
wrapper=importlib.util.module_from_spec(spec); spec.loader.exec_module(wrapper)
trainer,_=wrapper.install()
sys.path.insert(0,str(BASE))
import run_smoke as run
s=run.s
read,sha,require=s.read,s.sha,s.require

def live(pid,ct):
    try:return abs(psutil.Process(int(pid)).create_time()-float(ct))<.001
    except psutil.NoSuchProcess:return False

def main():
    start=time.monotonic(); out=BASE/'terminal_review.json'
    require(not out.exists(),'preserve prior report')
    owner=read(BASE/'ownership.json'); require(not live(owner['pid'],owner['create_time']),'live owner')
    result=read(BASE/'smoke_result.json'); require(result['passed'] and len(result['runs'])==2,'incomplete smoke')
    hashes=dict(read(BASE/'input_contract.json')['input_sha256']); hashes[str(Path(__file__))]=sha(__file__)
    s.ctl.execution.check_hashes(hashes)
    torch.set_num_threads(1); counts=[0,0,0]; namespaces=set(); reports={}
    for seed in (1,3):
        folder=BASE/f'seed{seed}_smoke_v3'
        term,proc=read(folder/'termination.json'),read(folder/'process.json')
        require(term['exit_code']==0 and not term['observer_errors'] and not term['remaining_observed_child_pids'],'unclean termination')
        require(not live(proc['pid'],proc['create_time']) and len(term['observed_children'])>=12 and all(not live(i,c) for i,c in term['observed_children'].items()),'workers')
        binding=read(folder/'parent_contract.json')
        require(sha(binding['path'])==binding['sha256'],'parent hash')
        p=torch.load(binding['path'],map_location='cpu',weights_only=False)
        initial=torch.load(folder/'initial_resumed_state.pt',map_location='cpu',weights_only=False)
        final=torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
        gate=read(folder/'initial_resume_gate.json'); norm=s.normalized_pool(p,200)
        require(gate['passed'] and sha(folder/'initial_resumed_state.pt')==gate['initial_sha256'],'initial hash')
        require(all(s.state_equal(norm[k],initial[k]) for k in gate['exact_keys']),'initial exact state')
        require(all(c['config']['ppo_replay_ratio']==0 and c['config']['ppo_replay_buffer_iterations']==2 for c in (initial,final)),'configuration')
        require(p['ppo_replay_cumulative_rows']==initial['ppo_replay_cumulative_rows']==final['ppo_replay_cumulative_rows'],'replay counter reset/use')
        require(p['ppo_replay_rng_state']==initial['ppo_replay_rng_state']==final['ppo_replay_rng_state'],'replay RNG consumed')
        require([e['iteration'] for e in final['ppo_replay_entries']]==[final['iteration']-1,final['iteration']],'buffer not rolling')
        verify=read(folder/'verification.json')
        require(verify['passed'] and sha(folder/'latest.pt')==verify['checkpoint_sha256'],'final binding')
        require(s.ctl.prior.optimizer_step_audit(p,final,True)==verify['optimizer'],'Adam evidence')
        for c in (initial,final):
            s.ctl.route_audit(c,True,p); s.ctl.evidence.initial_reference('static',p,c,s.ctl.HELPER.equal)
        fixed={x['id'] for x in p['pool_snapshots'] if x['score_components'].get('kind')=='initial_external_opponent'}
        require(len(fixed)==7 and len(final['pool_snapshots'])==9 and fixed<={x['id'] for x in final['pool_snapshots']},'fixed pool lost')
        for name,info in read(folder/'prefixes.json').items():
            with (folder/name).open('rb') as f: require(hashlib.sha256(f.read(info['bytes'])).hexdigest()==info['sha256']==sha(Path(binding['path']).parent/name),'prefix')
        rows=s.ctl.execution.complete_jsonl(folder/'opponent_assignments.jsonl'); metrics=s.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl')
        suffix=[r for r in rows if p['iteration']<r['applies_to_iteration']<=final['iteration']]
        require([r['applies_to_iteration'] for r in suffix]==list(range(p['iteration']+1,final['iteration']+1)),'assignment coverage')
        new=[m for m in metrics if m['iteration']>p['iteration']]
        require([m['iteration'] for m in new]==list(range(p['iteration']+1,final['iteration']+1)) and all(m['ppo_replay_rows']==0 and m['ppo_replay_ratio']==0 for m in new),'actual replay use')
        args=read(folder/'command.json'); opt=lambda k:args[args.index(k)+1]
        rng=random.Random()
        recovered=trainer.restore_group_assignment_rng_from_evidence([r for r in rows if r['applies_to_iteration']<=p['iteration']],[m for m in metrics if m['iteration']<=p['iteration']],rng=rng,seed=int(opt('--seed')),worker_count=int(opt('--workers')),group_count=int(opt('--opponent-groups')),self_play_fraction=float(opt('--self-play-fraction')),checkpoint_iteration=p['iteration'],checkpoint_total_hands=p['total_hands'],replay_origin=p['assignment_replay_origin'],pool_size=9,pool_snapshot_ids=[x['id'] for x in p['pool_snapshots']])
        require(recovered['pending_assignments'] is None,'pending parent')
        first,_=trainer.build_group_opponent_assignments(worker_count=int(opt('--workers')),pool_size=9,group_count=int(opt('--opponent-groups')),self_play_fraction=float(opt('--self-play-fraction')),rng=rng,pool_weights=p['adaptive_opponent_weights'])
        require(first.tolist()==[w['opponent']['local_index'] for w in suffix[0]['workers']],'first RNG allocation')
        attempt=final['fixed_deal_attempt']; ns=attempt['receipt']['namespace']
        require(ns not in namespaces and ns!=p['fixed_deal_attempt']['receipt']['namespace'] and ns==gate['namespace']==verify['namespace'],'namespace reuse')
        require(sha(attempt['path'])==attempt['sha256'] and read(attempt['path'])==attempt['receipt'] and attempt['receipt']['parent_checkpoint_sha256']==binding['sha256'],'attempt binding')
        namespaces.add(ns)
        fr=read(folder/'fresh_only_runtime.json')
        require(sha(folder/'fresh_only_runtime.json')==verify['fresh_only_runtime_sha256'] and fr['parent_sha256']==binding['sha256'] and fr['hook_sha256']==sha(run.QUAL/'hook.py') and fr['wrapper_sha256']==sha(BASE/'train_candidate.py'),'runtime source binding')
        delta=[final['environment_hand_accounting']['completed_hands']-p['environment_hand_accounting']['completed_hands'],final['total_hands']-p['total_hands'],final['ppo_replay_cumulative_rows']-p['ppo_replay_cumulative_rows']]
        require(delta==[verify[k] for k in ('new_physical_hands','new_transition_hands','new_replay_rows')] and delta[0]>=16384 and delta[2]==0,'accounting')
        counts=[a+b for a,b in zip(counts,delta)]
        reports[str(seed)]=dict(passed=True,first_assignment_replayed=first.tolist(),completed_assignments=len(suffix),delta=delta,namespace=ns,wall_seconds=term['wall_seconds'])
        for f in folder.iterdir():
            if f.is_file(): hashes[str(f)]=sha(f)
    require(counts[0]==result['new_physical_hands'],'total')
    s.ctl.execution.check_hashes(hashes)
    report=dict(passed=True,command=sys.orig_argv,seeds=reports,training_hands=counts[0],transition_hands=counts[1],new_replay_rows=0,evaluation_hands=0,input_sha256=hashes,wall_seconds=time.monotonic()-start,scope='Both real statistical resumes and first assignment RNG verified; not bitwise worker RNG equivalence, unique training coverage or strength evidence.')
    with out.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2,allow_nan=False)
    print(json.dumps({k:report[k] for k in ('passed','training_hands','transition_hands','new_replay_rows','wall_seconds')}))

if __name__=='__main__':main()
