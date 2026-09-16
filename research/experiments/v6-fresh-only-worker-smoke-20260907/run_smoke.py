"""Bounded real-worker qualification; no automatic retry and no strength gate."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import psutil
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
QUAL=BASE.parent/'v6-fresh-only-retained-buffer-qualification-20260907'
PARENT=BASE.parent/'v6-family-allocation-two-seed-geometric-20260907'
sys.path.insert(0,str(BASE.parent/'v6-expanded-family-worker-smoke-20260907'))
import run_smoke_v3 as s
require,read,sha,write_new=s.require,s.read,s.sha,s.write_new
s.BASE=BASE
def logger(*args):
    import subprocess
    r=subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*args],capture_output=True,text=True,timeout=45)
    require(r.returncode==0,r.stderr)
s.logger=logger; s.ctl.execution.logger_update=logger

class Smoke(s.Smoke):
    def __init__(self):
        torch.set_num_threads(1)
        require(read(BASE/'experiment.json')['status']=='RUNNING','record')
        require(not (BASE/'ownership.json').exists(),'preserve prior attempt')
        require(shutil.disk_usage(BASE).free>10*1024**3,'disk')
        # Exact command-token inventory; do not print unrelated user command lines.
        conflicts=[p.pid for p in psutil.process_iter(['pid','name','cmdline']) if p.pid!=os.getpid() and 'python' in (p.info['name'] or '').lower() and any(Path(a).name in {'train_candidate.py','train_v5.py','run_smoke.py','run_trial.py'} for a in p.info['cmdline'] or [])]
        require(not conflicts,f'live research process IDs:{conflicts}')
        report=read(QUAL/'real_parent_check.json'); require(report['passed'],'qualification')
        self.inputs=dict(report['input_sha256'])
        self.inputs[str(QUAL/'real_parent_check.json')]=sha(QUAL/'real_parent_check.json')
        for module in list(sys.modules.values()):
            path=getattr(module,'__file__',None)
            if path and Path(path).suffix=='.py' and Path(path).is_relative_to(ROOT): self.inputs[str(Path(path))]=sha(path)
        for p in BASE.glob('*.py'): self.inputs[str(p)]=sha(p)
        for seed in (1,3):
            parent=PARENT/f'seed{seed}_control_stage2'
            for n in ('latest.pt','command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl','mixture_runtime.json'): self.inputs[str(parent/n)]=sha(parent/n)
        s.ctl.execution.check_hashes(self.inputs)
        write_new(BASE/'ownership.json',dict(pid=os.getpid(),create_time=psutil.Process().create_time(),command=sys.orig_argv))
        write_new(BASE/'input_contract.json',dict(input_sha256=self.inputs,extra_physical_hands_per_seed=16384,seeds=[1,3],no_automatic_retry=True,statistical_not_bitwise_resume=True))
        self.child,self.results,self.last_tick=None,[],0
        self.phase='READY'

    def run_seed(self,seed):
        path=PARENT/f'seed{seed}_control_stage2/latest.pt'
        parent=torch.load(path,map_location='cpu',weights_only=False)
        physical=parent['environment_hand_accounting']['completed_hands']; digest=sha(path)
        run=BASE/f'seed{seed}_smoke_v3'; run.mkdir()
        prefixes={}
        for n in ('h1_training_metrics.jsonl','opponent_assignments.jsonl'):
            source=path.parent/n; prefixes[n]=dict(sha256=sha(source),bytes=source.stat().st_size)
            shutil.copy2(source,run/n)
        write_new(run/'prefixes.json',prefixes)
        argv=read(path.parent/'command.json'); argv[0]=sys.executable; argv[2]=str(BASE/'train_candidate.py')
        settings={'--resume':path,'--run-dir':run,'--out':run/'latest.pt','--total-environment-hands':physical+16384,'--max-runtime-seconds':600,'--deal-attempt-registry':BASE/'attempt_registry','--opponent-assignment-provenance-file':run/'opponent_assignments.jsonl','--ppo-replay-ratio':0,'--ppo-replay-buffer-iterations':2}
        for k,v in settings.items(): s.ctl.execution.set_option(argv,k,v)
        prior_runtime=path.parent/'mixture_runtime.json'
        write_new(run/'parent_contract.json',dict(path=str(path),sha256=digest,physical_hands=physical,iteration=parent['iteration'],opponent_greedy_mixture=0.,prior_mixture_runtime=str(prior_runtime),prior_mixture_runtime_sha256=sha(prior_runtime),intentional_change='ratio0 with retained rolling buffer2'))
        norm=s.normalized_pool(parent,200)
        def capture(line):
            if '[Save] initial resume checkpoint' not in line:return
            target=run/'initial_resumed_state.pt'; require(not target.exists(),'duplicate initial')
            shutil.copy2(run/'latest.pt',target); initial=torch.load(target,map_location='cpu',weights_only=False)
            keys=list(s.ctl.prior.INITIAL_KEYS)+['adaptive_opponent_ema_rewards','adaptive_opponent_weights','adaptive_opponent_observations']
            require(all(s.state_equal(norm[k],initial[k]) for k in keys),'initial state mismatch')
            require(initial['environment_hand_accounting']['completed_hands']==physical,'counter reset')
            require(initial['config']['ppo_replay_ratio']==0 and initial['config']['ppo_replay_buffer_iterations']==2,'fresh-only config')
            require(len(initial['pool_snapshots'])==9 and initial['pool_strategy']=='anchor-latest','pool')
            s.ctl.route_audit(initial,True,parent); s.ctl.evidence.initial_reference('static',parent,initial,s.ctl.HELPER.equal)
            ns=initial['fixed_deal_attempt']['receipt']['namespace']
            require(ns!=parent['fixed_deal_attempt']['receipt']['namespace'] and ns not in [r['namespace'] for r in self.results],'namespace reuse')
            write_new(run/'initial_resume_gate.json',dict(passed=True,exact_keys=keys,namespace=ns,initial_sha256=sha(target),parent_sha256=digest,intentional_change='replay ratio0; retained buffer2 and cumulative replay counter'))
        self.phase=f'TRAINING_SEED{seed}'
        wall=self.execute(argv,run,capture,training=True)
        gate=read(run/'initial_resume_gate.json')
        final=torch.load(run/'latest.pt',map_location='cpu',weights_only=False)
        delta=final['environment_hand_accounting']['completed_hands']-physical
        require(delta>=16384,'below target; no retry')
        optimizer=s.ctl.prior.optimizer_step_audit(parent,final,True)
        require(not optimizer['new_state_ids'],'Adam reset')
        require(final['ppo_replay_cumulative_rows']==parent['ppo_replay_cumulative_rows'] and final['ppo_replay_rng_state']==parent['ppo_replay_rng_state'],'replay history/RNG changed')
        require(len(final['ppo_replay_entries'])==2 and final['ppo_replay_entries'][-1]['iteration']==final['iteration'],'rolling buffer missing')
        metrics=s.ctl.execution.complete_jsonl(run/'h1_training_metrics.jsonl')
        new=[r for r in metrics if r['iteration']>parent['iteration']]
        require([r['iteration'] for r in new]==list(range(parent['iteration']+1,final['iteration']+1)),'metric coverage')
        require(all(r['ppo_replay_ratio']==0 and r['ppo_replay_rows']==0 for r in new),'nonzero replay used')
        observation=read(run/'mixture_observation.json'); runtime=read(run/'fresh_only_runtime.json')
        require(observation['clean_return'] and observation['opponent_forward_rows']>0,'opponent execution')
        require(runtime['parent_sha256']==digest and runtime['ratio']==0 and runtime['buffer_iterations']==2,'runtime binding')
        for n,info in prefixes.items():
            with (run/n).open('rb') as f: require(hashlib.sha256(f.read(info['bytes'])).hexdigest()==info['sha256'],'prefix changed')
        result=dict(passed=True,seed=seed,new_physical_hands=delta,new_transition_hands=final['total_hands']-parent['total_hands'],new_replay_rows=0,historical_replay_rows=final['ppo_replay_cumulative_rows'],namespace=gate['namespace'],wall_seconds=wall,optimizer=optimizer,checkpoint_sha256=sha(run/'latest.pt'),fresh_only_runtime_sha256=sha(run/'fresh_only_runtime.json'),completed_iterations=len(new))
        write_new(run/'verification.json',result); self.results.append(result)
        logger('--artifact',str(run/'verification.json'),'--artifact',str(run/'initial_resume_gate.json'))
        self.tick(force=True)

def main():
    for k in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):os.environ[k]='1'
    smoke=Smoke()
    for seed in (1,3):smoke.run_seed(seed)
    write_new(BASE/'smoke_result.json',dict(passed=True,runs=smoke.results,new_physical_hands=sum(r['new_physical_hands'] for r in smoke.results),evaluation_hands=0))
    logger('--artifact',str(BASE/'smoke_result.json'),'--metric','smoke_complete=true')

if __name__=='__main__':main()
