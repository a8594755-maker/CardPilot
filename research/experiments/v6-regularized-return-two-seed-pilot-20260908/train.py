"""Run one fixed training stage, no automatic evaluation or second-stage launch."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
spec=importlib.util.spec_from_file_location('durable_runner',BASE.parent/'v6-regularized-durable-runner-20260908/runner.py')
r=importlib.util.module_from_spec(spec); spec.loader.exec_module(r)


def log(hands):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,
        '--count',f'training_hands={hands}'],cwd=ROOT,check=True,capture_output=True)


def train(stage):
    assert stage in (1,2)
    torch.set_num_threads(1)
    inputs=json.loads((BASE.parent/'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    binding=BASE/'inputs.json'
    if not binding.exists():
        assert stage==1
        r.write_json(binding,dict(inputs=inputs,train_sha=r.sha(Path(__file__)),
            protocol_sha=r.sha(BASE/'protocol.md'),sources=r.sources()))
    lock=json.loads(binding.read_text())
    assert lock['inputs']==inputs and lock['sources']==r.sources()
    assert lock['train_sha']==r.sha(Path(__file__)) and lock['protocol_sha']==r.sha(BASE/'protocol.md')
    r.write_json(BASE/f'stage{stage}_owner.json',dict(pid=os.getpid(),started_at=time.time(),command=sys.argv))
    target={1:16384,2:65536}[stage]
    if stage==2: assert (BASE/'stage1_evaluation_review.json').exists(),'complete prior frozen evaluation first'
    totals={}; started=time.perf_counter()
    for seed in ('1','3'):
        for label,eta in (('control',0.0),('regularized',.1)):
            folder=BASE/f'seed{seed}_{label}'
            if folder.exists():
                _,_,cursor,_=r.inspect(folder); totals[folder.name]=cursor
            else: totals[folder.name]=0
    for seed in ('1','3'):
        for label,eta in (('control',0.0),('regularized',.1)):
            folder=BASE/f'seed{seed}_{label}'
            if folder.exists(): e=r.restore(folder)
            else:
                assert stage==1
                e=r.online.Engine(inputs['parents'][seed]['path'],inputs['anchors']['standard10']['path'],
                    f'regularized-return-pilot-20260908-train-seed{seed}',eta)
                assert e.parent_sha==inputs['parents'][seed]['sha256']
                assert e.reference_sha==inputs['anchors']['standard10']['sha256']
                r.initialize(folder,e)
            assert e.cursor<=target and e.contract['eta_bb']==eta
            while e.cursor<target:
                assert shutil.disk_usage(BASE).free>8*1024**3,'disk safety stop at clean boundary'
                r.step(folder,e,min(2048,target-e.cursor))
                totals[folder.name]=e.cursor; log(sum(totals.values()))
                print(json.dumps(dict(stage=stage,arm=folder.name,hands=e.cursor,total=sum(totals.values()))),flush=True)
            _,checkpoint,cursor,updates=r.inspect(folder)
            receipt=BASE/f'stage{stage}_{folder.name}.json'
            if not receipt.exists(): r.write_json(receipt,dict(path=str(checkpoint),sha256=r.sha(checkpoint),
                hands=cursor,updates=updates,parent_sha=e.parent_sha,transition_hands=e.transition_hands,
                transition_rows=e.transition_rows))
            del e
    r.write_json(BASE/f'stage{stage}_training_terminal.json',dict(status='FROZEN_EVALUATION_REQUIRED',
        accounting=totals,total_new_hands=sum(totals.values()),stage_wall_seconds=time.perf_counter()-started))


if __name__=='__main__': train(int(sys.argv[1]))
