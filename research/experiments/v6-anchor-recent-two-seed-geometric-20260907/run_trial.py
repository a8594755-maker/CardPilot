"""Fixed matched anchor-latest/loss-kbest trial; single owner, no automatic retries."""
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
OLD = ROOT/'research/experiments/v6-preflop-actor-trunk-two-seed-geometric-20260906'
PARENTS = ROOT/'research/experiments/v6-preflop-actor-route-2m-continuation-20260906'
WRAPPER = ROOT/'research/experiments/v6-anchor-recent-trainer-integration-20260907/train_candidate.py'
sys.path.insert(0,str(OLD))
import run_actor_control as ctl
require,read,sha,write_new = ctl.require,ctl.read,ctl.sha,ctl.write_new
EXPECTED = {1:'c9459d471dbaea0662533633631fb3b86a8e7d164238a887098aabe72d1c29e3',
            3:'d2c7acdde6e97eec6290c07904943fbcda734d5acec57bb7e89cd12843136e23'}
INITIAL = {1:12595669,3:12591968}
DOSES = {1:262144,2:1048576}
STRATEGIES = {'control':'loss-kbest','recent':'anchor-latest'}
ORDER = [(1,'control'),(1,'recent'),(3,'recent'),(3,'control')]
EVAL_SEEDS = {(seed,stage):20265000+seed*10+stage for seed in (1,3) for stage in (1,2)}

def directory(seed,arm,stage):
    require(seed in INITIAL and arm in STRATEGIES and stage in DOSES,'unknown cell')
    return BASE/f'seed{seed}_{arm}_stage{stage}'

def parent_path(seed,arm,stage):
    directory(seed,arm,stage)
    return PARENTS/f'seed{seed}_connected_stage3/latest.pt' if stage == 1 else directory(seed,arm,1)/'latest.pt'

def logger(*args):
    result = subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*args],
        cwd=ROOT,capture_output=True,text=True,timeout=45)
    require(result.returncode == 0,result.stderr)

ctl.execution.logger_update = logger

def additional_count(current,parent):
    require(current >= parent,'live counter reset')
    return current-parent

def training_command(seed,arm,stage):
    run,path = directory(seed,arm,stage),parent_path(seed,arm,stage)
    argv = read((PARENTS/f'seed{seed}_connected_stage3')/'command.json')
    argv[0],argv[2] = sys.executable,str(WRAPPER)
    for flag,value in {'--resume':path,'--run-dir':run,'--out':run/'latest.pt',
        '--pool-strategy':STRATEGIES[arm],'--total-environment-hands':INITIAL[seed]+DOSES[stage],
        '--max-runtime-seconds':7200,'--deal-attempt-registry':BASE/'attempt_registry',
        '--opponent-assignment-provenance-file':run/'opponent_assignments.jsonl'}.items():
        ctl.execution.set_option(argv,flag,value)
    return argv

