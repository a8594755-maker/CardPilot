"""Matched three versus five fixed learned opponents; one new eligible treatment."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
CURVE = ROOT/'research/experiments/v6-full-network-learning-curve-20260831'
RETENTION = ROOT/'research/experiments/v6-source-kl-retention-pilot-20260831'
SPEED = ROOT/'research/experiments/v6-gpu-multienv-throughput-20260831'
TARGET, PAIRS, EVAL_SEED, EVAL_HANDS = 262144, 8192, 20260927, 245760
SOURCE_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
EXEC_SHA = '2f1da801ec637ef4c5ce4fcf03b8a1170d40020502b4f774f1bb6835e13389e7'
SPEED_SHA = '20c2669a14cb51f9231b9c416e2de19ae5049c23d5837c06efb639998f494fde'
LEAGUE = [('league_kl001', CURVE/'frozen/final.pt', '0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606'),
          ('league_kl010', RETENTION/'frozen/treatment.pt', '9b7b0e3a0c2be3bdfbbab4167e1eb4a5e7f284d619a8afa13d608c9943b46efb')]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stats = load_module('retention_statistics', RETENTION/'run_pilot.py')


def sha(path): return sha256_file(Path(path))


def read(path): return json.loads(Path(path).read_text())


def write(path, value): Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def training_command(label):
    assert label in ['control3', 'diverse5']
    assert sha(SPEED/'execution.json') == EXEC_SHA and sha(SPEED/'reviewed_analysis.json') == SPEED_SHA
    qualification = read(SPEED/'reviewed_analysis.json')
    assert qualification['status'] == 'PASS' and qualification['selected_fresh_start_configuration'] == 'multi8'
    child = next(r for r in read(SPEED/'execution.json')['children'] if r['arm'] == 'multi8')
    cmd = [value.replace(str(SPEED), str(BASE)) for value in child['command'][1:]]
    run = BASE/'production'/label
    for flag, value in {'--total-environment-hands':TARGET, '--run-id':f'v6_diverse_{label}_20260831',
                        '--run-dir':run, '--out':run/'latest.pt',
                        '--opponent-assignment-provenance-file':run/'opponent_assignments.jsonl',
                        '--seed':20260926, '--worker-seed-base':2026092600, '--max-runtime-seconds':3600}.items():
        cmd[cmd.index(flag)+1] = str(value)
    if label == 'diverse5':
        start = cmd.index('--fixed-opponent-checkpoints')+1
        end = next(i for i in range(start, len(cmd)) if cmd[i].startswith('--'))
        cmd[end:end] = [str(BASE/'frozen'/f'{name}.pt') for name, _, _ in LEAGUE]
    assert cmd[cmd.index('--resume')+1] == str(ROOT/'models/baseline/standard10/latest.pt')
    assert cmd[cmd.index('--source-policy-kl-coef')+1] == '.01'
    return cmd


def verify(copies, inputs):
    assert sha(ROOT/'models/baseline/standard10/latest.pt') == SOURCE_SHA
    assert sha(SPEED/'execution.json') == EXEC_SHA and sha(SPEED/'reviewed_analysis.json') == SPEED_SHA
    for row in copies: assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original', 'copy'])
    for row in inputs: assert sha(row['path']) == row['sha256'] == sha(row['source'])


def training_health(label):
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    run = BASE/'production'/label
    checkpoint = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint['environment_hand_accounting']
    assert account['completed_hands'] >= TARGET and account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == f'v6_diverse_{label}_20260831'
    assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
    config = checkpoint['config']
    for k, v in dict(source_policy_kl_coef=.01, rollout_mode='multi', rollout_envs_per_worker=8,
                     seed=20260926, worker_seed_base=2026092600, validate_stream=True).items(): assert config[k] == v
    metrics = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
    counts = [r['environment_hand_accounting']['completed_hands'] for r in metrics]
    assert [r['iteration'] for r in metrics] == list(range(1, checkpoint['iteration']+1))
    assert all(a < b for a,b in zip([0]+counts[:-1], counts))
    assert all(h < TARGET for h in counts[:-1]) and counts[-1] >= TARGET
    source = torch.load(ROOT/'models/baseline/standard10/latest.pt', map_location='cpu', weights_only=False)
    assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    assert sum(not torch.equal(v, source['model'][k]) for k,v in checkpoint['model'].items()) == 86
    assert len(checkpoint['optimizer']['state']) == 86 and not checkpoint.get('ppo_replay_entries')
    for state in checkpoint['optimizer']['state'].values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    cmd = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
           '--expected-target-hands', '99999999', '--expected-target-environment-hands', str(TARGET),
           '--expected-final-iteration', str(checkpoint['iteration']), '--expected-pool-size', '3' if label == 'control3' else '5',
           '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(run/'session_audit.json')]
    record(cmd)
    with (run/'audit_stdout.log').open('x') as output:
        subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(run/'session_audit.json')['status'] == 'PASS'
    shutil.copy2(run/'latest.pt', BASE/'frozen'/f'{label}.pt')
    health = dict(status='PASS', new_training_hands=account['completed_hands'], iteration=checkpoint['iteration'],
                  overshoot=account['completed_hands']-TARGET, shutdown_counter_tail=account['completed_hands']-counts[-1],
                  legacy_markers=checkpoint['total_hands'], finite_changed_tensors=86,
                  checkpoint_sha256=sha(run/'latest.pt'), qualification_admitted=False)
    write(run/'training_health.json', health)
    log(*[v for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl',
                        'latest_train.log', 'session_audit.json', 'training_health.json', 'audit_stdout.log'] for v in ['--artifact', run/name]],
        '--artifact', BASE/'frozen'/f'{label}.pt')
    return health


def main():
    import psutil
    import torch
    torch.set_num_threads(1)
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json', 'execution_code', 'production', 'frozen']):
        raise ValueError('Preserve existing run; no automatic restart')
    for p in psutil.process_iter(['name','cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
                Path(a).name in ['train_v5.py','run_pilot.py','run_benchmark.py','v6_mirror_eval.py','play_slumbot_v6_journaled.py']
                for a in p.info['cmdline'] or []): raise RuntimeError('Another research process is active')
    assert torch.cuda.is_available() and psutil.virtual_memory().available >= 16*2**30
    execution = dict(status='RUNNING', pid=psutil.Process().pid, started_at=datetime.now(timezone.utc).isoformat(), children=[])
    write(BASE/'execution.json', execution)
    directory = BASE/'execution_code'
    directory.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__','game_state','hand_eval']]
    paths += ['research/experiment_log.py', (RETENTION/'run_pilot.py').relative_to(ROOT).as_posix(), (RETENTION/'review_finish.py').relative_to(ROOT).as_posix()]
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    write(directory/'copy_manifest.json', copies)
    log(*[v for name in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/name]])
    counts, evaluation_hands = {}, 0
    try:
        cmd = ['-m','pytest',str(BASE/'test_pilot.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable,*cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        (BASE/'frozen').mkdir()
        inputs, anchors = [], []
        for old in read(CURVE/'anchor_manifest.json'):
            source = Path(old['path'])
            assert sha(source) == old['sha256']
            target = BASE/'frozen'/source.name
            shutil.copy2(source,target)
            row = dict(index=old['index'], path=str(target), source=str(source), sha256=sha(target))
            anchors.append(row)
            inputs.append(row)
        for name, source, expected in LEAGUE:
            assert sha(source) == expected
            target = BASE/'frozen'/f'{name}.pt'
            shutil.copy2(source,target)
            inputs.append(dict(name=name,path=str(target),source=str(source),sha256=sha(target)))
        write(BASE/'anchor_manifest.json',anchors)
        write(BASE/'frozen_inputs.json',inputs)
        log('--artifact',BASE/'anchor_manifest.json','--artifact',BASE/'frozen_inputs.json', *[v for r in inputs for v in ['--artifact',r['path']]])
        for label in ['control3','diverse5']:
            verify(copies,inputs)
            cmd = training_command(label)
            record(cmd)
            with (BASE/f'{label}_stdout.log').open('x') as output:
                child = subprocess.Popen([sys.executable,*cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                info = dict(role=f'train_{label}',pid=child.pid,command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(info)
                write(BASE/'execution.json',execution)
                seen = -1
                while child.poll() is None:
                    try: manifest = read(BASE/'production'/label/'run_manifest.json')
                    except (OSError,json.JSONDecodeError): manifest = {}
                    current = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands',0))
                    if current != seen:
                        counts[label], seen = current,current
                        log('--count',f'new_training_hands={sum(counts.values())}','--metric',f'active_arm={label}',
                            '--metric',f'active_iteration={manifest.get("iteration",0)}')
                    time.sleep(5)
                info['exit_code'] = child.wait()
            write(BASE/'execution.json',execution)
            log('--artifact',BASE/f'{label}_stdout.log')
            if info['exit_code']: raise RuntimeError('Trainer failed; preserve evidence without retry')
            health = training_health(label)
            counts[label] = health['new_training_hands']
            verify(copies,inputs)
            log('--count',f'new_training_hands={sum(counts.values())}','--note',f'{label} training completed with passing health/session audit; final frozen.')
            print(json.dumps(dict(arm=label,**health)),flush=True)
        candidates = {label:dict(path=str(path),sha256=sha(path)) for label,path in [
            ('source',BASE/'frozen/anchor0.pt'),('control3',BASE/'frozen/control3.pt'),('diverse5',BASE/'frozen/diverse5.pt')]}
        write(BASE/'candidate_manifest.json',candidates)
        log('--artifact',BASE/'candidate_manifest.json','--note','Both new finals frozen before all15fixed fresh cells; only diverse5 is eligible for separate confirmation.')
        jobs = []
        for label,candidate in candidates.items():
            for anchor in anchors:
                out = BASE/'matrix'/f'{label}_anchor{anchor["index"]}'
                cmd = ['scripts/alpha_holdem/v6_mirror_eval.py','--candidate',candidate['path'],'--anchor',anchor['path'],
                       '--pairs',str(PAIRS),'--seed',str(EVAL_SEED),'--device','cpu','--out-dir',str(out)]
                record(cmd)
                jobs.append((label,anchor['index'],out,cmd))
        def evaluate(job):
            label,index,out,cmd = job
            with (BASE/f'{label}_anchor{index}_stdout.log').open('x') as output:
                process = subprocess.Popen([sys.executable,*cmd],cwd=ROOT,stdout=output,stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                psutil.Process(process.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
                info = dict(role=f'{label}_anchor{index}',pid=process.pid,command=[sys.executable,*cmd],exit_code=None)
                execution['children'].append(info)
                info['exit_code'] = process.wait()
            return info
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate,job) for job in jobs]
            previous = -1
            while not all(f.done() for f in futures):
                evaluation_hands = sum(stats.raw_count(out/'pairs.jsonl')*2 for _,_,out,_ in jobs)
                if evaluation_hands != previous:
                    log('--count',f'evaluation_hands={evaluation_hands}')
                    previous = evaluation_hands
                write(BASE/'execution.json',execution)
                time.sleep(10)
            outcomes = [f.result() for f in futures]
        assert all(r['exit_code'] == 0 for r in outcomes)
        evaluation_hands = sum(stats.raw_count(out/'pairs.jsonl')*2 for _,_,out,_ in jobs)
        assert evaluation_hands == EVAL_HANDS
        values, decks = {}, None
        for label,index,out,_ in jobs:
            summary = read(out/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 2*PAIRS and summary['seed'] == EVAL_SEED
            assert summary['candidate_sha256'] == candidates[label]['sha256'] and summary['anchor_sha256'] == anchors[index]['sha256']
            assert summary['pairs_sha256'] == sha(out/'pairs.jsonl')
            rows = [json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
            assert [r['pair_index'] for r in rows] == list(range(PAIRS))
            current = [r['deck'] for r in rows]
            if decks is None: decks = current
            assert decks == current
            values[label,index] = [sum(r['rewards_bb'])*50 for r in rows]
            log('--artifact',out/'summary.json','--artifact',out/'pairs.jsonl','--artifact',BASE/f'{label}_anchor{index}_stdout.log')
        assert all(v == 0 for v in values['source',0])
        contrasts = [dict(anchor=a,**stats.estimate([b-s for s,b in zip(values['source',a],values['diverse5',a])])) for a in range(5)]
        heldout = stats.estimate([(values['diverse5',3][i]-values['control3',3][i]+values['diverse5',4][i]-values['control3',4][i])/2 for i in range(PAIRS)])
        passed = stats.gate(contrasts,heldout)
        verify(copies,inputs)
        for r in candidates.values(): assert sha(r['path']) == r['sha256']
        report = dict(status='COMPLETED_PENDING_REVIEW',new_training_hands=sum(counts.values()),arm_counts=counts,
                      evaluation_hands=evaluation_hands,slumbot_hands=0,primary_contrasts=contrasts,heldout_league_contrast=heldout,
                      confirmation_gate_pass=passed,decision='ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'LEAGUE_DIVERSITY_GATE_NOT_PASSED')
        write(BASE/'completed_analysis.json',report)
        log('--count',f'new_training_hands={sum(counts.values())}','--count',f'evaluation_hands={evaluation_hands}',
            '--artifact',BASE/'completed_analysis.json','--note','Fixed two-arm training/matrix complete; independent review required before finish or confirmation.')
        execution['status'] = 'COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status'] = 'NEEDS_REVIEW'
        execution['error'] = traceback.format_exc()
        for label in ['control3','diverse5']:
            try: counts[label] = read(BASE/'production'/label/'run_manifest.json')['environment_hand_accounting']['completed_hands']
            except (OSError,KeyError,json.JSONDecodeError): pass
        evaluation_hands = sum(stats.raw_count(p) * 2 for p in (BASE/'matrix').glob('*/pairs.jsonl'))
        log('--count',f'new_training_hands={sum(counts.values())}','--count',f'evaluation_hands={evaluation_hands}',
            '--note','Execution error/interruption preserved; no automatic retries, counter resets, or cell replays.')
        raise
    finally:
        execution['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json',execution)
        log('--artifact',BASE/'execution.json')


if __name__ == '__main__': main()
