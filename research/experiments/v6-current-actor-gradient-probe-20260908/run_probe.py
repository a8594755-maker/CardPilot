"""Reuse established managed training lifecycle, enabling observation only."""
from datetime import datetime, timezone
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import time
import psutil
import torch

BASE = Path(__file__).resolve().parent
PARENT = BASE.parent/'v6-fresh-only-two-seed-geometric-20260907'
SOURCE = BASE.parent/'v6-expanded-family-two-seed-geometric-20260907/run_trial.py'
spec = importlib.util.spec_from_file_location('gradient_probe_lifecycle', SOURCE)
old = importlib.util.module_from_spec(spec); spec.loader.exec_module(old)
old.BASE = BASE
old.PARENTS = PARENT
old.WRAPPER = BASE.parent/'v6-opponent-execution-mixture-two-seed-geometric-20260907/train_candidate.py'
old.DOSES = {1:16384}
old.STRATEGIES = {'control':'anchor-latest'}
old.CAPACITY = {'control':9}
old.ORDER = [(1,'control'),(3,'control')]
original_command = old.training_command


def training_command(seed, arm, stage):
    argv = original_command(seed, arm, stage)
    if '--gradient-diagnostic-minibatches' in argv:
        old.ctl.execution.set_option(argv, '--gradient-diagnostic-minibatches', 1)
    else:
        argv += ['--gradient-diagnostic-minibatches', '1']
    old.ctl.execution.set_option(argv, '--max-runtime-seconds', 600)
    return argv


old.training_command = training_command


class Probe(old.Controller):
    def __init__(self):
        torch.set_num_threads(1)
        old.require(old.read(BASE/'experiment.json')['status']=='RUNNING', 'record')
        old.require(not (BASE/'ownership.json').exists(), 'existing attempt requires review')
        conflicts = [p.pid for p in psutil.process_iter(['pid','name','cmdline']) if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower() and any(Path(a).name in {'run_probe.py','run_trial.py','train_candidate.py','train_v5.py','run.py'} for a in p.info['cmdline'] or [])]
        old.require(not conflicts, f'live research processes:{conflicts}')
        old.require(shutil.disk_usage(BASE).free>15*1024**3,'disk')
        review = old.read(PARENT/'post_terminal_review.json')
        old.require(review['passed'], 'parent experiment evidence')
        prior = old.read(PARENT/'input_contract.json')['input_sha256']
        self.inputs = {p:h for p,h in prior.items() if p.endswith('.py')}
        self.inputs.update({str(SOURCE):old.sha(SOURCE),str(BASE/'run_probe.py'):old.sha(BASE/'run_probe.py'),str(BASE/'protocol.md'):old.sha(BASE/'protocol.md')})
        self.namespaces = set(review['namespaces'])
        self.namespaces.update(old.read(PARENT/'qualification.json')['known_namespaces'])
        parents = {}
        for seed in (1,3):
            folder = PARENT/f'seed{seed}_control_stage2'
            path = folder/'latest.pt'
            digest = old.sha(path)
            old.require(digest == old.read(folder/'verification.json')['checkpoint_sha256'], 'parent hash')
            checkpoint = torch.load(path,map_location='cpu',weights_only=False)
            old.INITIAL[seed] = checkpoint['environment_hand_accounting']['completed_hands']
            old.EXPECTED[seed] = digest
            parents[f'{seed}_control'] = digest
            self.namespaces.add(checkpoint['fixed_deal_attempt']['receipt']['namespace'])
            for name in ('latest.pt','command.json','h1_training_metrics.jsonl','opponent_assignments.jsonl','mixture_runtime.json'):
                self.inputs[str(folder/name)] = old.sha(folder/name)
            del checkpoint
        old.ctl.execution.check_hashes(self.inputs)
        old.write_new(BASE/'qualification.json',dict(parent_sha256=parents, scope='Existing frozen trainer/resume lifecycle; diagnostic observer only. Not a new trainer qualification.'))
        self.inputs[str(BASE/'qualification.json')] = old.sha(BASE/'qualification.json')
        self.sources = {p:h for p,h in self.inputs.items() if p.endswith('.py')}
        self.corpus = {}
        self.started,self.last_tick,self.child = time.perf_counter(),0,None
        self.results,self.phase = [],'READY'
        self.owner = dict(pid=os.getpid(),create_time=psutil.Process().create_time(),started_at=datetime.now(timezone.utc).isoformat(),command=sys.orig_argv)
        old.write_new(BASE/'ownership.json',self.owner)
        old.write_new(BASE/'input_contract.json',dict(input_sha256=self.inputs,initial=old.INITIAL,doses=old.DOSES,statistical_not_bitwise_resume=True))


def main():
    for key in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key] = '1'
    probe = Probe()
    for seed in (1,3):
        probe.train(seed,'control',1)
        folder = old.directory(seed,'control',1)
        boundary = old.read(folder/'parent_contract.json')['iteration']
        rows = [r for r in old.ctl.execution.complete_jsonl(folder/'h1_training_metrics.jsonl') if r['iteration']>boundary]
        old.require(rows and all(r.get('gradient_diagnostics') for r in rows),'missing diagnostics')
        old.write_new(folder/'gradient_probe.json',dict(seed=seed,rows=[dict(iteration=r['iteration'],gradient_diagnostics=r['gradient_diagnostics'],approx_kl=r['approx_kl'],entropy=r['entropy'],reference_policy_kl=r['reference_policy_kl']) for r in rows]))
    old.ctl.execution.check_hashes(probe.inputs)
    old.write_new(BASE/'terminal.json',dict(status='COMPLETE_REVIEW_REQUIRED',runs=probe.results,wall_seconds=time.perf_counter()-probe.started))
    probe.tick(force=True)


if __name__=='__main__':
    main()
