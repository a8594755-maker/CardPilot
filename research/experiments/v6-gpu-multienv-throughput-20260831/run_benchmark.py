"""Fixed fresh-start GPU throughput arms; no retries, resume, or strength gate."""
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-full-network-learning-curve-20260831'
TARGET = 32768
ARMS = [('single1', 'single', 1), ('multi4', 'multi', 4), ('multi8', 'multi', 8)]
SOURCE_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
EXEC_SHA = '47e842579af7d536b09571db45e8bd02620d52afe614d0bdbdca13ee2640b41c'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def training_command(label, mode, slots):
    assert (label, mode, slots) in ARMS
    assert sha(PARENT/'execution.json') == EXEC_SHA
    original = json.loads((PARENT/'execution.json').read_text())['children'][0]['command'][1:]
    cmd = [value.replace(str(PARENT), str(BASE)) for value in original]
    run = BASE/'arms'/label
    settings = {'--total-environment-hands':TARGET, '--run-id':f'v6_gpu_{label}_20260831',
                '--run-dir':run, '--out':run/'latest.pt',
                '--opponent-assignment-provenance-file':run/'opponent_assignments.jsonl',
                '--seed':20260925, '--worker-seed-base':2026092500,
                '--max-runtime-seconds':1200, '--rollout-mode':mode}
    for flag, value in settings.items(): cmd[cmd.index(flag)+1] = str(value)
    cmd += ['--rollout-envs-per-worker', str(slots), '--inference-min-batch-slots', '0',
            '--inference-batch-deadline-us', '700', '--validate-stream']
    assert cmd[cmd.index('--source-policy-kl-coef')+1] == '.01'
    assert cmd[cmd.index('--resume')+1] == str(ROOT/'models/baseline/standard10/latest.pt')
    return cmd


def summarize(log_text, metrics, final_count, elapsed, target=TARGET):
    """Fail closed on missing/reordered console/metric evidence; rounded timing."""
    pattern = re.compile(r'^\[\s*(\d+)\].*?hands=([\d,]+) envhands=([\d,]+).*?inf_bs=([\d.]+) collect=([\d.]+)s ppo=([\d.]+)s$')
    lines = [line for line in log_text.splitlines() if re.match(r'^\[\s*\d+\]', line)]
    if len(lines) != len(metrics) or len(lines) < 2: raise ValueError('Missing update evidence')
    if not math.isfinite(elapsed) or elapsed <= 0: raise ValueError('Invalid wall time')
    rows, previous = [], 0
    for index, (line, metric) in enumerate(zip(lines, metrics), 1):
        m = pattern.fullmatch(line)
        if not m or int(m[1]) != index or metric['iteration'] != index:
            raise ValueError('Noncontiguous update')
        account = metric['environment_hand_accounting']
        physical = account['completed_hands']
        if physical != int(m[3].replace(',', '')) or metric['hands'] != int(m[2].replace(',', '')):
            raise ValueError('Counter mismatch')
        if physical <= previous or previous >= target: raise ValueError('Wrong target boundary')
        if not account['prefix_complete'] or account['unknown_prefix_training_marker_hands'] != 0:
            raise ValueError('Unknown physical prefix')
        if sum(w['completed_hands'] for w in account['session_worker_counts']) != physical:
            raise ValueError('Worker sum mismatch')
        health = [metric[k] for k in ['approx_kl', 'reference_policy_kl', 'reference_policy_kl_coef']]
        if not all(math.isfinite(v) for v in health): raise ValueError('Nonfinite PPO health')
        if metric['ppo_replay_rows'] or metric['ppo_replay_buffer_iterations']:
            raise ValueError('Unexpected replay')
        rows.append(dict(iteration=index, physical_hands=physical, delta_physical=physical-previous,
                         legacy_markers=metric['hands'], inference_batch_mean=float(m[4]),
                         collection_seconds_rounded=float(m[5]), ppo_seconds_rounded=float(m[6]),
                         approx_kl=metric['approx_kl'], reference_kl=metric['reference_policy_kl'],
                         ppo_epochs=metric['ppo_epochs_completed']))
        previous = physical
    if previous < target or final_count < previous: raise ValueError('Incomplete final target')
    def window(selected):
        collection = sum(r['collection_seconds_rounded'] for r in selected)
        ppo = sum(r['ppo_seconds_rounded'] for r in selected)
        if collection <= 0 or ppo < 0: raise ValueError('Invalid update timing')
        return dict(physical_hands=sum(r['delta_physical'] for r in selected),
                    collection_seconds_rounded=collection, ppo_seconds_rounded=ppo,
                    physical_hands_per_logged_second=sum(r['delta_physical'] for r in selected)/(collection+ppo),
                    median_inference_batch_mean=statistics.median(r['inference_batch_mean'] for r in selected))
    return dict(new_training_hands=final_count, trainer_wall_seconds=elapsed,
                physical_hands_per_trainer_wall_second=final_count/elapsed,
                overshoot=final_count-target, shutdown_counter_tail=final_count-previous,
                all_updates=window(rows), excluding_update1=window(rows[1:]), rows=rows)


