"""One fixed source-KL intervention and fresh control matrix; no auto retry."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import statistics
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-full-network-learning-curve-20260831'
TARGET, PAIRS, EVAL_SEED, EVAL_HANDS = 262144, 8192, 20260921, 245760
RUN_ID = 'v6_kl010_retention_20260831'
EXEC_SHA = '47e842579af7d536b09571db45e8bd02620d52afe614d0bdbdca13ee2640b41c'
CONTROL_SHA = '0d2f660b3225664c5ed2bc85467649d3f3d17930cba8ab86c70b3d2082ee8606'
SOURCE_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def training_command():
    assert sha(PARENT/'execution.json') == EXEC_SHA
    original = json.loads((PARENT/'execution.json').read_text())['children'][0]['command'][1:]
    cmd = [value.replace(str(PARENT), str(BASE)) for value in original]
    assert float(cmd[cmd.index('--source-policy-kl-coef')+1]) == .01
    cmd[cmd.index('--source-policy-kl-coef')+1] = '0.1'
    cmd[cmd.index('--run-id')+1] = RUN_ID
    return cmd


def estimate(values):
    if len(values) < 2 or not all(math.isfinite(x) for x in values): raise ValueError('Invalid independent pairs')
    mean = statistics.mean(values)
    se = statistics.stdev(values)/math.sqrt(len(values))
    z = statistics.NormalDist().inv_cdf(1-.05/12)
    return dict(bb_per_100=mean, ci95=[mean-1.96*se, mean+1.96*se],
                ci_adjusted=[mean-z*se, mean+z*se], standard_error=se)


def gate(contrasts, retention):
    if len(contrasts) != 5 or [r['anchor'] for r in contrasts] != list(range(5)):
        raise ValueError('Wrong source contrast family')
    if not all(math.isfinite(v) for r in [*contrasts, retention]
               for v in [r['bb_per_100'], *r['ci_adjusted']]):
        raise ValueError('Nonfinite gate evidence')
    significant = {r['anchor'] for r in contrasts if r['ci_adjusted'][0] > 0}
    return (all(r['bb_per_100'] > 0 for r in contrasts) and len(significant) >= 3
            and 0 in significant and bool(significant & {3, 4}) and retention['ci_adjusted'][0] > 0)


def raw_count(path):
    path = Path(path)
    return path.read_bytes().count(b'\n') if path.exists() else 0


def verify(copies, anchors):
    assert sha(ROOT/'models/baseline/standard10/latest.pt') == SOURCE_SHA
    assert sha(PARENT/'execution.json') == EXEC_SHA
    assert sha(PARENT/'frozen/final.pt') == CONTROL_SHA
    for item in copies:
        assert all(sha(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
    for item in anchors:
        assert sha(item['path']) == item['sha256'] == sha(item['source'])


def main():
    import psutil
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    if sys.argv[1:] or any((BASE/name).exists() for name in ['production', 'frozen', 'execution.json', 'execution_code']):
        raise ValueError('Fixed experiment; preserve existing run')
    for p in psutil.process_iter(['pid', 'name', 'cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
                Path(a).name in ['train_v5.py', 'v6_mirror_eval.py', 'play_slumbot.py', 'play_slumbot_v6.py', 'run_pilot.py', 'run_curve.py']
                for a in p.info['cmdline'] or []): raise RuntimeError('Another poker job is active')
    assert psutil.cpu_count() >= 8 and psutil.virtual_memory().available >= 16*2**30
    parent_review = json.loads((PARENT/'reviewed_analysis.json').read_text())
    assert parent_review['status'] == 'PASS' and parent_review['decision'] == 'FINAL_BREADTH_GATE_NOT_PASSED'
    started = time.time()
    execution = dict(status='RUNNING', pid=psutil.Process().pid, started_at=datetime.now(timezone.utc).isoformat(), children=[])
    def save(): (BASE/'execution.json').write_text(json.dumps(execution, indent=2)+'\n')
    save()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py']
    paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
    directory = BASE/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    log(*[v for name in ['source_manifest.json', 'code.patch', 'copy_manifest.json'] for v in ['--artifact', directory/name]])
    cmd = ['-m', 'pytest', str(BASE/'test_pilot.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
    record(cmd)
    subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
    log('--artifact', BASE/'prerun_tests.xml')
    (BASE/'frozen').mkdir()
    anchors = []
    for old in json.loads((PARENT/'anchor_manifest.json').read_text()):
        source = Path(old['path'])
        assert sha(source) == old['sha256']
        target = BASE/'frozen'/source.name
        shutil.copy2(source, target)
        anchors.append(dict(index=old['index'], path=str(target), source=str(source), sha256=sha(target), role=old['role']))
    shutil.copy2(PARENT/'frozen/final.pt', BASE/'frozen/weak_control.pt')
    assert sha(BASE/'frozen/weak_control.pt') == CONTROL_SHA
    (BASE/'anchor_manifest.json').write_text(json.dumps(anchors, indent=2)+'\n')
    verify(copies, anchors)
    log('--artifact', BASE/'anchor_manifest.json', '--artifact', BASE/'frozen/weak_control.pt',
        *[v for item in anchors for v in ['--artifact', item['path']]])
    count = 0
    try:
        cmd = training_command()
        record(cmd)
        with (BASE/'trainer_stdout.log').open('x') as output:
            child = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            info = dict(role='trainer', pid=child.pid, command=[sys.executable, *cmd], exit_code=None)
            execution['children'].append(info)
            save()
            log('--metric', f'trainer_pid={child.pid}')
            seen = -1
            while child.poll() is None:
                try: manifest = json.loads((BASE/'production/run_manifest.json').read_text())
                except (OSError, json.JSONDecodeError): manifest = {}
                current = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands', 0))
                if current > seen:
                    count, seen = current, current
                    log('--count', f'new_training_hands={count}', '--metric', f'latest_iteration={manifest.get("iteration", 0)}')
                time.sleep(5)
            info['exit_code'] = child.wait()
        save()
        log('--artifact', BASE/'trainer_stdout.log', '--metric', f'trainer_exit_code={info["exit_code"]}')
        if info['exit_code']: raise RuntimeError('Trainer exited nonzero; preserve state')
        run = BASE/'production'
        ckpt = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
        validate_metadata(ckpt)
        count = ckpt['environment_hand_accounting']['completed_hands']
        assert count >= TARGET and ckpt['environment_hand_accounting']['prefix_complete']
        assert ckpt['config']['source_policy_kl_coef'] == .1 and len(ckpt['optimizer']['state']) == 86
        cmd = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
               '--expected-target-hands', '99999999', '--expected-target-environment-hands', str(TARGET),
               '--expected-final-iteration', str(ckpt['iteration']), '--expected-pool-size', '3',
               '--expected-archive-every', '4', '--expected-normalization', 'global', '--out', str(BASE/'session_audit.json')]
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        shutil.copy2(run/'latest.pt', BASE/'frozen/treatment.pt')
        candidates = {label:dict(path=str(path), sha256=sha(path)) for label, path in [
            ('source', BASE/'frozen/anchor0.pt'), ('weak_control', BASE/'frozen/weak_control.pt'), ('treatment', BASE/'frozen/treatment.pt')]}
        (BASE/'candidate_manifest.json').write_text(json.dumps(candidates, indent=2)+'\n')
        verify(copies, anchors)
        log('--count', f'new_training_hands={count}', '--artifact', BASE/'session_audit.json',
            '--artifact', BASE/'candidate_manifest.json', '--artifact', BASE/'frozen/treatment.pt',
            *[v for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl'] for v in ['--artifact', run/name]],
            '--note', 'Sole new final frozen before performance evaluation; starting fixed245760hand fresh matrix. Old control is not eligible for admission.')
        jobs = []
        for label, item in candidates.items():
            for anchor in anchors:
                out = BASE/'matrix'/f'{label}_anchor{anchor["index"]}'
                cmd = ['scripts/alpha_holdem/v6_mirror_eval.py', '--candidate', item['path'], '--anchor', anchor['path'],
                       '--pairs', str(PAIRS), '--seed', str(EVAL_SEED), '--device', 'cpu', '--out-dir', str(out)]
                record(cmd)
                jobs.append((label, anchor['index'], out, cmd))
        def evaluate(job):
            label, index, out, cmd = job
            with (BASE/f'{label}_anchor{index}_stdout.log').open('x') as output:
                process = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                psutil.Process(process.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
                info = dict(role=f'{label}_anchor{index}', pid=process.pid, command=[sys.executable, *cmd], exit_code=None)
                execution['children'].append(info)
                info['exit_code'] = process.wait()
            return info
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            previous = -1
            while not all(f.done() for f in futures):
                total = sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs)
                if total != previous:
                    log('--count', f'evaluation_hands={total}')
                    previous = total
                save()
                time.sleep(10)
            outcomes = [f.result() for f in futures]
        save()
        assert all(row['exit_code'] == 0 for row in outcomes)
        assert sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs) == EVAL_HANDS
        cells, shared_decks = {}, None
        for label, index, out, _ in jobs:
            summary = json.loads((out/'summary.json').read_text())
            assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 2*PAIRS
            assert summary['candidate_sha256'] == candidates[label]['sha256'] and summary['anchor_sha256'] == anchors[index]['sha256']
            assert sha(out/'pairs.jsonl') == summary['pairs_sha256']
            rows = [json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
            assert [row['pair_index'] for row in rows] == list(range(PAIRS))
            decks = [row['deck'] for row in rows]
            if shared_decks is None: shared_decks = decks
            assert shared_decks == decks
            cells[label, index] = [sum(row['rewards_bb'])*50 for row in rows]
            log('--artifact', out/'summary.json', '--artifact', out/'pairs.jsonl', '--artifact', BASE/f'{label}_anchor{index}_stdout.log')
        assert all(x == 0 for x in cells['source', 0])
        primary = [dict(anchor=a, **estimate([b-s for s, b in zip(cells['source', a], cells['treatment', a])])) for a in range(5)]
        retention = estimate([statistics.mean(cells['treatment', a][i]-cells['weak_control', a][i] for a in [3, 4]) for i in range(PAIRS)])
        passed = gate(primary, retention)
        verify(copies, anchors)
        for item in candidates.values(): assert sha(item['path']) == item['sha256']
        report = dict(status='COMPLETED_PENDING_REVIEW', new_training_hands=count, evaluation_hands=EVAL_HANDS,
                      slumbot_hands=0, primary_contrasts=primary, retention_contrast=retention,
                      confirmation_gate_pass=passed, decision='ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'RETENTION_GATE_NOT_PASSED')
        (BASE/'completed_analysis.json').write_text(json.dumps(report, indent=2)+'\n')
        log('--count', f'new_training_hands={count}', '--count', f'evaluation_hands={EVAL_HANDS}',
            '--artifact', BASE/'completed_analysis.json', '--note', 'Fixed treatment and matrix complete; independent review required before finish/admission. No old checkpoint promotion.')
        execution['status'] = 'COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status'] = 'NEEDS_REVIEW'
        execution['error'] = traceback.format_exc()
        log('--count', f'new_training_hands={count}', '--note', 'Terminal wrapper exception; preserve all artifacts, no automatic retraining or cell replay.')
        raise
    finally:
        execution['finished_at'] = datetime.now(timezone.utc).isoformat()
        execution['wall_time_seconds'] = time.time()-started
        save()
        log('--artifact', BASE/'execution.json')


if __name__ == '__main__': main()
