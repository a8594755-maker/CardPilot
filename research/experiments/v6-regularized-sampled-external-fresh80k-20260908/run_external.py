"""Exclusive fixed-wave executor. No restart, replacements or efficacy stopping."""
from datetime import datetime, timezone
from importlib import metadata
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil
import protocol as p

BASE, ROOT = p.BASE, p.ROOT


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    with Path(path).open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def write(path, value):
    with Path(path).open('x', encoding='utf-8') as f:
        json.dump(value, f, indent=2, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())


def check(inputs):
    for path, digest in inputs.items():
        p.require(sha(path) == digest, 'Frozen input changed: ' + path)


def log(*args):
    subprocess.run([sys.executable, str(ROOT / 'research/experiment_log.py'), 'update', BASE.name,
                    *args], cwd=ROOT, check=True, capture_output=True)


def count_raw():
    count = 0
    for path in (BASE / 'sessions').glob('*/*/hands.jsonl'):
        with path.open('rb') as f:
            for line in f:
                if line.endswith(b'\n'):
                    json.loads(line)
                    count += 1
    return count


def validate_summary(summary, item):
    p.require(summary['status'] == 'COMPLETED' and
        summary['successful_hands'] == summary['attempted_hands'] == summary['target_hands'] == item['hands'],
        'Incomplete planned session')
    p.require(summary['session_id'] == item['session_id'] and summary['policy_seed'] == item['policy_seed'] and
        summary['model_sha256'] == p.MODEL_HASHES[item['arm']], 'Changed session identity')
    p.require(summary['policy_mode'] == 'sample' and summary['policy_temperature'] == 1 and
        summary['observation_bridge_contract'] == p.BRIDGE and summary['frozen_identity_verified'] and
        summary['closing_event_persisted'], 'Changed execution or unclosed evidence')


def prepare():
    p.require(read(BASE / 'experiment.json')['status'] == 'RUNNING', 'Register first')
    p.require(read(BASE / 'session_qualification.json')['passed'], 'Full session qualification required')
    p.require(not (BASE / 'execution').exists(), 'Existing execution: do not restart')
    prior_ids, prior_seeds, prior_tokens, prior_hashes, unreadable = set(), set(), set(), {}, []
    for path in (ROOT / 'research/experiments').glob('*/sessions/**/hands.jsonl'):
        if BASE in path.parents:
            continue
        try:
            with path.open('rb') as f:
                line = f.readline()
            if not line:
                continue
            row = json.loads(line)
            if row.get('session_token_sha256'):
                prior_ids.add(row['session_id'])
                prior_seeds.add(row['policy_seed'])
                prior_tokens.add(row['session_token_sha256'])
                prior_hashes[str(path)] = dict(prefix_bytes=len(line), prefix_sha256=hashlib.sha256(line).hexdigest())
        except (OSError, ValueError, KeyError) as exc:
            unreadable.append(dict(path=str(path), error=type(exc).__name__))
    for path in (ROOT / 'research/experiments').glob('*/*combined_audit.json'):
        try:
            data = read(path)
            if data.get('status') == 'PASS':
                for row in data.get('results', []):
                    prior_tokens.update(row.get('token_sha256', []))
        except (OSError, ValueError) as exc:
            unreadable.append(dict(path=str(path), error=type(exc).__name__))
    p.require(not prior_ids.intersection(r['session_id'] for r in p.schedule()), 'Reused session IDs')
    p.require(not prior_seeds.intersection(r['policy_seed'] for r in p.schedule()), 'Reused policy seeds')
    for arm, digest in p.MODEL_HASHES.items():
        p.require(sha(p.EXPORTS / (arm + '.pt')) == digest, 'Changed qualified export')
    runtime = BASE / 'runtime'
    runtime.mkdir(exist_ok=False)
    for package in ('alpha_holdem', 'deep_cfr'):
        for src in (ROOT / 'scripts' / package).rglob('*.py'):
            if '__pycache__' in src.parts:
                continue
            dest = runtime / src.relative_to(ROOT / 'scripts')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest)
    (BASE / 'frozen').mkdir(exist_ok=False)
    for arm in p.ARMS:
        shutil.copy2(p.EXPORTS / (arm + '.pt'), BASE / 'frozen' / (arm + '.pt'))
    inputs = {str(f):sha(f) for f in runtime.rglob('*.py')}
    inputs.update({str(f):sha(f) for f in BASE.glob('*.py')})
    for f in [p.TEMPLATE, BASE / 'preregistration.md', BASE / 'session_qualification.json',
              BASE / 'protocol_tests.xml', BASE / 'replay_tests.xml', ROOT / 'research/experiment_log.py',
              *list((BASE / 'frozen').glob('*.pt'))]:
        inputs[str(f)] = sha(f)
    manifest = dict(created_at=datetime.now(timezone.utc).isoformat(), inputs=inputs,
        schedule=p.schedule(), models=p.MODEL_HASHES, prior_tokens=sorted(prior_tokens),
        prior_prefixes=prior_hashes, unreadable_prior=unreadable,
        prior_scope='Readable raw initial tokens and PASS combined-audit chains; unknown tails not covered.',
        python=sys.version, executable=sys.executable,
        packages={n:metadata.version(n) for n in ('torch','numpy','scipy','requests','psutil')},
        commands={r['session_id']:subprocess.list2cmdline([sys.executable,'-B',*p.session_command(r,runtime)]) for r in p.schedule()})
    write(BASE / 'frozen_manifest.json', manifest)
    log('--artifact', str(BASE / 'frozen_manifest.json'), '--command',
        subprocess.list2cmdline([sys.executable, '-B', str(Path(__file__).resolve()), 'run']))
    print('Prepared fixed 32 sessions / 80000 development hands; zero requests.', flush=True)


