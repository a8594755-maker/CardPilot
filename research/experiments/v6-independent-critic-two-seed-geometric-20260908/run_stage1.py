"""Fixed four-job first stage; stops for evaluation, never silently retries."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import psutil
import torch

from preflight import read, sha

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
QUAL = BASE.parent/'v6-independent-observable-critic-qualification-20260908'


def write_new(path, obj):
    with path.open('x',encoding='utf-8') as handle: json.dump(obj,handle,indent=2)


def logger(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*args],
                   cwd=ROOT,check=True,capture_output=True,timeout=45)


def main():
    torch.set_num_threads(1)
    contract = read(BASE/'input_contract.json')
    assert contract['passed'] and sha(BASE/'protocol.md') == contract['protocol_sha256']
    assert read(BASE/'experiment.json')['status'] == 'RUNNING'
    for name,digest in contract['sources'].items(): assert sha(Path(name)) == digest
    conflicts = [p.pid for p in psutil.process_iter(['pid','name','cmdline'])
        if p.pid != os.getpid() and 'python' in (p.info['name'] or '').lower()
        and any(Path(a).name in {'run_stage1.py','train_job.py','train_candidate.py','run_trial.py','train_capture.py'}
                for a in p.info['cmdline'] or [])]
    assert not conflicts, conflicts
    assert shutil.disk_usage(BASE).free > 20*1024**3
    write_new(BASE/'stage1_owner.json',{'pid':os.getpid(),'create_time':psutil.Process().create_time(),
        'started_at':datetime.now(timezone.utc).isoformat(),'command':sys.orig_argv})
    sys.path.insert(0,str(QUAL.parent/'v6-preflop-actor-trunk-route-qualification-20260906/candidate/scripts'))
    results = []
    for seed,arm in ((1,'control'),(1,'independent'),(3,'independent'),(3,'control')):
        item = contract['parents'][str(seed)]
        parent_path = Path(item['path'])
        assert sha(parent_path) == item['sha256']
        parent = torch.load(parent_path,map_location='cpu',weights_only=False)
        physical = parent['environment_hand_accounting']['completed_hands']
        folder = BASE/f'seed{seed}_{arm}_stage1'
        folder.mkdir()
        prefixes = {}
        for name in ('h1_training_metrics.jsonl','opponent_assignments.jsonl'):
            source = parent_path.parent/name
            shutil.copyfile(source,folder/name)
            prefixes[name] = {'bytes':source.stat().st_size,'sha256':sha(source)}
        argv = read(parent_path.parent/'command.json')
        argv[0],argv[2] = sys.executable,str(BASE/'train_job.py')
        index = argv.index('--opponent-greedy-mixture'); assert float(argv[index+1]) == 0
        del argv[index:index+2]
        for key,value in {'--resume':parent_path,'--run-dir':folder,'--out':folder/'latest.pt',
            '--total-environment-hands':physical+262144,'--max-runtime-seconds':7200,
            '--deal-attempt-registry':BASE/'attempt_registry',
            '--opponent-assignment-provenance-file':folder/'opponent_assignments.jsonl'}.items():
            argv[argv.index(key)+1] = str(value)
        if arm == 'independent': argv.append('--independent-observable-critic')
        sources = {**contract['sources'],str(Path(__file__).resolve()):sha(Path(__file__))}
        write_new(folder/'job_contract.json',{'parent':str(parent_path),'parent_sha256':item['sha256'],
            'sources':sources,'arm':arm,'seed':seed,'stage':1,'prefixes':prefixes,
            'initial_physical':physical,'initial_transition':parent['total_hands'],'initial_iteration':parent['iteration']})
        write_new(folder/'command.json',argv)
        del parent
        logger('--command',subprocess.list2cmdline(argv),'--artifact',str(folder/'command.json'),
               '--artifact',str(folder/'job_contract.json'))
        started = time.perf_counter()
        with (folder/'stdout.log').open('x',encoding='utf-8') as handle:
            child = subprocess.Popen(argv,cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT,
                env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),
                creationflags=subprocess.CREATE_NO_WINDOW)
        write_new(folder/'process.json',{'pid':child.pid,'create_time':psutil.Process(child.pid).create_time()})
        print(json.dumps({'phase':folder.name,'pid':child.pid}),flush=True)
        while True:
            try: code = child.wait(timeout=60); break
            except subprocess.TimeoutExpired:
                rows = (folder/'h1_training_metrics.jsonl').read_text().splitlines()
                row = json.loads(rows[-1])
                count = sum(r['new_physical_hands'] for r in results) + row['environment_hand_accounting']['completed_hands']-physical
                logger('--count',f'training_hands={count}','--metric','phase='+folder.name)
        write_new(folder/'terminal_process.json',{'returncode':code,'wall_seconds':time.perf_counter()-started})
        assert code == 0, (folder,code)
        assert read(folder/'initial_gate.json')['passed']
        final = torch.load(folder/'latest.pt',map_location='cpu',weights_only=False)
        actual = final['environment_hand_accounting']['completed_hands']-physical
        assert actual >= 262144
        assert all(torch.isfinite(t).all() for t in final['model'].values())
        for name,digest in sources.items(): assert sha(Path(name)) == digest
        result = {'seed':seed,'arm':arm,'new_physical_hands':actual,
                  'checkpoint_sha256':sha(folder/'latest.pt'),'wall_seconds':time.perf_counter()-started,
                  'scope':'Terminal checks only; independent detailed review and evaluation still required.'}
        write_new(folder/'terminal_training.json',result)
        results.append(result)
        logger('--count',f"training_hands={sum(r['new_physical_hands'] for r in results)}",'--artifact',str(folder/'terminal_training.json'))
        del final
    write_new(BASE/'stage1_training_terminal.json',{'status':'TRAINED_REVIEW_AND_EVALUATION_REQUIRED','runs':results})
    print('Stage1 training complete; stopped for fixed evaluation.',flush=True)


if __name__ == '__main__': main()
