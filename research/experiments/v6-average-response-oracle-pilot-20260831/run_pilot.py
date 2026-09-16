"""New PPO response to an immutable learned average; no external requests."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

import oracle_stats as stats

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SPEED = ROOT/'research/experiments/v6-gpu-multienv-throughput-20260831'
PARENT = ROOT/'research/experiments/v6-historical-average-fresh20k-slumbot-20260831'
ASSESS = ROOT/'research/experiments/v6-historical-average-assessment-20260831'
TARGET, PAIRS, SEED, EVAL_SEED = 1048576, 4096, 20261013, 20261014
LABELS = ('initial', 'quarter', 'half', 'final')
OPPONENTS = ('average', 'anchor0', 'anchor1', 'anchor2', 'anchor3', 'anchor4')
EVAL_HANDS = len(LABELS)*len(OPPONENTS)*PAIRS*2
MODEL_SHA = 'cd7ce2b27cf3a86e96141432c92c6f92a3eb923dce519d1f1128af5acbb2364b'
PARENT_SHA = '7fd709482b068cc411d5b1adbbd262c836902bd5933506516daf363b7ab56d6d'
EXEC_SHA = '2f1da801ec637ef4c5ce4fcf03b8a1170d40020502b4f774f1bb6835e13389e7'
SPEED_SHA = '20c2669a14cb51f9231b9c416e2de19ae5049c23d5837c06efb639998f494fde'
ANCHOR_SHAS = (
    '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2',
    'd942236f1272664576daed3eb624cc2ee3647ad952a47eeb0f4a5185b5679e90',
    'c2c8171a3c06e6b2fca2012b4e693246881586c1e2a1831c0d66935713bca577',
    'fe127b5d025316dc7f604522cb9ea38ef6b1910013cebb254157f384f6ed0e23',
    '7dfb45baee263353e7fd375062b068747c2795b7042480e410693fa4d28541b9')
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
sys.path.insert(0, str(ROOT/'scripts/alpha_holdem'))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def parent_check():
    assert sha(PARENT/'reviewed_analysis.json') == PARENT_SHA
    assert read(PARENT/'experiment.json')['status'] == 'COMPLETED'
    prior = read(PARENT/'reviewed_analysis.json')
    assert prior['status'] == 'PASS' and prior['decision'] == 'PILOT_POINT_NOT_POSITIVE'
    assert prior['model_sha256'] == MODEL_SHA and prior['slumbot_hands'] == 20000
    assert sha(PARENT/'frozen/final.pt') == MODEL_SHA
    assert sha(SPEED/'execution.json') == EXEC_SHA and sha(SPEED/'reviewed_analysis.json') == SPEED_SHA
    q = read(SPEED/'reviewed_analysis.json')
    assert q['status'] == 'PASS' and q['selected_fresh_start_configuration'] == 'multi8'
    for row in read(SPEED/'execution_code/copy_manifest.json'):
        if row['original'].startswith('scripts/'):
            assert sha(ROOT/row['original']) == row['sha256'] == sha(ROOT/row['copy'])


def verify(copies, inputs):
    parent_check()
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ('original', 'copy'))
    for row in inputs:
        assert sha(row['path']) == row['sha256'] == sha(row['source'])


def replace_flag(cmd, flag, value):
    cmd[cmd.index(flag)+1] = str(value)


def training_command():
    parent_check()
    child = next(r for r in read(SPEED/'execution.json')['children'] if r['arm'] == 'multi8')
    cmd = [v.replace(str(SPEED), str(BASE)) for v in child['command'][1:]]
    assert cmd[:2] == ['-u', 'scripts/alpha_holdem/train_v5.py']
    cmd[1] = str(BASE/'execution_code/source_files/scripts/alpha_holdem/train_v5.py')
    # Distilled v6 weights are a new initialization, never legacy rebinding or SL resume.
    cmd.remove('--v6-rebind-legacy-weights')
    idx = cmd.index('--source-policy-reference-checkpoint')
    del cmd[idx:idx+2]
    idx = cmd.index('--fixed-opponent-checkpoints')+1
    end = next(i for i in range(idx, len(cmd)) if cmd[i].startswith('--'))
    cmd[idx:end] = [str(BASE/'frozen/average.pt')]
    directory = BASE/'production'
    for flag, value in {
        '--total-environment-hands':TARGET, '--self-play-fraction':0,
        '--source-policy-kl-coef':0, '--resume':BASE/'frozen/average.pt',
        '--seed':SEED, '--worker-seed-base':2026101300,
        '--run-id':'v6_average_response_20260831', '--run-dir':directory,
        '--out':directory/'latest.pt', '--max-runtime-seconds':7200,
        '--opponent-assignment-provenance-file':directory/'opponent_assignments.jsonl'
    }.items(): replace_flag(cmd, flag, value)
    return cmd


def initialization_check(path=None):
    import torch
    from alpha_holdem.execution_v6 import load_policy
    from alpha_holdem.train_v5 import initial_environment_hand_accounting
    model, checkpoint, digest = load_policy(path or BASE/'frozen/average.pt', 'cpu')
    assert digest == MODEL_SHA and checkpoint['training_algorithm'] == 'historical_behavior_distillation_v1'
    assert checkpoint['resume_contract'].startswith('Not a train_v5 PPO continuation')
    assert len(checkpoint['optimizer']['state']) == 80 and checkpoint['epoch'] == 12
    assert len(model.state_dict()) == 86 and all(torch.equal(v, checkpoint['model'][k]) for k, v in model.state_dict().items())
    # Deployment loader freezes parameters; explicitly construct a trainable
    # weights-only view for the new-PPO initialization diagnostic, with no steps.
    model.train()
    for parameter in model.parameters(): parameter.requires_grad_(True)
    assert all(p.requires_grad for p in model.parameters())
    optimizer = torch.optim.Adam(model.parameters(), lr=3e-5)
    assert len(optimizer.state) == 0 and len(optimizer.param_groups[0]['params']) == 86
    counter = initial_environment_hand_accounting(checkpoint, reset_hand_counter=True, run_id='v6_average_response_20260831')
    assert counter['completed_hands'] == 0 and counter['prefix_complete'] and counter['unknown_prefix_training_marker_hands'] == 0
    return dict(status='PASS', operation='NEW_PPO_WEIGHTS_INITIALIZATION_NOT_SL_RESUME', source_sha256=digest,
        identical_initial_tensors=86, source_optimizer_states_preserved=80, new_optimizer_states=0,
        new_trainable_parameters=86, old_hands_not_recounted=262144, initial_actual_hands=0)


def training_health():
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    directory = BASE/'production'
    checkpoint = torch.load(directory/'latest.pt', map_location='cpu', weights_only=False)
    source = torch.load(BASE/'frozen/average.pt', map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    account = checkpoint['environment_hand_accounting']
    assert account['completed_hands'] >= TARGET and account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
    assert account['origin_run_id'] == 'v6_average_response_20260831'
    assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
    config = checkpoint['config']
    for key, expected in dict(self_play_fraction=0, source_policy_kl_coef=0, rollout_mode='multi',
        rollout_envs_per_worker=8, workers=12, seed=SEED, worker_seed_base=2026101300, validate_stream=True,
        reset_optimizer=True, reset_hand_counter=True, v6_rebind_legacy_weights=False).items():
        assert config[key] == expected
    assert config['resume'] == str(BASE/'frozen/average.pt')
    assert config['fixed_opponent_checkpoints'] == [str(BASE/'frozen/average.pt')]
    assert not config['source_policy_reference_checkpoint']
    metrics = [json.loads(line) for line in (directory/'h1_training_metrics.jsonl').read_text().splitlines()]
    counts = [m['environment_hand_accounting']['completed_hands'] for m in metrics]
    assert [m['iteration'] for m in metrics] == list(range(1, checkpoint['iteration']+1))
    assert all(a < b for a, b in zip([0]+counts[:-1], counts))
    assert all(v < TARGET for v in counts[:-1]) and counts[-1] >= TARGET
    assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    assert sum(not torch.equal(v, source['model'][k]) for k, v in checkpoint['model'].items()) == 86
    assert len(checkpoint['optimizer']['state']) == 86 and not checkpoint.get('ppo_replay_entries')
    for state in checkpoint['optimizer']['state'].values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    assignments = [json.loads(line) for line in (directory/'opponent_assignments.jsonl').read_text().splitlines()]
    exposure = stats.exposure(assignments, checkpoint['iteration'])
    cmd = [str(BASE/'execution_code/source_files/scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py'),
        '--run-dir', str(directory), '--expected-target-hands', '99999999', '--expected-target-environment-hands', str(TARGET),
        '--expected-final-iteration', str(checkpoint['iteration']), '--expected-pool-size', '1',
        '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(directory/'session_audit.json')]
    record(cmd)
    with (directory/'audit_stdout.log').open('x') as output:
        subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(directory/'session_audit.json')['status'] == 'PASS'
    result = dict(status='PASS', actual_hands=account['completed_hands'], iteration=checkpoint['iteration'],
        overshoot=account['completed_hands']-TARGET, shutdown_counter_tail=account['completed_hands']-counts[-1],
        legacy_markers=checkpoint['total_hands'], finite_changed_tensors=86, checkpoint_sha256=sha(directory/'latest.pt'),
        fresh_policy_rows=sum(m['fresh_policy_rows'] for m in metrics),
        terminal_trajectories=sum(m['terminal_trajectories'] for m in metrics), exposure=exposure,
        adam_step_range=[min(float(s['step']) for s in checkpoint['optimizer']['state'].values()),
                         max(float(s['step']) for s in checkpoint['optimizer']['state'].values())])
    write(directory/'training_health.json', result)
    log(*[v for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl',
        'latest_train.log', 'session_audit.json', 'audit_stdout.log', 'training_health.json'] for v in ['--artifact', directory/name]])
    return checkpoint, result


def freeze_curve(checkpoint):
    import torch
    archives = []
    metrics = [json.loads(line) for line in (BASE/'production/h1_training_metrics.jsonl').read_text().splitlines()]
    by_iteration = {m['iteration']:m['environment_hand_accounting']['completed_hands'] for m in metrics}
    for path in sorted((BASE/'production/checkpoints').glob('checkpoint_iter*_hands*.pt')):
        archive = torch.load(path, map_location='cpu', weights_only=False)
        account = archive['environment_hand_accounting']
        assert account['prefix_complete'] and account['origin_run_id'] == 'v6_average_response_20260831'
        assert by_iteration[archive['iteration']] <= account['completed_hands'] < by_iteration.get(archive['iteration']+1, account['completed_hands']+1)
        archives.append(dict(path=str(path), sha256=sha(path), iteration=archive['iteration'], actual_hands=account['completed_hands']))
    selected = {label: stats.select_first_actual(archives, threshold) for label, threshold in [('quarter', TARGET//4), ('half', TARGET//2)]}
    selected['final'] = dict(path=str(BASE/'production/latest.pt'), sha256=sha(BASE/'production/latest.pt'),
        iteration=checkpoint['iteration'], actual_hands=checkpoint['environment_hand_accounting']['completed_hands'])
    candidates = {'initial':dict(path=str(BASE/'frozen/average.pt'), sha256=MODEL_SHA, actual_hands=0, iteration=0)}
    for label, row in selected.items():
        path = BASE/'frozen'/f'{label}.pt'
        shutil.copy2(row['path'], path)
        assert sha(path) == row['sha256']
        candidates[label] = {**row, 'source':row['path'], 'path':str(path)}
        log('--artifact', path, '--artifact', row['path'])
    write(BASE/'archive_selection.json', dict(archives=archives, selected=selected))
    write(BASE/'candidate_manifest.json', candidates)
    log('--artifact', BASE/'archive_selection.json', '--artifact', BASE/'candidate_manifest.json')
    return candidates


def eval_command(label, opponent):
    assert label in LABELS and opponent in OPPONENTS
    candidate = 'average' if label == 'initial' else label
    return [str(BASE/'execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py'),
        '--candidate', str(BASE/'frozen'/f'{candidate}.pt'), '--anchor', str(BASE/'frozen'/f'{opponent}.pt'),
        '--pairs', str(PAIRS), '--seed', str(EVAL_SEED), '--device', 'cpu',
        '--out-dir', str(BASE/'evaluation'/f'{label}_{opponent}')]


def analyze(candidates, inputs):
    values, absolute, decks = {}, {}, None
    opponents = {r['label']:r for r in inputs}
    for label in LABELS:
        for opponent in OPPONENTS:
            directory = BASE/'evaluation'/f'{label}_{opponent}'
            summary = read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['pairs'] == PAIRS and summary['evaluation_hands'] == 2*PAIRS and summary['seed'] == EVAL_SEED
            assert summary['candidate_sha256'] == candidates[label]['sha256'] and summary['anchor_sha256'] == opponents[opponent]['sha256']
            assert summary['pairs_sha256'] == sha(directory/'pairs.jsonl')
            rows = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert len(rows) == PAIRS and [r['pair_index'] for r in rows] == list(range(PAIRS))
            current = [r['deck'] for r in rows]
            if decks is None: decks = current
            assert decks == current
            cell = [sum(r['rewards_bb'])*50 for r in rows]
            values[label, opponent] = cell
            absolute[f'{label}_{opponent}'] = {k:v for k,v in stats.estimate(cell).items() if k != 'family18_ci95'}
            log('--artifact', directory/'pairs.jsonl', '--artifact', directory/'summary.json')
    assert all(v == 0 for v in values['initial', 'average'])
    effects = {f'{label}_{opponent}':stats.estimate([v-s for v, s in zip(values[label, opponent], values['initial', opponent])])
               for label in LABELS[1:] for opponent in OPPONENTS}
    return dict(absolute=absolute, paired_response_minus_initial=effects,
                primary=effects['final_average'], decision=stats.decision(effects['final_average']))


def main():
    import psutil
    import torch
    torch.set_num_threads(1)
    if sys.argv[1:] or any((BASE/n).exists() for n in ('execution.json', 'execution_code', 'production', 'frozen')):
        raise ValueError('Preserve existing work; no automatic restart or overwrite')
    names = {'train_v5.py','run_pilot.py','run_assessment.py','run_distillation.py','v6_mirror_eval.py','play_slumbot.py','play_slumbot_v6.py','play_slumbot_v6_journaled.py'}
    for process in psutil.process_iter(['name', 'cmdline']):
        if process.pid != psutil.Process().pid and (process.info['name'] or '').lower().startswith('python') and any(Path(a).name in names for a in process.info['cmdline'] or []):
            raise RuntimeError('Another poker workload is active')
    assert torch.cuda.is_available() and psutil.virtual_memory().available >= 16*2**30
    parent_check()
    start = time.monotonic()
    execution = dict(status='PREPARING', pid=psutil.Process().pid, create_time=psutil.Process().create_time(),
        started_at=datetime.now(timezone.utc).isoformat(), children=[])
    write(BASE/'execution.json', execution)
    processes = []
    actual, evaluated = 0, 0
    try:
        directory = BASE/'execution_code'
        directory.mkdir()
        paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
        paths += [f'scripts/deep_cfr/{n}.py' for n in ('__init__', 'game_state', 'hand_eval')]+['research/experiment_log.py']
        paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
        capture_code_provenance(ROOT, directory, paths)
        copies = []
        for relative in paths:
            target = directory/'source_files'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
            copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
        write(directory/'copy_manifest.json', copies)
        log(*[v for name in ('source_manifest.json', 'code.patch', 'copy_manifest.json') for v in ['--artifact', directory/name]])
        (BASE/'frozen').mkdir()
        inputs = []
        for label, source, expected in [('average', PARENT/'frozen/final.pt', MODEL_SHA)]+[
                (f'anchor{i}', ASSESS/'frozen'/f'anchor{i}.pt', digest) for i, digest in enumerate(ANCHOR_SHAS)]:
            assert sha(source) == expected
            path = BASE/'frozen'/f'{label}.pt'
            shutil.copy2(source, path)
            inputs.append(dict(label=label, path=str(path), source=str(source), sha256=sha(path)))
        write(BASE/'input_manifest.json', inputs)
        write(BASE/'initialization_audit.json', initialization_check())
        log('--artifact', BASE/'input_manifest.json', '--artifact', BASE/'initialization_audit.json',
            *[v for r in inputs for v in ['--artifact', r['path']]])
        cmd = ['-m', 'pytest', str(BASE/'test_pilot.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        verify(copies, inputs)
        cmd = training_command()
        record(cmd)
        execution['status'] = 'TRAINING'
        with (BASE/'training_stdout.log').open('x') as output:
            child = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            info = dict(role='trainer', pid=child.pid, create_time=psutil.Process(child.pid).create_time(),
                command=[sys.executable, *cmd], exit_code=None)
            processes.append((child, info))
            execution['children'].append(info)
            write(BASE/'execution.json', execution)
            previous = -1
            while child.poll() is None:
                try: manifest = read(BASE/'production/run_manifest.json')
                except (OSError, json.JSONDecodeError): manifest = {}
                actual = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands', 0))
                if actual != previous:
                    log('--count', f'new_training_hands={actual}', '--metric', f'active_iteration={manifest.get("iteration",0)}')
                    previous = actual
                time.sleep(5)
            info['exit_code'] = child.wait()
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'training_stdout.log')
        if info['exit_code'] != 0: raise RuntimeError('Trainer failed; preserve the original attempt')
        checkpoint, health = training_health()
        actual = health['actual_hands']
        verify(copies, inputs)
        candidates = freeze_curve(checkpoint)
        log('--count', f'new_training_hands={actual}', '--note', 'Training/session audit complete. All4actual-counter-selected checkpoints frozen before24fixed internal cells. No external allocation.')
        print(json.dumps(dict(phase='TRAINING_COMPLETED', **health)), flush=True)
        execution['status'] = 'INTERNAL_EVALUATION'
        jobs = []
        for label in LABELS:
            for opponent in OPPONENTS:
                cmd = eval_command(label, opponent)
                record(cmd)
                info = dict(role=f'{label}_{opponent}', label=label, opponent=opponent,
                    command=[sys.executable, *cmd], exit_code=None)
                execution['children'].append(info)
                jobs.append(info)
        write(BASE/'evaluation_commands.json', jobs)
        log('--artifact', BASE/'evaluation_commands.json')
        write(BASE/'execution.json', execution)
        def evaluate(info):
            with (BASE/f'{info["role"]}_stdout.log').open('x') as output:
                child = subprocess.Popen(info['command'], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                p = psutil.Process(child.pid)
                p.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
                info.update(pid=child.pid, create_time=p.create_time())
                processes.append((child, info))
                info['exit_code'] = child.wait()
            return info
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, info) for info in jobs]
            previous = -1
            while not all(f.done() for f in futures):
                evaluated = sum(stats.raw_count(BASE/'evaluation'/info['role']/'pairs.jsonl')*2 for info in jobs)
                if evaluated != previous:
                    log('--count', f'evaluation_hands={evaluated}')
                    previous = evaluated
                write(BASE/'execution.json', execution)
                time.sleep(10)
            assert all(f.result()['exit_code'] == 0 for f in futures)
        evaluated = sum(stats.raw_count(BASE/'evaluation'/info['role']/'pairs.jsonl')*2 for info in jobs)
        assert evaluated == EVAL_HANDS
        verify(copies, inputs)
        assert all(sha(row['path']) == row['sha256'] for row in candidates.values())
        result = analyze(candidates, inputs)
        write(BASE/'completed_analysis.json', dict(status='COMPLETED_PENDING_REVIEW', new_training_hands=actual,
            evaluation_hands=evaluated, slumbot_hands=0, qualification_hands=0, goal_achieved=False, **result))
        log('--artifact', BASE/'completed_analysis.json', *[v for info in jobs for v in ['--artifact', BASE/f'{info["role"]}_stdout.log']])
        execution['status'] = 'COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status'] = 'NEEDS_REVIEW'
        execution['error'] = traceback.format_exc()
        (BASE/'failure.txt').write_text(execution['error'])
        log('--artifact', BASE/'failure.txt', '--note', 'Original attempt preserved; no automatic replay, restart or counter reset. Incomplete evidence is not a strength result.')
        raise
    finally:
        for process, info in processes:
            if process.poll() is None: info['exit_code'] = process.wait()
        try: actual = read(BASE/'production/run_manifest.json')['environment_hand_accounting']['completed_hands']
        except (OSError, KeyError, json.JSONDecodeError): pass
        evaluated = sum(stats.raw_count(p)*2 for p in (BASE/'evaluation').glob('*/pairs.jsonl'))
        execution.update(finished_at=datetime.now(timezone.utc).isoformat(), wall_time_seconds=time.monotonic()-start,
            new_training_hands=actual, evaluation_hands=evaluated)
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'execution.json', '--count', f'new_training_hands={actual}', '--count', f'evaluation_hands={evaluated}', '--count', 'slumbot_hands=0')
        print(json.dumps(dict(status=execution['status'], new_training_hands=actual, evaluation_hands=evaluated)), flush=True)


if __name__ == '__main__': main()
