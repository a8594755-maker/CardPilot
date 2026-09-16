"""Two real retained-parent GPU resumes; fixed 16,384 extra physical hands each."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import psutil
import torch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
OLD = ROOT / 'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906'
PARENTS = ROOT / 'research/experiments/v6-anchor-recent-two-seed-geometric-20260907'
sys.path.insert(0, str(OLD))
import run_actor_control as ctl
require, read, sha, write_new = ctl.require, ctl.read, ctl.sha, ctl.write_new
EXPECTED = {1: '819bfdd9ea0b9625a2e6e2528cbd7be5d984667a463d1ac14f70a44b4091dd85',
            3: 'df2d4c7cdac0aba5c88c03e43922b8b0a55e57341868ea62bfe5adbbe0a2a7b5'}


def logger(*args):
    result = subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'),
        'update', BASE.name, *args], cwd=ROOT, capture_output=True, text=True, timeout=45)
    require(result.returncode == 0, result.stderr)


ctl.execution.logger_update = logger


class Smoke:
    execute = ctl.execution.Controller.execute

    def __init__(self):
        torch.set_num_threads(1)
        require(read(BASE/'experiment.json')['status'] == 'RUNNING', 'record not running')
        conflicts = [p.pid for p in psutil.process_iter(['pid', 'name', 'cmdline'])
            if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower() and any(Path(a).name in {
                'train_candidate.py', 'train_v5.py', 'run_smoke.py', 'run_scale.py', 'run_pair.py'}
                for a in p.info['cmdline'] or [])]
        require(not conflicts, f'live research owner: {conflicts}')
        require(shutil.disk_usage(BASE).free > 10*1024**3, 'disk space')
        require(not any((BASE/f'seed{s}_smoke').exists() for s in EXPECTED), 'existing attempt; no retry')
        write_new(BASE/'smoke_ownership.json', {'pid':os.getpid(),
            'create_time':psutil.Process().create_time(), 'command':sys.orig_argv})
        self.inputs = {str(p):sha(p) for p in BASE.glob('*.py')}
        for seed, digest in EXPECTED.items():
            self.inputs[str(PARENTS/f'seed{seed}_recent_stage2/latest.pt')] = digest
        ctl.execution.check_hashes(self.inputs)
        write_new(BASE/'smoke_input_contract.json', {'input_sha256':self.inputs,
            'extra_physical_target_per_seed':16384, 'seeds':[1,3],
            'statistical_not_bitwise_worker_continuation':True,
            'strength_evaluation':False, 'no_automatic_retry':True})
        self.child, self.results, self.last_tick = None, [], 0
        self.phase = 'READY'

    def tick(self, force=False):
        if not force and time.perf_counter()-self.last_tick < 60:
            return
        self.last_tick = time.perf_counter()
        ctl.execution.check_hashes(self.inputs)
        logger('--metric', 'smoke_phase='+self.phase,
               '--count', 'training_hands='+str(sum(r['new_physical_hands'] for r in self.results)))

    def run_seed(self, seed):
        path = PARENTS/f'seed{seed}_recent_stage2/latest.pt'
        parent = torch.load(path, map_location='cpu', weights_only=False)
        physical = parent['environment_hand_accounting']['completed_hands']
        run = BASE/f'seed{seed}_smoke'
        run.mkdir()
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = path.parent/name
            prefixes[name] = {'sha256':sha(source), 'bytes':source.stat().st_size}
            shutil.copy2(source, run/name)
        write_new(run/'prefixes.json', prefixes)
        argv = read(path.parent/'command.json')
        argv[0], argv[2] = sys.executable, str(BASE/'train_candidate.py')
        settings = {'--resume':path, '--run-dir':run, '--out':run/'latest.pt',
            '--pool-strategy':'anchor-latest', '--opponent-greedy-mixture':0.5, '--total-environment-hands':physical+16384,
            '--max-runtime-seconds':600, '--deal-attempt-registry':BASE/'attempt_registry',
            '--opponent-assignment-provenance-file':run/'opponent_assignments.jsonl'}
        for flag, value in settings.items():
            ctl.execution.set_option(argv, flag, value)
        write_new(run/'parent_contract.json', {'path':str(path), 'sha256':EXPECTED[seed],
            'physical_hands':physical, 'iteration':parent['iteration']})

        def capture(line):
            if '[Save] initial resume checkpoint' not in line:
                return
            target = run/'initial_resumed_state.pt'
            require(not target.exists(), 'initial already captured')
            shutil.copy2(run/'latest.pt', target)
            initial = torch.load(target, map_location='cpu', weights_only=False)
            keys = list(ctl.prior.INITIAL_KEYS)
            keys += ['adaptive_opponent_ema_rewards', 'adaptive_opponent_weights', 'adaptive_opponent_observations']
            for key in keys:
                require(ctl.HELPER.equal(parent[key], initial[key]), 'initial state changed: '+key)
            require(initial['pool_strategy'] == initial['config']['pool_strategy'] == 'anchor-latest', 'strategy not active')
            require(initial['environment_hand_accounting']['completed_hands'] == physical, 'physical reset')
            ctl.route_audit(initial, True, parent)
            ctl.evidence.initial_reference('static', parent, initial, ctl.HELPER.equal)
            namespace = initial['fixed_deal_attempt']['receipt']['namespace']
            require(namespace != parent['fixed_deal_attempt']['receipt']['namespace'], 'parent namespace reused')
            require(namespace not in [r['namespace'] for r in self.results], 'smoke namespace reused')
            write_new(run/'initial_resume_gate.json', {'passed':True, 'exact_keys':keys,
                'intentional_change':'opponent execution mixture only; new managed attempt namespace',
                'namespace':namespace, 'parent_sha256':EXPECTED[seed], 'initial_sha256':sha(target)})

        self.phase = f'TRAINING_SEED{seed}'
        wall = self.execute(argv, run, capture, training=True)
        gate = read(run/'initial_resume_gate.json')
        observation = read(run/'mixture_observation.json')
        runtime = read(run/'mixture_runtime.json')
        require(observation['clean_return'] and observation['opponent_forward_rows'] > 0, 'mixture not executed')
        require(observation['runtime_sha256'] == sha(run/'mixture_runtime.json') and runtime['greedy_weight'] == .5, 'mixture runtime changed')
        require(runtime['parent_sha256'] == EXPECTED[seed], 'mixture parent differs')
        batch = observation['first_batch']
        for original, actual, greedy in zip(batch['original_probabilities'], batch['mixture_probabilities'], batch['greedy_actions']):
            require(all(abs(p - (.5*q + (.5 if i == greedy else 0))) < 1e-6 for i,(p,q) in enumerate(zip(actual,original))), 'actual mixture probabilities wrong')
        final = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        new_physical = final['environment_hand_accounting']['completed_hands']-physical
        require(new_physical >= 16384, 'natural boundary below target; no restart')
        optimizer = ctl.prior.optimizer_step_audit(parent, final, True)
        require(not optimizer['new_state_ids'], 'optimizer state reset')
        require(final['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'], 'replay did not advance')
        candidates = [r for r in final['pool_candidate_history'] if int(r['iteration']) > int(parent['iteration'])]
        require(len(candidates) >= 2 and all(r['selected'] for r in candidates), 'recent candidates not admitted')
        require({0,1,2}.issubset({s['id'] for s in final['pool_snapshots']}), 'anchor lost')
        for name, prefix in prefixes.items():
            with (run/name).open('rb') as handle:
                require(hashlib.sha256(handle.read(prefix['bytes'])).hexdigest() == prefix['sha256'], 'prefix changed')
        result = {'passed':True, 'seed':seed, 'new_physical_hands':new_physical,
            'new_transition_hands':final['total_hands']-parent['total_hands'],
            'new_replay_rows':final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows'],
            'namespace':gate['namespace'], 'wall_seconds':wall, 'optimizer':optimizer,
            'new_candidates':candidates, 'checkpoint_sha256':sha(run/'latest.pt'),
            'scope':'Actual trainer resume and bounded rollout; not strength evidence or full deck audit'}
        write_new(run/'verification.json', result)
        self.results.append(result)
        logger('--artifact', str(run/'verification.json'), '--artifact', str(run/'initial_resume_gate.json'))
        self.tick(force=True)


def main():
    for key in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key] = '1'
    smoke = Smoke()
    for seed in (1,3):
        smoke.run_seed(seed)
    write_new(BASE/'smoke_result.json', {'passed':True, 'runs':smoke.results,
        'new_physical_hands':sum(r['new_physical_hands'] for r in smoke.results),
        'evaluation_hands':0, 'final_qualification_hands':0})
    logger('--artifact', str(BASE/'smoke_result.json'), '--metric', 'smoke_complete=true')


if __name__ == '__main__':
    main()