def launch(argv, directory, env):
    directory.mkdir(exist_ok=False, parents=True)
    stdout = (directory / 'stdout.log').open('xb')
    stderr = (directory / 'stderr.log').open('xb')
    process = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=stdout, stderr=stderr,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    write(directory / 'process.json', dict(pid=process.pid, create_time=psutil.Process(process.pid).create_time(),
          argv=argv, exact_command=subprocess.list2cmdline(argv)))
    return process, stdout, stderr, directory


def drain(jobs):
    last = 0
    while any(job[0].poll() is None for job in jobs):
        if time.monotonic() - last >= 60:
            hands = count_raw()
            log('--count', f'evaluation_hands={hands}', '--metric', f'external_hands={hands}')
            print(f'Committed external hands: {hands}', flush=True)
            last = time.monotonic()
        time.sleep(2)
    codes = []
    for process, stdout, stderr, directory in jobs:
        stdout.close()
        stderr.close()
        codes.append(process.returncode)
        write(directory / 'terminal.json', dict(exit_code=process.returncode, pid=process.pid))
    return codes


def run():
    manifest = read(BASE / 'frozen_manifest.json')
    check(manifest['inputs'])
    p.require(manifest['schedule'] == p.schedule() and manifest['models'] == p.MODEL_HASHES, 'Plan changed')
    p.require(manifest['python'] == sys.version and manifest['executable'] == sys.executable, 'Python changed')
    p.require(all(metadata.version(n) == v for n,v in manifest['packages'].items()), 'Packages changed')
    for path, info in manifest['prior_prefixes'].items():
        with Path(path).open('rb') as f:
            p.require(hashlib.sha256(f.read(info['prefix_bytes'])).hexdigest() == info['prefix_sha256'], 'Prior prefix changed')
    execution = BASE / 'execution'
    execution.mkdir(exist_ok=False)
    write(execution / 'owner.json', dict(pid=os.getpid(), create_time=psutil.Process().create_time()))
    started = time.monotonic()
    runtime = BASE / 'runtime'
    env = dict(os.environ, PYTHONPATH=str(runtime), PYTHONDONTWRITEBYTECODE='1',
               OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    jobs = []
    try:
        for wave in range(4):
            check(manifest['inputs'])
            jobs = []
            for item in p.schedule():
                if item['wave'] == wave:
                    argv = [sys.executable, '-B', *p.session_command(item, runtime)]
                    jobs.append(launch(argv, execution / item['session_id'], env))
            p.require(all(code == 0 for code in drain(jobs)), 'Session failure: no new waves')
            for item in p.schedule():
                if item['wave'] == wave:
                    directory = BASE / 'sessions' / item['arm'] / f"s{item['index']:02d}"
                    summary = read(directory / 'summary.json')
                    validate_summary(summary, item)
                    p.require(sha(directory / 'hands.jsonl') == summary['hands_sha256'] and
                              sha(directory / 'journal.jsonl') == summary['journal_sha256'], 'Raw evidence changed')
            print(f'Wave {wave+1}/4 complete', flush=True)
        check(manifest['inputs'])
        write(execution / 'terminal.json', dict(status='EVALUATION_COMPLETE_PENDING_AUDIT',
             wall_seconds=time.monotonic()-started, external_hands=count_raw()))
        log('--count', f'evaluation_hands={count_raw()}', '--artifact', str(execution / 'terminal.json'),
            '--metric', 'external_execution_complete=true', '--note', 'All fixed sessions terminal; full audits and record finish remain pending.')
    except BaseException as exc:
        live_or_unclosed = [j for j in jobs if not (j[3] / 'terminal.json').exists()]
        if live_or_unclosed:
            drain(live_or_unclosed)
        write(execution / 'failure.json', dict(error=repr(exc), wall_seconds=time.monotonic()-started,
                                             external_hands=count_raw()))
        log('--count', f'evaluation_hands={count_raw()}', '--artifact', str(execution / 'failure.json'),
            '--note', 'Controller failure; retained already-started sessions drained. Do not restart or replace.')
        raise


if __name__ == '__main__':
    {'prepare':prepare, 'run':run}[sys.argv[1]]()
