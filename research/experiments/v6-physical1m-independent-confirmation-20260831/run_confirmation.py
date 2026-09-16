"""Fixed frozen-weight confirmation. No training, network, restart or rescue."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

from confirmation_contract import CELLS, HANDS, PAIRS, SEED, analyze, decks, disjoint_decks, raw_count

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-physical1m-learning-curve-20260831'
REVIEW_SHA = '68e6214a068f727f7abae83c0070bc5f1d765371b6bcd9fc733985dd3f8373aa'
EXEC_SHA = '076e30fd46017800d344abe691c5b1d1380cb001484bb4fc21de5ffa870b211c'
COPIES_SHA = 'eec7b2e22eb45db9d1fde68f80b46f1e91b58c1908625d0a9aaeb0ee482388cc'
MODEL_SHAS = {
    'source': '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2',
    'mid262': '7d7eeb0d648f2d1a51ff79b600e59e0fdc4afcca73541e90bd5dda304348a0c3',
    'final': 'bc4f62257a474ad438cd574d4c59b28ea009060749f0fb86e3e97c46120d0172',
}
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def verify_parent():
    assert sha(PARENT/'reviewed_analysis.json') == REVIEW_SHA
    assert sha(PARENT/'execution.json') == EXEC_SHA
    assert sha(PARENT/'execution_code/copy_manifest.json') == COPIES_SHA
    review = read(PARENT/'reviewed_analysis.json')
    assert review['status'] == 'PASS' and review['confirmation_gate_pass']
    assert review['new_training_hands'] == 1051652 and review['evaluation_hands'] == 327680
    parent_record = read(PARENT/'experiment.json')
    assert parent_record['status'] == 'COMPLETED'
    # Historical source copies are immutable; original paths may evolve later.
    for row in read(PARENT/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy']) == row['sha256']
    for label, expected in MODEL_SHAS.items():
        item = review['selection'][label]
        assert item['sha256'] == expected == sha(item['path'])
    for name, item in parent_record['artifact_integrity'].items():
        if item['type'] == 'file': assert sha(ROOT/name) == item['sha256']


def verify(copies, models=(), anchors=()):
    verify_parent()
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original', 'copy'])
    for row in [*models, *anchors]:
        assert sha(row['path']) == row['sha256'] == sha(row['source'])


def snapshot():
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
    return copies


def freeze():
    (BASE/'frozen').mkdir()
    selected = read(PARENT/'checkpoint_selection.json')
    models, anchors = {}, []
    for label, expected in MODEL_SHAS.items():
        source, target = Path(selected[label]['path']), BASE/'frozen'/f'{label}.pt'
        assert sha(source) == expected
        shutil.copy2(source, target)
        models[label] = dict(label=label, source=str(source), path=str(target), sha256=expected)
    for item in read(PARENT/'anchor_manifest.json'):
        source, target = Path(item['path']), BASE/'frozen'/f'anchor{item["index"]}.pt'
        assert sha(source) == item['sha256']
        shutil.copy2(source, target)
        anchors.append(dict(index=item['index'], source=str(source), path=str(target), sha256=item['sha256']))
    assert [r['index'] for r in anchors] == list(range(5))
    assert models['source']['sha256'] == anchors[0]['sha256']
    write(BASE/'model_manifest.json', models)
    write(BASE/'anchor_manifest.json', anchors)
    log('--artifact', BASE/'model_manifest.json', '--artifact', BASE/'anchor_manifest.json',
        *[v for r in [*models.values(), *anchors] for v in ['--artifact', r['path']]])
    return models, anchors


def check_deals():
    path = PARENT/'matrix/source_anchor0/pairs.jsonl'
    previous = [json.loads(line)['deck'] for line in path.read_text().splitlines()]
    assert previous == decks(20261001, PAIRS)
    current = decks()
    disjoint_decks(current, previous)
    report = dict(status='PASS', seed=SEED, pairs=PAIRS, unique_full_decks=PAIRS,
                  excluded_parent_seed=20261001, excluded_parent_pairs=PAIRS,
                  excluded_raw_path=str(path), excluded_raw_sha256=sha(path), full_deck_overlap=0,
                  limitation='Full-deck freshness, not disjoint partial boards or card combinations.')
    write(BASE/'deal_freshness.json', report)
    log('--artifact', BASE/'deal_freshness.json')
    return current


def collect(models, anchors, expected):
    values = {}
    for label, a in CELLS:
        directory = BASE/'matrix'/f'{label}_anchor{a}'
        summary, raw = read(directory/'summary.json'), directory/'pairs.jsonl'
        assert summary['status'] == 'COMPLETED' and summary['seed'] == SEED
        assert summary['evaluation_hands'] == PAIRS*2 and summary['pairs'] == PAIRS
        assert summary['candidate_sha256'] == models[label]['sha256'] and summary['anchor_sha256'] == anchors[a]['sha256']
        assert summary['pairs_sha256'] == sha(raw)
        rows = [json.loads(line) for line in raw.read_text().splitlines()]
        assert [r['pair_index'] for r in rows] == list(range(PAIRS)) and [r['deck'] for r in rows] == expected
        for r in rows:
            assert len(r['rewards_bb']) == 2 and all(math.isfinite(v) and abs(v) <= 200 for v in r['rewards_bb'])
            assert len(r['decisions']) == 2 and all(type(v) is int and v > 0 for v in r['decisions'])
        values[label, a] = [math.fsum(r['rewards_bb'])*50 for r in rows]
        log('--artifact', raw, '--artifact', directory/'summary.json', '--artifact', BASE/f'{label}_anchor{a}_stdout.log')
    assert all(v == 0 for v in values['source', 0])
    return values


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution.json', 'execution_code', 'frozen', 'matrix']):
        raise ValueError('No alternate arguments, overwrite or restart')
    for p in psutil.process_iter(['name', 'cmdline']):
        if p.pid != psutil.Process().pid and (p.info['name'] or '').lower().startswith('python') and any(
                Path(a).name in ['train_v5.py', 'v6_mirror_eval.py', 'play_slumbot_v6_journaled.py', 'run_curve.py', 'run_confirmation.py']
                for a in p.info['cmdline'] or []): raise RuntimeError('Another poker process is active')
    verify_parent()
    execution = dict(status='RUNNING', pid=psutil.Process().pid, create_time=psutil.Process().create_time(),
                     started_at=datetime.now(timezone.utc).isoformat(), children=[])
    write(BASE/'execution.json', execution)
    lock = threading.Lock()
    jobs = []
    try:
        copies = snapshot()
        cmd = ['-m', 'pytest', str(BASE/'test_confirmation.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        models, anchors = freeze()
        expected = check_deals()
        verify(copies, models.values(), anchors)
        evaluator = BASE/'execution_code/source_files/scripts/alpha_holdem/v6_mirror_eval.py'
        for label, a in CELLS:
            out = BASE/'matrix'/f'{label}_anchor{a}'
            cmd = [str(evaluator), '--candidate', models[label]['path'], '--anchor', anchors[a]['path'],
                   '--pairs', str(PAIRS), '--seed', str(SEED), '--device', 'cpu', '--out-dir', str(out)]
            record(cmd)
            jobs.append((label, a, out, cmd))
        log('--note', 'All models frozen and full-deck freshness verified before the fixed196608hand matrix; no outcome peeking or extensions.')
        print(json.dumps(dict(phase='fixed_evaluation', target_hands=HANDS, seed=SEED, frozen_final=MODEL_SHAS['final'])), flush=True)
        def evaluate(job):
            label, a, out, cmd = job
            with (BASE/f'{label}_anchor{a}_stdout.log').open('x') as output:
                process = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                                           creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                child = psutil.Process(process.pid)
                info = dict(role=f'{label}_anchor{a}', pid=process.pid, create_time=child.create_time(),
                            command=[sys.executable, *cmd], exit_code=None)
                with lock: execution['children'].append(info)
                child.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
                code = process.wait()
                with lock: info['exit_code'] = code
            return info
        with ThreadPoolExecutor(max_workers=6) as pool:
            futures = [pool.submit(evaluate, job) for job in jobs]
            previous = -1
            while not all(f.done() for f in futures):
                count = sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs)
                if count != previous:
                    log('--count', f'evaluation_hands={count}')
                    previous = count
                with lock: write(BASE/'execution.json', execution)
                time.sleep(10)
            outcomes = [f.result() for f in futures]
        assert len(outcomes) == 12 and all(r['exit_code'] == 0 for r in outcomes)
        count = sum(raw_count(out/'pairs.jsonl')*2 for _, _, out, _ in jobs)
        assert count == HANDS
        values = collect(models, anchors, expected)
        verify(copies, models.values(), anchors)
        report = dict(status='COMPLETED_PENDING_REVIEW', new_training_hands=0, evaluation_hands=count,
                      slumbot_hands=0, models=models, parent_review_sha256=REVIEW_SHA, **analyze(values))
        write(BASE/'completed_analysis.json', report)
        log('--count', 'new_training_hands=0', '--count', f'evaluation_hands={count}', '--count', 'slumbot_hands=0',
            '--artifact', BASE/'completed_analysis.json', '--note', 'All fixed cells completed; independent arithmetic/session review required before finish.')
        execution['status'] = 'COMPLETED_PENDING_REVIEW'
    except BaseException:
        execution['status'] = 'NEEDS_REVIEW'
        execution['error'] = traceback.format_exc()
        count = sum(raw_count(p)*2 for p in (BASE/'matrix').glob('*/pairs.jsonl'))
        log('--count', f'evaluation_hands={count}', '--note', 'Execution exception preserved; no automatic restart, retry or cell replay.')
        raise
    finally:
        execution['finished_at'] = datetime.now(timezone.utc).isoformat()
        write(BASE/'execution.json', execution)
        log('--artifact', BASE/'execution.json')


if __name__ == '__main__': main()