def select(results):
    if [r['arm'] for r in results] != [r[0] for r in ARMS] or any(r['health'] != 'PASS' for r in results):
        raise ValueError('Require all three valid fixed arms')
    control = results[0]
    eligible = []
    for row in results[1:]:
        primary = row['physical_hands_per_trainer_wall_second']/control['physical_hands_per_trainer_wall_second']
        warm = row['excluding_update1']['physical_hands_per_logged_second']/control['excluding_update1']['physical_hands_per_logged_second']
        if not all(math.isfinite(x) and x > 0 for x in [primary, warm]): raise ValueError('Invalid speed ratio')
        if primary >= 1.25 and warm >= 1.25: eligible.append(row)
    return max(eligible, key=lambda r:(r['physical_hands_per_trainer_wall_second'], -r['slots']))['arm'] if eligible else 'single1'


def verify(copies, anchors):
    assert sha(ROOT/'models/baseline/standard10/latest.pt') == SOURCE_SHA
    assert sha(PARENT/'execution.json') == EXEC_SHA
    for row in copies:
        assert all(sha(ROOT/row[key]) == row['sha256'] for key in ['original', 'copy'])
    for row in anchors: assert sha(row['path']) == row['sha256'] == sha(row['source'])


def inspect_arm(label, mode, slots, elapsed):
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    run = BASE/'arms'/label
    checkpoint = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    config = checkpoint['config']
    assert config['rollout_mode'] == mode and config['rollout_envs_per_worker'] == slots
    assert config['validate_stream'] and config['source_policy_kl_coef'] == .01
    assert config['seed'] == 20260925 and config['worker_seed_base'] == 2026092500
    assert config['fixed_training_deal_start_index'] == 0 and not checkpoint.get('ppo_replay_entries')
    account = checkpoint['environment_hand_accounting']
    assert account['origin_run_id'] == f'v6_gpu_{label}_20260831'
    metrics = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
    summary = summarize((run/'latest_train.log').read_text(), metrics, account['completed_hands'], elapsed)
    assert metrics[-1]['iteration'] == checkpoint['iteration']
    source = torch.load(ROOT/'models/baseline/standard10/latest.pt', map_location='cpu', weights_only=False)
    assert len(checkpoint['model']) == 86 and all(torch.isfinite(v).all() for v in checkpoint['model'].values())
    changed = sum(not torch.equal(v, source['model'][k]) for k, v in checkpoint['model'].items())
    assert changed == 86
    optimizer = checkpoint['optimizer']['state']
    assert len(optimizer) == 86
    for state in optimizer.values():
        assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
    assert len({float(state['step']) for state in optimizer.values()}) == 1
    cmd = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
           '--expected-target-hands', '99999999', '--expected-target-environment-hands', str(TARGET),
           '--expected-final-iteration', str(checkpoint['iteration']), '--expected-pool-size', '3',
           '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(run/'session_audit.json')]
    record(cmd)
    with (run/'audit_stdout.log').open('x') as output:
        subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    audit = json.loads((run/'session_audit.json').read_text())
    assert audit['status'] == 'PASS' and audit['actual_environment_hands'] == account['completed_hands']
    summary.update(arm=label, mode=mode, slots=slots, health='PASS', changed_tensors=changed,
                   optimizer_states=len(optimizer), optimizer_step=float(next(iter(optimizer.values()))['step']),
                   checkpoint_sha256=sha(run/'latest.pt'), no_decision_hands=account['no_trainable_decision_hands'],
                   unconsumed_decision_hands=account['completed_hands']-account['no_trainable_decision_hands']-checkpoint['total_hands'],
                   evaluation_hands=0, slumbot_hands=0, resume_qualified=False, strength_qualified=False)
    assert summary['unconsumed_decision_hands'] >= 0
    write(run/'analysis.json', summary)
    log(*[v for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl',
                        'latest_train.log', 'session_audit.json', 'analysis.json', 'audit_stdout.log'] for v in ['--artifact', run/name]])
    return summary


