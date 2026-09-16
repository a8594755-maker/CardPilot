"""Run only the fixed stage1 evaluation after all training reviews pass."""
import gzip
import json
import os
from pathlib import Path
import subprocess
import sys
import time

from preflight import read, sha

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]


def write_new(path, value):
    with path.open('x',encoding='utf-8') as handle: json.dump(value,handle,indent=2)


def completed_raw_rows(path):
    if not path.exists(): return 0
    count = 0
    try:
        with gzip.open(path,'rt',encoding='utf-8') as handle:
            for line in handle:
                try: json.loads(line)
                except json.JSONDecodeError: break
                count += 1
    except (EOFError,OSError): pass
    return count


def main():
    terminal = read(BASE/'stage1_training_terminal.json')
    assert terminal['status'] == 'TRAINED_REVIEW_AND_EVALUATION_REQUIRED'
    contract = read(BASE/'input_contract.json')
    assert sha(BASE/'protocol.md') == contract['protocol_sha256']
    reviews = {}
    for seed,arm in ((1,'control'),(1,'independent'),(3,'independent'),(3,'control')):
        folder = BASE/f'seed{seed}_{arm}_stage1'
        if not (folder/'independent_review.json').exists():
            subprocess.run([sys.executable,str(BASE/'review_training.py'),str(folder)],cwd=ROOT,check=True)
        review = read(folder/'independent_review.json')
        assert review['passed'] and sha(folder/'latest.pt') == review['checkpoint_sha256']
        reviews[f'{seed}_{arm}'] = review
    for name,digest in contract['sources'].items(): assert sha(Path(name)) == digest
    inputs = {**contract['sources'],str(Path(__file__).resolve()):sha(Path(__file__)),
              str(BASE/'review_training.py'):sha(BASE/'review_training.py')}
    jobs = []
    for seed in (1,3):
        for arm in ('control','independent'):
            checkpoint = BASE/f'seed{seed}_{arm}_stage1/latest.pt'
            out = BASE/f'eval_seed{seed}_{arm}_stage1'
            job = BASE/f'evaluation_job_seed{seed}_{arm}_stage1'
            assert not out.exists() and not job.exists(), 'preserve existing evaluation attempt'
            argv = [sys.executable,'-u',str(BASE/'eval_candidate.py'),
                '--control',contract['parents'][str(seed)]['path'],'--treatment',str(checkpoint)]
            for name,anchor in contract['anchors'].items():
                assert sha(Path(anchor['path'])) == anchor['sha256']
                argv += ['--anchor',f"{name}={anchor['path']}"]
            argv += ['--pairs-per-anchor','1024','--seed',str(contract['eval_seeds'][f'{seed}_1']),
                     '--device','cuda','--out-dir',str(out)]
            jobs.append({'seed':seed,'arm':arm,'argv':argv,'out':str(out),'job':str(job)})
            inputs[str(checkpoint)] = reviews[f'{seed}_{arm}']['checkpoint_sha256']
    write_new(BASE/'stage1_evaluation_execution.json',{'input_sha256':inputs,'jobs':jobs,'expected_hands':131072})
    completed = 0
    for spec in jobs:
        job,out = Path(spec['job']),Path(spec['out'])
        job.mkdir()
        write_new(job/'command.json',spec['argv'])
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
            '--command',subprocess.list2cmdline(spec['argv']),'--artifact',str(job/'command.json')],check=True,capture_output=True)
        started = time.perf_counter()
        with (job/'stdout.log').open('x',encoding='utf-8') as handle:
            child = subprocess.Popen(spec['argv'],cwd=ROOT,stdout=handle,stderr=subprocess.STDOUT,
                env=dict(os.environ,OMP_NUM_THREADS='1',MKL_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1'),
                creationflags=subprocess.CREATE_NO_WINDOW)
        print(json.dumps({'phase':out.name,'pid':child.pid}),flush=True)
        while True:
            try: code = child.wait(timeout=60); break
            except subprocess.TimeoutExpired:
                count = completed + 4*completed_raw_rows(out/'common_deck_pairs.jsonl.gz')
                subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
                    '--count',f'evaluation_hands={count}'],check=True,capture_output=True)
        write_new(job/'terminal.json',{'returncode':code,'wall_seconds':time.perf_counter()-started})
        assert code == 0
        assert completed_raw_rows(out/'common_deck_pairs.jsonl.gz') == 8192
        completed += 32768
        subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
            '--count',f'evaluation_hands={completed}','--artifact',str(out/'summary.json')],check=True,capture_output=True)
    for name,digest in inputs.items(): assert sha(Path(name)) == digest
    write_new(BASE/'stage1_evaluation_terminal.json',{'completed_hands':completed,'status':'RAW_REVIEW_REQUIRED'})


if __name__ == '__main__': main()
