"""Exclusive second attempt: actual extended-state resume and initial capture."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

import psutil
import torch

from run_smoke import sha, write_new, set_option

BASE = Path(__file__).resolve().parent


def main():
    parent_dir = BASE.parent / 'v6-fixed-regimen-two-seed-2m-20260908/seed3_control_stage1'
    review = {'checkpoint_sha256': 'c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94'}
    assert sha(parent_dir / 'latest.pt') == review['checkpoint_sha256']
    conflicts = [p.pid for p in psutil.process_iter(['pid', 'name', 'cmdline'])
                 if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower()
                 and any(Path(a).name in {'train_candidate.py', 'train_capture.py', 'run_smoke.py', 'run_restart.py'}
                         for a in p.info['cmdline'] or [])]
    assert not conflicts, conflicts
    sys.path.insert(0, str(BASE.parent / 'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts'))
    parent = torch.load(parent_dir / 'latest.pt', map_location='cpu', weights_only=False)
    initial = parent['environment_hand_accounting']['completed_hands']
    folder = BASE / 'seed3_first_capture_v2'
    folder.mkdir()
    sources = {str(p.resolve()): sha(p) for p in BASE.glob('*.py')}
    prefixes = {}
    for name in ('h1_training_metrics.jsonl', 'opponent_assignments.jsonl'):
        source = parent_dir / name
        shutil.copyfile(source, folder / name)
        prefixes[name] = {'sha256': sha(source), 'bytes': source.stat().st_size}
    argv = json.loads((parent_dir / 'command.json').read_text())
    argv[2] = str(BASE / 'train_capture_derivation_v2.py')
    for key, value in {'--resume': parent_dir / 'latest.pt', '--run-dir': folder,
        '--out': folder / 'latest.pt', '--total-environment-hands': initial+4096,
        '--opponent-assignment-provenance-file': folder / 'opponent_assignments.jsonl'}.items():
        set_option(argv, key, value)
    index = argv.index('--opponent-greedy-mixture')
    assert float(argv[index+1]) == 0
    del argv[index:index+2]
    argv.append('--independent-observable-critic')
    set_option(argv, '--deal-attempt-registry', BASE / 'attempt_registry')
    set_option(argv, '--max-runtime-seconds', 600)
    write_new(folder / 'command.json', argv)
    write_new(folder / 'capture_contract.json', {'parent_sha256': review['checkpoint_sha256'],
        'sources': sources, 'prefixes': prefixes, 'initial_physical_hands': initial,
        'initial_iteration': parent['iteration'], 'target_new_hands': 4096,
        'stopping': 'First complete PPO iteration crossing target; max600s; no retry.'})
    del parent
    with (folder / 'stdout.log').open('x', encoding='utf-8') as output:
        child = subprocess.Popen(argv, cwd=BASE.parents[2], stdout=output, stderr=subprocess.STDOUT,
            env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1', OPENBLAS_NUM_THREADS='1'),
            creationflags=subprocess.CREATE_NO_WINDOW)
    write_new(folder / 'process.json', {'pid': child.pid, 'create_time': psutil.Process(child.pid).create_time(),
        'started_at': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'pid': child.pid, 'target': initial+4096}), flush=True)
    code = child.wait()
    write_new(folder / 'terminal_process.json', {'returncode': code, 'ended_at': datetime.now(timezone.utc).isoformat()})
    print(json.dumps({'returncode': code}), flush=True)


if __name__ == '__main__':
    main()