class Controller:
    execute = ctl.execution.Controller.execute

    def __init__(self):
        torch.set_num_threads(1)
        require(read(BASE/'experiment.json')['status'] == 'RUNNING','record not running')
        conflicts = [p.pid for p in psutil.process_iter(['pid','name','cmdline'])
            if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower()
            and any(Path(a).name in {'run_trial.py','train_candidate.py','train_v5.py','run_pair.py','run_scale.py','run_smoke.py'}
                for a in p.info['cmdline'] or [])]
        require(not conflicts,f'live research owner: {conflicts}')
        require(not (BASE/'ownership.json').exists(),'prior attempt requires review')
        require(not any(directory(seed,arm,stage).exists() for stage in DOSES for seed,arm in ORDER),'existing output preserved')
        qualification = read(BASE/'qualification.json')
        require(qualification['passed'] and qualification['tests_passed'] >= 6,'controller not qualified')
        self.inputs = dict(qualification['input_sha256'])
        self.inputs[str(BASE/'qualification.json')] = sha(BASE/'qualification.json')
        ctl.execution.check_hashes(self.inputs)
        require(shutil.disk_usage(BASE).free > 15*1024**3,'disk space')
        self.corpus = dict(qualification['prior_corpus'])
        self.namespaces = set(qualification['known_namespaces'])
        self.sources = {p:h for p,h in self.inputs.items() if p.endswith('.py')}
        self.started,self.last_tick,self.child = time.perf_counter(),0,None
        self.results,self.phase = [],'READY'
        self.owner = {'pid':os.getpid(),'create_time':psutil.Process().create_time(),
            'started_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv}
        write_new(BASE/'ownership.json',self.owner)
        write_new(BASE/'input_contract.json',{'input_sha256':self.inputs,'doses':DOSES,
            'initial_physical_hands':INITIAL,'statistical_not_bitwise_worker_continuation':True})
        logger('--command',subprocess.list2cmdline(sys.orig_argv),'--artifact',str(BASE/'ownership.json'),
            '--artifact',str(BASE/'input_contract.json'))

    def tick(self,force=False):
        if not force and time.perf_counter()-self.last_tick < 60:
            return
        ctl.execution.check_hashes(self.sources)
        counts = {'training_hands':0,'transition_hands':0,'evaluation_hands':0,'final_qualification_hands':0}
        for stage in DOSES:
            for seed,arm in ORDER:
                run = directory(seed,arm,stage)
                if not (run/'parent_contract.json').exists():
                    continue
                parent = read(run/'parent_contract.json')
                metrics = ctl.execution.complete_jsonl(run/'h1_training_metrics.jsonl')
                if metrics:
                    counts['training_hands'] += additional_count(metrics[-1]['environment_hand_accounting']['completed_hands'],parent['physical_hands'])
                    counts['transition_hands'] += additional_count(metrics[-1]['hands'],parent['transition_hands'])
        for path in BASE.glob('eval_*/common_deck_pairs.jsonl.gz'):
            counts['evaluation_hands'] += 4*ctl.execution.gzip_count(path)
        from research.experiment_log import atomic_json
        atomic_json(BASE/'status.json',{**self.owner,'phase':self.phase,'counts':counts,
            'active_child_pid':self.child.pid if self.child and self.child.poll() is None else None,
            'wall_seconds':time.perf_counter()-self.started,'updated_at':datetime.now(timezone.utc).isoformat()})
        logger(*[part for key,value in counts.items() for part in ('--count',f'{key}={value}')],
            '--metric','controller_phase='+self.phase)
        print(json.dumps({'phase':self.phase,**counts}),flush=True)
        self.last_tick = time.perf_counter()

    def train(self, seed, arm, stage):
        path = parent_path(seed, arm, stage)
        digest = sha(path)
        require(digest == (EXPECTED[seed] if stage == 1 else read(path.parent/'verification.json')['checkpoint_sha256']), 'parent hash')
        parent = torch.load(path, map_location='cpu', weights_only=False)
        physical = parent['environment_hand_accounting']['completed_hands']
        run = directory(seed, arm, stage)
        run.mkdir()
        prefixes = {}
        for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
            source = path.parent/name
            prefixes[name] = {'sha256':sha(source), 'bytes':source.stat().st_size}
            shutil.copy2(source, run/name)
        write_new(run/'prefixes.json', prefixes)
        argv = training_command(seed,arm,stage)
        write_new(run/'parent_contract.json', {'path':str(path), 'sha256':digest,
            'physical_hands':physical, 'transition_hands':parent['total_hands'], 'iteration':parent['iteration']})

        def capture(line):
            if '[Save] initial resume checkpoint' not in line:
                return
            target = run/'initial_resumed_state.pt'
            require(not target.exists(), 'initial already captured')
            shutil.copy2(run/'latest.pt', target)
            initial = torch.load(target, map_location='cpu', weights_only=False)
            keys = [k for k in ctl.prior.INITIAL_KEYS if k != 'pool_strategy']
            keys += ['adaptive_opponent_ema_rewards', 'adaptive_opponent_weights', 'adaptive_opponent_observations']
            for key in keys:
                require(ctl.HELPER.equal(parent[key], initial[key]), 'initial state changed: '+key)
            require(initial['pool_strategy'] == initial['config']['pool_strategy'] == STRATEGIES[arm], 'strategy not active')
            require(initial['environment_hand_accounting']['completed_hands'] == physical, 'physical reset')
            ctl.route_audit(initial, True, parent)
            ctl.evidence.initial_reference('static', parent, initial, ctl.HELPER.equal)
            namespace = initial['fixed_deal_attempt']['receipt']['namespace']
            require(namespace != parent['fixed_deal_attempt']['receipt']['namespace'], 'parent namespace reused')
            require(namespace not in self.namespaces, 'smoke namespace reused')
            write_new(run/'initial_resume_gate.json', {'passed':True, 'exact_keys':keys,
                'intentional_change':'pool_strategy only; new managed attempt namespace',
                'namespace':namespace, 'parent_sha256':digest, 'initial_sha256':sha(target)})

        self.phase = f'TRAINING_{run.name}'
        wall = self.execute(argv, run, capture, training=True)
        gate = read(run/'initial_resume_gate.json')
        final = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        new_physical = final['environment_hand_accounting']['completed_hands']-physical
        ctl.execution.target_or_safe_boundary(physical+new_physical, INITIAL[seed]+DOSES[stage])
        optimizer = ctl.prior.optimizer_step_audit(parent, final, True)
        require(not optimizer['new_state_ids'], 'optimizer state reset')
        require(final['ppo_replay_cumulative_rows'] > parent['ppo_replay_cumulative_rows'], 'replay did not advance')
        candidates = [r for r in final['pool_candidate_history'] if int(r['iteration']) > int(parent['iteration'])]
        require(len(candidates) >= 2, 'missing learned candidates')
        if arm == 'recent':
            require(all(r['selected'] for r in candidates), 'recent candidates not admitted')
        if arm == 'recent':
            require({0,1,2}.issubset({s['id'] for s in final['pool_snapshots']}), 'anchor lost')
        assignments = ctl.execution.complete_jsonl(run/'opponent_assignments.jsonl')
        current = [r for r in assignments if r['applies_to_iteration'] > parent['iteration']]
        require([r['applies_to_iteration'] for r in current] == list(range(parent['iteration']+1,final['iteration']+1)), 'assignment coverage')
        parent_ids = {s['id'] for s in parent['pool_snapshots']}
        sampled_new = {w['opponent']['snapshot_id'] for r in current for w in r['workers']
            if w['opponent']['kind'] == 'pool_snapshot' and w['opponent']['snapshot_id'] not in parent_ids}
        if arm == 'recent':
            require(len(sampled_new) >= 2, 'new opponents not assigned')
        receipt = final['fixed_deal_attempt']
        require(ctl.HELPER.helpers.load_attempt(Path(receipt['path']),receipt['sha256']) == receipt['receipt'], 'receipt changed')
        require(receipt['receipt']['parent_checkpoint_sha256'] == digest and receipt['receipt']['namespace'] == gate['namespace'], 'attempt binding')
        for name, prefix in prefixes.items():
            with (run/name).open('rb') as handle:
                require(hashlib.sha256(handle.read(prefix['bytes'])).hexdigest() == prefix['sha256'], 'prefix changed')
        result = {'passed':True, 'seed':seed, 'arm':arm, 'stage':stage, 'new_physical_hands':new_physical,
            'new_transition_hands':final['total_hands']-parent['total_hands'],
            'new_replay_rows':final['ppo_replay_cumulative_rows']-parent['ppo_replay_cumulative_rows'],
            'namespace':gate['namespace'], 'wall_seconds':wall, 'optimizer':optimizer,
            'new_candidates':candidates, 'checkpoint_sha256':sha(run/'latest.pt'),
            'sampled_new_snapshot_ids':sorted(sampled_new),
            'scope':'Physical bounded training; matched internal strength evaluated separately'}
        write_new(run/'verification.json', result)
        self.results.append(result)
        self.namespaces.add(gate['namespace'])
        self.inputs[str(run/'latest.pt')] = result['checkpoint_sha256']
        logger('--artifact', str(run/'verification.json'), '--artifact', str(run/'initial_resume_gate.json'))
        self.tick(force=True)

    def evaluate(self,stage):
        results, fresh_rows = {},[]
        for seed in (1,3):
            arms = {}
            for arm in STRATEGIES:
                out = BASE/f'eval_seed{seed}_{arm}_stage{stage}'
                job = BASE/f'job_{out.name}'
                job.mkdir()
                endpoint = directory(seed,arm,stage)/'latest.pt'
                original = parent_path(seed,arm,1)
                argv = [sys.executable,'-u',str(ROOT/'scripts/alpha_holdem/v6_public_opponent_matched_eval.py'),
                    '--control',str(original),'--treatment',str(endpoint)]
                for name,path in ctl.execution.ANCHORS.items():
                    argv += ['--anchor',f'{name}={path}']
                argv += ['--pairs-per-anchor','2048','--seed',str(EVAL_SEEDS[seed,stage]),
                    '--device','cuda','--out-dir',str(out)]
                self.phase = 'EVALUATING_'+out.name
                self.execute(argv,job)
                report = read(out/'summary.json')
                rows = ctl.evidence.read_rows(out/'common_deck_pairs.jsonl.gz')
                require(report['status'] == 'COMPLETED' and report['evaluation_hands'] == 32768
                    and report['policy_mode'] == 'greedy' and report['starting_stack_bb'] == 200
                    and report['observation_style'] == 'legacy_v4','eval execution contract')
                require(len(rows) == len(ctl.evidence.validated_map(rows)) == 8192,'pair count')
                require(report['raw_pairs_sha256'] == sha(out/'common_deck_pairs.jsonl.gz'),'raw hash')
                require(report['input_sha256'] == {'control':EXPECTED[seed],'treatment':sha(endpoint),
                    **{f'anchor:{k}':v for k,v in ctl.execution.ANCHOR_SHA256.items()}},'eval checkpoint hashes')
                for index,name in enumerate(ctl.execution.ANCHORS):
                    selected = [r for r in rows if r['anchor'] == name]
                    require(len(selected) == 2048 and sorted(r['pair_index'] for r in selected) == list(range(2048)),'anchor coverage')
                    require(all(r['anchor_seed'] == EVAL_SEEDS[seed,stage]+1000003*index for r in selected),'eval seed')
                arms[arm] = rows
                logger('--artifact',str(out/'summary.json'),'--artifact',str(out/'common_deck_pairs.jsonl.gz'))
            contrast = ctl.evidence.summarize_rows(ctl.evidence.join_arms(arms['control'],arms['recent']))
            endpoints = {arm:ctl.evidence.summarize_rows(rows) for arm,rows in arms.items()}
            results[str(seed)] = {'recent_minus_control':contrast,'endpoint_minus_parent':endpoints,
                'absolute_vs_anchors':{arm:ctl.evidence.summarize_rows([
                    ctl.evidence.derived_row(r,[0.,0.],r['treatment_rewards_bb']) for r in rows]) for arm,rows in arms.items()},
                'broad_collapse':ctl.evidence.broad_collapse(contrast) or any(ctl.evidence.broad_collapse(v) for v in endpoints.values())}
            fresh_rows += arms['control']
        require(len({tuple(r['deck']) for r in fresh_rows}) == 16384,'cross-seed evaluation overlap')
        freshness = ctl.evidence.check_prior_decks(fresh_rows,self.corpus)
        analysis = {'passed':True,'stage':stage,'seeds':results,'freshness':freshness,
            'evaluation_hands':131072,'broad_collapse':any(r['broad_collapse'] for r in results.values()),
            'ci_scope':'conditional paired decks, not training-seed population or Slumbot strength'}
        write_new(BASE/f'stage{stage}_analysis.json',analysis)
        for path in BASE.glob(f'eval_*_stage{stage}/common_deck_pairs.jsonl.gz'):
            self.corpus[str(path)] = sha(path)
        logger('--artifact',str(BASE/f'stage{stage}_analysis.json'))
        return analysis

    def run(self):
        for stage in DOSES:
            order = ORDER if stage == 1 else list(reversed(ORDER))
            for seed,arm in order:
                self.train(seed,arm,stage)
            if self.evaluate(stage)['broad_collapse']:
                self.phase = f'STAGE{stage}_BROAD_COLLAPSE_REVIEW'
                break
        else:
            self.phase = 'FIXED_1M_COMPLETE_NEEDS_EXTERNAL_CALIBRATION'
        write_new(BASE/'controller_result.json',{'phase':self.phase,'training':self.results,
            'wall_seconds':time.perf_counter()-self.started,'goal_achieved':False})
        logger('--artifact',str(BASE/'controller_result.json'))
        self.tick(force=True)

def main():
    for key in ('PYTHONDONTWRITEBYTECODE','OMP_NUM_THREADS','MKL_NUM_THREADS','OPENBLAS_NUM_THREADS'):
        os.environ[key] = '1'
    controller = Controller()
    try:
        controller.run()
    except Exception as exc:
        controller.phase = 'PRESERVED_BOUNDARY_NEEDS_REVIEW'
        write_new(BASE/'controller_error.json',{'error':repr(exc),'automatic_retry':False})
        controller.tick(force=True)
        raise

if __name__ == '__main__':
    main()
