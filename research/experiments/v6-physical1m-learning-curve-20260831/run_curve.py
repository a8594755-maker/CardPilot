"""One fresh corrected-v6 physical1m curve; immutable runtime, no retries."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import traceback

from curve_contract import TARGET, PAIRS, EVAL_SEED, EVAL_HANDS, choose_curve, estimate, gate, raw_count

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-diverse-learned-league-pilot-20260831'
EXTERNAL = ROOT/'research/experiments/v6-source-fresh20k-slumbot-20260831'
SOURCE = ROOT/'models/baseline/standard10/latest.pt'
SOURCE_SHA = '91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428'
PARENT_EXEC_SHA = '572aa0ef9662eb0d22b8623b5b4acb687f309efe2775bc79a8d289fd88b5f959'
PARENT_REVIEW_SHA = '03e6f1c8a2613876a124cd9a1a3f6d7c86d3f360fd0843b53d1ac420fd29434f'
EXTERNAL_REVIEW_SHA = 'fd94d113dddb6ce2f0d425980b93eba9234078283e34aedcf2b63c72b52a5147'
RUN_ID = 'v6_physical1m_curve_20260831'
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'scripts'))
from research.experiment_log import capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): Path(path).write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def verify_parents():
    assert sha(SOURCE) == SOURCE_SHA
    assert sha(PARENT/'execution.json') == PARENT_EXEC_SHA
    assert sha(PARENT/'reviewed_analysis.json') == PARENT_REVIEW_SHA
    assert sha(EXTERNAL/'reviewed_analysis.json') == EXTERNAL_REVIEW_SHA
    assert read(PARENT/'reviewed_analysis.json')['status'] == 'PASS'
    for row in read(PARENT/'execution_code/copy_manifest.json'):
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original', 'copy'])


def training_command():
    assert sha(PARENT/'execution.json') == PARENT_EXEC_SHA
    child = next(r for r in read(PARENT/'execution.json')['children'] if r['role'] == 'train_control3')
    assert child['exit_code'] == 0
    cmd = [v.replace(str(PARENT), str(BASE)) for v in child['command'][1:]]
    run = BASE/'production'
    for flag, value in {'--total-environment-hands': TARGET, '--run-id': RUN_ID,
                        '--run-dir': run, '--out': run/'latest.pt',
                        '--opponent-assignment-provenance-file': run/'opponent_assignments.jsonl',
                        '--seed': 20260930, '--worker-seed-base': 2026093000,
                        '--max-runtime-seconds': 7200}.items():
        cmd[cmd.index(flag)+1] = str(value)
    return cmd


def verify(copies, anchors=()):
    verify_parents()
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original', 'copy'])
    for row in anchors:
        assert sha(row['path']) == row['sha256'] == sha(row['source'])


def archives_for(run):
    archives = {}
    for path in (run/'checkpoints').glob('checkpoint_iter*_hands*.pt'):
        match = re.fullmatch(r'checkpoint_iter(\d+)_hands(\d+)\.pt', path.name)
        assert match and int(match[1]) not in archives
        archives[int(match[1])] = path
    return archives


def health_and_freeze():
    import torch
    from alpha_holdem.policy_contract_v6 import validate_metadata
    run = BASE/'production'
    checkpoint = torch.load(run/'latest.pt', map_location='cpu', weights_only=False)
    validate_metadata(checkpoint)
    count = checkpoint['environment_hand_accounting']['completed_hands']
    assert count >= TARGET and checkpoint['run_id'] == RUN_ID
    cmd = ['scripts/alpha_holdem/audit_train_v5_fixed_pool_session.py', '--run-dir', str(run),
           '--expected-target-hands', '99999999', '--expected-target-environment-hands', str(TARGET),
           '--expected-final-iteration', str(checkpoint['iteration']), '--expected-pool-size', '3',
           '--expected-archive-every', '4', '--expected-normalization', 'global',
           '--out', str(run/'session_audit.json')]
    record(cmd)
    with (run/'audit_stdout.log').open('x') as output:
        subprocess.run([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, check=True)
    assert read(run/'session_audit.json')['status'] == 'PASS'
    rows = [json.loads(line) for line in (run/'h1_training_metrics.jsonl').read_text().splitlines()]
    archives = archives_for(run)
    chosen = choose_curve(rows, archives)
    counts = [r['environment_hand_accounting']['completed_hands'] for r in rows]
    assert all(v < TARGET for v in counts[:-1]) and TARGET <= counts[-1] <= count
    source = torch.load(SOURCE, map_location='cpu', weights_only=False)
    selection = {'source': dict(path=str(BASE/'frozen/anchor0.pt'), sha256=sha(BASE/'frozen/anchor0.pt'), physical_hands=0)}
    for label, path in [*[(label, archives[row['iteration']]) for label, row in chosen.items()], ('final', run/'latest.pt')]:
        payload = torch.load(path, map_location='cpu', weights_only=False)
        validate_metadata(payload)
        account = payload['environment_hand_accounting']
        assert account['prefix_complete'] and account['unknown_prefix_training_marker_hands'] == 0
        assert account['origin_run_id'] == payload['run_id'] == RUN_ID
        assert sum(w['completed_hands'] for w in account['session_worker_counts']) == account['completed_hands']
        if label != 'final': assert account['completed_hands'] == chosen[label]['environment_hand_accounting']['completed_hands']
        assert len(payload['model']) == 86 and all(torch.isfinite(v).all() for v in payload['model'].values())
        assert sum(not torch.equal(v, source['model'][k]) for k, v in payload['model'].items()) == 86
        assert len(payload['optimizer']['state']) == 86
        for state in payload['optimizer']['state'].values():
            assert float(state['step']) > 0 and all(torch.isfinite(v).all() for v in state.values() if isinstance(v, torch.Tensor))
        target = BASE/'frozen'/f'{label}.pt'
        shutil.copy2(path, target)
        selection[label] = dict(path=str(target), source=str(path), sha256=sha(target),
                                physical_hands=account['completed_hands'], iteration=payload['iteration'])
    assert list(selection) == ['source', 'mid262', 'mid524', 'final']
    write(BASE/'checkpoint_selection.json', selection)
    health = dict(status='PASS', new_training_hands=count, iteration=checkpoint['iteration'],
                  overshoot=count-TARGET, shutdown_counter_tail=count-counts[-1],
                  legacy_markers=checkpoint['total_hands'], finite_changed_tensors=86)
    write(run/'training_health.json', health)
    log('--count', f'new_training_hands={count}', '--artifact', BASE/'checkpoint_selection.json',
        *[v for item in selection.values() for v in ['--artifact', item['path']]],
        *[v for name in ['latest.pt', 'run_manifest.json', 'h1_training_metrics.jsonl', 'opponent_assignments.jsonl',
                         'latest_train.log', 'session_audit.json', 'audit_stdout.log', 'training_health.json'] for v in ['--artifact', run/name]],
        '--note', 'All curve weights frozen using only physical counters; no performance selection. Training/session health passed.')
    return selection, health


def main():
    import psutil
    import torch
    torch.set_num_threads(1)
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json', 'execution_code', 'production', 'frozen']):
        raise ValueError('Preserve existing experiment; no alternate arguments or restart')
    for p in psutil.process_iter(['name', 'cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ['train_v5.py', 'v6_mirror_eval.py', 'play_slumbot_v6_journaled.py', 'run_pilot.py', 'run_baseline.py', 'run_curve.py']
            for a in p.info['cmdline'] or []): raise RuntimeError('Another poker process is active')
    verify_parents()
    assert torch.cuda.is_available() and psutil.virtual_memory().available > 16*2**30
    execution = dict(status='RUNNING', pid=psutil.Process().pid, started_at=datetime.now(timezone.utc).isoformat(), children=[])
    write(BASE/'execution.json', execution)
    count, eval_hands = 0, 0
    try:
        directory = BASE/'execution_code'
        directory.mkdir()
        paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
        paths += [f'scripts/deep_cfr/{n}.py' for n in ['__init__', 'game_state', 'hand_eval']]
        paths += ['research/experiment_log.py']
        paths += [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py', '.md'}]
        capture_code_provenance(ROOT, directory, paths)
        copies = []
        for relative in paths:
            target = directory/'source_files'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
            copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
        write(directory/'copy_manifest.json', copies)
        log(*[v for name in ['source_manifest.json', 'code.patch', 'copy_manifest.json'] for v in ['--artifact', directory/name]])
        cmd = ['-m', 'pytest', str(BASE/'test_curve.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        (BASE/'frozen').mkdir()
        anchors = []
        for previous in read(PARENT/'anchor_manifest.json'):
            source = Path(previous['path'])
            assert sha(source) == previous['sha256']
            target = BASE/'frozen'/source.name
            shutil.copy2(source, target)
            anchors.append(dict(index=previous['index'], source=str(source), path=str(target), sha256=sha(target)))
        assert [r['index'] for r in anchors] == list(range(5))
        write(BASE/'anchor_manifest.json', anchors)
        log('--artifact', BASE/'anchor_manifest.json', *[v for r in anchors for v in ['--artifact', r['path']]])
        verify(copies, anchors)
        cmd = training_command()
        record(cmd)
        with (BASE/'trainer_stdout.log').open('x') as output:
            child = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                     creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
            info = dict(role='trainer', pid=child.pid, command=[sys.executable, *cmd], exit_code=None)
            execution['children'].append(info)
            write(BASE/'execution.json', execution)
            seen = -1
            while child.poll() is None:
                try: manifest = read(BASE/'production/run_manifest.json')
                except (OSError, json.JSONDecodeError): manifest = {}
                current = int((manifest.get('environment_hand_accounting') or {}).get('completed_hands', 0))
                if current > seen:
                    count, seen = current, current
                    log('--count', f'new_training_hands={count}', '--metric', f'active_iteration={manifest.get("iteration", 0)}')
                time.sleep(5)
            info['exit_code'] = child.wait()
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'trainer_stdout.log')
        if info['exit_code']: raise RuntimeError('Trainer failed; preserve evidence without retry')
        selection, health = health_and_freeze()
        count = health['new_training_hands']
        verify(copies, anchors)
        print(json.dumps(dict(phase='training_complete', **health)), flush=True)
        jobs = []
        for label, item in selection.items():
            for anchor in anchors:
                out = BASE/'matrix'/f'{label}_anchor{anchor["index"]}'
                cmd = ['scripts/alpha_holdem/v6_mirror_eval.py', '--candidate', item['path'], '--anchor', anchor['path'],
                       '--pairs', str(PAIRS), '--seed', str(EVAL_SEED), '--device', 'cpu', '--out-dir', str(out)]
                record(cmd)
                jobs.append((label, anchor['index'], out, cmd))
        log('--note', 'All training has ended; starting the one fixed327680hand matrix. No outcome peeking, selection or extensions.')
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
                eval_hands = sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs)
                if eval_hands != previous:
                    log('--count', f'evaluation_hands={eval_hands}')
                    previous = eval_hands
                write(BASE/'execution.json', execution)
                time.sleep(10)
            outcomes = [f.result() for f in futures]
        assert all(r['exit_code'] == 0 for r in outcomes)
        eval_hands = sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs)
        assert eval_hands == EVAL_HANDS
        values, decks = {}, None
        for label, a, out, _ in jobs:
            summary = read(out/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['evaluation_hands'] == 2*PAIRS and summary['seed'] == EVAL_SEED
            assert summary['candidate_sha256'] == selection[label]['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
            assert summary['pairs_sha256'] == sha(out/'pairs.jsonl')
            rows = [json.loads(line) for line in (out/'pairs.jsonl').read_text().splitlines()]
            assert [r['pair_index'] for r in rows] == list(range(PAIRS))
            current = [r['deck'] for r in rows]
            if decks is None: decks = current
            assert decks == current
            values[label, a] = [sum(r['rewards_bb'])*50 for r in rows]
            log('--artifact', out/'summary.json', '--artifact', out/'pairs.jsonl', '--artifact', BASE/f'{label}_anchor{a}_stdout.log')
        assert all(v == 0 for v in values['source', 0])
        primary = [dict(anchor=a, **estimate([f-s for f, s in zip(values['final', a], values['source', a])])) for a in range(5)]
        growth = estimate([sum(values['final', a][i]-values['mid262', a][i] for a in [3, 4])/2 for i in range(PAIRS)])
        passed = gate(primary, growth)
        verify(copies, anchors)
        for r in selection.values(): assert sha(r['path']) == r['sha256']
        report = dict(status='COMPLETED_PENDING_REVIEW', new_training_hands=count, evaluation_hands=eval_hands, slumbot_hands=0,
                      selection=selection, primary_contrasts=primary, heldout_growth=growth, confirmation_gate_pass=passed,
                      decision='ADMIT_INDEPENDENT_CONFIRMATION' if passed else 'PHYSICAL_SCALE_GATE_NOT_PASSED')
        write(BASE/'completed_analysis.json', report)
        log('--count', f'new_training_hands={count}', '--count', f'evaluation_hands={eval_hands}',
            '--artifact', BASE/'completed_analysis.json', '--note', 'Fixed training/matrix completed; independent review required before finish.')
        execution['status'] = 'COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status'] = 'NEEDS_REVIEW'
        execution['error'] = traceback.format_exc()
        try: count = read(BASE/'production/run_manifest.json')['environment_hand_accounting']['completed_hands']
        except (OSError, KeyError, json.JSONDecodeError): pass
        eval_hands = sum(raw_count(p)*2 for p in (BASE/'matrix').glob('*/pairs.jsonl'))
        log('--count', f'new_training_hands={count}', '--count', f'evaluation_hands={eval_hands}',
            '--note', 'Terminal execution exception preserved. Do not automatically reset, restart or replay any hands/cells.')
        raise
    finally:
        execution['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'execution.json')


if __name__ == '__main__': main()