def main():
    import psutil
    import torch
    torch.set_num_threads(1)
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json', 'execution_code', 'frozen', 'arms']):
        raise ValueError('Preserve existing execution; no automatic restart')
    for process in psutil.process_iter(['name', 'cmdline']):
        if process.pid != psutil.Process().pid and (process.info['name'] or '').lower().startswith('python') and any(
                Path(a).name in ['train_v5.py', 'v6_mirror_eval.py', 'run_pilot.py', 'run_curve.py', 'run_benchmark.py',
                                 'play_slumbot_v6_journaled.py'] for a in process.info['cmdline'] or []):
            raise RuntimeError('Another research job is active')
    assert torch.cuda.is_available() and psutil.virtual_memory().available >= 16*2**30
    execution = dict(status='RUNNING', pid=psutil.Process().pid, started_at=datetime.now(timezone.utc).isoformat(), children=[])
    write(BASE/'execution.json', execution)
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py'] + [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
    directory = BASE/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    write(directory/'copy_manifest.json', copies)
    log(*[v for name in ['source_manifest.json', 'code.patch', 'copy_manifest.json'] for v in ['--artifact', directory/name]])
    results, counts = [], {}
    try:
        cmd = ['-m', 'pytest', str(BASE/'test_benchmark.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        (BASE/'frozen').mkdir()
        anchors = []
        for old in json.loads((PARENT/'anchor_manifest.json').read_text())[:3]:
            source = Path(old['path'])
            assert sha(source) == old['sha256']
            target = BASE/'frozen'/source.name
            shutil.copy2(source, target)
            anchors.append(dict(index=old['index'], source=str(source), path=str(target), sha256=sha(target)))
        write(BASE/'anchor_manifest.json', anchors)
        log('--artifact', BASE/'anchor_manifest.json', *[v for a in anchors for v in ['--artifact', a['path']]])
        for label, mode, slots in ARMS:
            verify(copies, anchors)
            cmd = training_command(label, mode, slots)
            record(cmd)
            started = time.perf_counter()
            with (BASE/f'{label}_stdout.log').open('x') as output:
                child = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                         creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                info = dict(arm=label, pid=child.pid, command=[sys.executable, *cmd], exit_code=None)
                execution['children'].append(info)
                write(BASE/'execution.json', execution)
                seen = -1
                while child.poll() is None:
                    try: manifest = json.loads((BASE/'arms'/label/'run_manifest.json').read_text())
                    except (OSError, json.JSONDecodeError): manifest = {}
                    current = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands', 0))
                    if current != seen:
                        counts[label], seen = current, current
                        log('--count', f'new_training_hands={sum(counts.values())}', '--metric', f'active_arm={label}',
                            '--metric', f'active_iteration={manifest.get("iteration", 0)}')
                    time.sleep(2)
                info['exit_code'] = child.wait()
            info['wall_seconds'] = time.perf_counter()-started
            write(BASE/'execution.json', execution)
            log('--artifact', BASE/f'{label}_stdout.log')
            if info['exit_code']: raise RuntimeError(f'{label} trainer failed; preserve evidence, no retry')
            result = inspect_arm(label, mode, slots, info['wall_seconds'])
            verify(copies, anchors)
            results.append(result)
            counts[label] = result['new_training_hands']
            log('--count', f'new_training_hands={sum(counts.values())}', '--artifact', BASE/'execution.json',
                '--note', f'{label} terminal health PASS; {counts[label]} actual physical hands; not strength evidence.')
            print(json.dumps({k:v for k,v in result.items() if k not in ['rows']}), flush=True)
        selected = select(results)
        report = dict(status='COMPLETED_PENDING_REVIEW', new_training_hands=sum(counts.values()), evaluation_hands=0,
                      slumbot_hands=0, selected_fresh_start_configuration=selected, strength_qualified=False,
                      resume_qualified=False, results=results)
        write(BASE/'completed_analysis.json', report)
        execution['status'] = report['status']
        log('--artifact', BASE/'completed_analysis.json', '--count', f'new_training_hands={sum(counts.values())}',
            '--note', f'All three fixed arms complete. Selected configuration={selected}; independent review required. No policy promotion.')
    except BaseException:
        execution['status'] = 'FAILED_PRESERVED'
        (BASE/'failure.txt').write_text(traceback.format_exc())
        for label, _, _ in ARMS:
            try:
                manifest = json.loads((BASE/'arms'/label/'run_manifest.json').read_text())
                counts[label] = manifest['environment_hand_accounting']['completed_hands']
            except (OSError, KeyError, json.JSONDecodeError): pass
        log('--count', f'new_training_hands={sum(counts.values())}', '--artifact', BASE/'failure.txt',
            '--note', 'Execution failed or interrupted; all existing evidence retained. No automatic retry or resume.')
        raise
    finally:
        execution['ended_at'] = datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'execution.json')


if __name__ == '__main__': main()
