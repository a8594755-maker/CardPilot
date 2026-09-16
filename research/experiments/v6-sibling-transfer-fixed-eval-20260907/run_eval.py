"""Fixed evaluation controller; reuse qualified process/evidence handling."""
from pathlib import Path
from datetime import datetime, timezone
import json
import os
import sys
import subprocess
import time
import psutil

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
TRIAL=BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907'
sys.path.insert(0,str(TRIAL))
import run_trial as old
ex=old.ctl.execution
read,sha,require,write_new=old.read,old.sha,old.require,old.write_new
ORDER=((1,'control'),(1,'mixture'),(3,'control'),(3,'mixture'))
def logger(*args):
    r=subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*args],cwd=ROOT,capture_output=True,text=True)
    require(r.returncode==0,r.stderr)
def command(seed,arm,config):
    endpoint=TRIAL/f'seed{seed}_{arm}_stage2/latest.pt'
    parent=read(TRIAL/f'seed{seed}_{arm}_stage1/parent_contract.json')['path']
    argv=[sys.executable,'-B','-u',str(ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),'--control',parent,'--treatment',str(endpoint)]
    for name,path in config['anchors'].items(): argv+=['--anchor',f'{name}={path}']
    return argv+['--pairs-per-anchor','1024','--seed',str(20265901+10*seed),'--device','cuda','--out-dir',str(BASE/f'eval_seed{seed}_{arm}')]
class Controller:
    execute=ex.Controller.execute
    def __init__(self):
        self.q=read(BASE/'preflight.json'); require(self.q['passed'],'preflight')
        require(read(BASE/'experiment.json')['status']=='RUNNING','record')
        require(not (BASE/'ownership.json').exists(),'prior attempt needs review')
        conflicts=[p.pid for p in psutil.process_iter(['pid','name','cmdline']) if p.pid!=os.getpid()
            and 'python' in (p.info['name'] or '').lower() and any(Path(a).name in
            {'run_eval.py','run_trial.py','train_candidate.py','train_v5.py','v6_public_opponent_matched_eval.py'} for a in p.info['cmdline'] or [])]
        require(not conflicts,f'live research process {conflicts}')
        self.inputs=self.q['input_sha256']; ex.check_hashes(self.inputs)
        self.sources={p:h for p,h in self.inputs.items() if p.endswith('.py')}
        self.child=None; self.started=time.perf_counter(); self.last_tick=0; self.phase='READY'
        self.owner={'pid':os.getpid(),'create_time':psutil.Process().create_time(),'command':sys.orig_argv}
        write_new(BASE/'ownership.json',self.owner)
        ex.logger_update=logger
    def tick(self,force=False):
        if not force and time.perf_counter()-self.last_tick<60: return
        ex.check_hashes(self.sources)
        n=sum(4*ex.gzip_count(p) for p in BASE.glob('eval_*/common_deck_pairs.jsonl.gz'))
        from research.experiment_log import atomic_json
        atomic_json(BASE/'status.json',{**self.owner,'phase':self.phase,'evaluation_hands':n,
            'active_child_pid':self.child.pid if self.child and self.child.poll() is None else None,
            'updated_at':datetime.now(timezone.utc).isoformat()})
        logger('--count',f'evaluation_hands={n}','--metric','controller_phase='+self.phase)
        print(json.dumps({'phase':self.phase,'evaluation_hands':n}),flush=True); self.last_tick=time.perf_counter()
    def run(self):
        try:
            for seed,arm in ORDER:
                job=BASE/f'job_seed{seed}_{arm}'; job.mkdir()
                self.phase=f'EVALUATING_seed{seed}_{arm}'; self.execute(command(seed,arm,self.q),job)
                out=BASE/f'eval_seed{seed}_{arm}'; s=read(out/'summary.json')
                require(s['status']=='COMPLETED' and s['evaluation_hands']==20480,'count')
                require(sha(out/'common_deck_pairs.jsonl.gz')==s['raw_pairs_sha256'],'raw hash')
            self.phase='COMPLETE_REQUIRES_RAW_REVIEW'
            write_new(BASE/'controller_result.json',{'phase':self.phase,'wall_seconds':time.perf_counter()-self.started,'goal_achieved':False})
        except Exception as exc:
            self.phase='ERROR_PRESERVED_REVIEW'; write_new(BASE/'controller_error.json',{'error':repr(exc)}); raise
        finally: self.tick(force=True)
if __name__=='__main__': Controller().run()
