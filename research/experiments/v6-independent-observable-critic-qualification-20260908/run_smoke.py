"""One exclusive seed1 worker smoke. No automatic retry or record completion."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import psutil
import torch

BASE = Path(__file__).resolve().parent
PARENT = BASE.parent / 'v6-fixed-regimen-two-seed-2m-20260908/seed1_control_stage1'
EXPECTED = '52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2'


def sha(path):
    with path.open('rb') as handle:
        return hashlib.file_digest(handle, 'sha256').hexdigest()


def write_new(path, value):
    with path.open('x', encoding='utf-8') as handle:
        json.dump(value, handle, indent=2)


def set_option(argv, key, value):
    index = argv.index(key)
    argv[index+1] = str(value)


def main():
    torch.set_num_threads(1)
    assert sha(PARENT / 'latest.pt') == EXPECTED
    assert json.loads((BASE / 'experiment.json').read_text())['status'] == 'RUNNING'
    conflicts = [p.pid for p in psutil.process_iter(['pid', 'name', 'cmdline'])
                 if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower()
                 and any(Path(a).name in {'train_candidate.py', 'candidate_train.py', 'run_trial.py', 'run_probe.py', 'run_smoke.py'}
                         for a in p.info['cmdline'] or [])]
    assert not conflicts, conflicts
    assert shutil.disk_usage(BASE).free > 15 * 1024**3
    sys.path.insert(0, str(BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts'))
    parent = torch.load(PARENT / 'latest.pt', map_location='cpu', weights_only=False)
    initial = parent['environment_hand_accounting']['completed_hands']
    folder = BASE / 'seed1_first_smoke'
    folder.mkdir()  # Exclusive: never reuse a partial attempt.
    sources = {str(p.resolve()): sha(p) for p in BASE.glob('*.py')}
    write_new(BASE / 'runtime_sources.json', sources)
    prefixes = {}
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
        source = PARENT / name
        shutil.copyfile(source, folder / name)
        prefixes[name] = {'sha256': sha(source), 'bytes': source.stat().st_size}
    argv = json.loads((PARENT / 'command.json').read_text())
    argv[2] = str(BASE / 'train_candidate.py')
    index = argv.index('--opponent-greedy-mixture')
    assert float(argv[index+1]) == 0
    del argv[index:index+2]
    for key, value in {
        '--resume': PARENT / 'latest.pt', '--run-dir': folder,
        '--out': folder / 'latest.pt', '--max-runtime-seconds': 600,
        '--total-environment-hands': initial + 8192,
        '--opponent-assignment-provenance-file': folder / 'opponent_assignments.jsonl',
        '--deal-attempt-registry': BASE / 'attempt_registry',
    }.items():
        set_option(argv, key, value)
    argv.append('--independent-observable-critic')
    write_new(folder / 'command.json', argv)
    write_new(folder / 'input_contract.json', {'parent': str(PARENT / 'latest.pt'),
        'parent_sha256': EXPECTED, 'initial_physical_hands': initial,
        'initial_iteration': parent['iteration'], 'prefixes': prefixes,
        'target_new_physical_hands': 8192, 'sources': sources})
    del parent
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1',
               MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1')
    with (folder / 'stdout.log').open('x', encoding='utf-8') as output:
        child = subprocess.Popen(argv, cwd=BASE.parents[2], env=env, stdout=output,
            stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
    write_new(folder / 'process.json', {'pid': child.pid,
        'create_time': psutil.Process(child.pid).create_time(),
        'started_at': datetime.now(timezone.utc).isoformat(), 'command': argv})
    print(json.dumps({'pid': child.pid, 'folder': str(folder), 'initial': initial,
                      'target': initial + 8192}), flush=True)
    returncode = child.wait()
    write_new(folder / 'terminal_process.json', {'returncode': returncode,
        'ended_at': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'returncode': returncode}), flush=True)


if __name__ == '__main__':
    main()
