"""Append-only batched update transactions, fail closed on any unfinished tail."""
import importlib.util
import json
import os
from pathlib import Path
import time
import torch

BASE=Path(__file__).resolve().parent
ROOT=BASE.parents[2]
spec=importlib.util.spec_from_file_location('batch_collector',BASE.parent/'v6-regularized-batched-collector-20260908/collector.py')
batch=importlib.util.module_from_spec(spec); spec.loader.exec_module(batch)
online=batch.online
sha=online.c.sha


def write_json(path,value):
    with Path(path).open('x',encoding='utf-8') as handle:
        json.dump(value,handle,indent=2); handle.flush(); os.fsync(handle.fileno())


def sources():
    paths=list((ROOT/'scripts/alpha_holdem').glob('*.py'))
    paths += [Path(__file__),Path(batch.__file__),Path(online.__file__),
        Path(online.adapter.__file__),Path(online.c.__file__),
        BASE.parent/'v6-regularized-return-kernel-20260908/regularized_return.py',
        BASE.parent/'v6-sampled-physical-evaluator-qualification-20260908/sampled_eval.py']
    return {str(p.resolve()):sha(p) for p in paths}


def initialize(folder,engine):
    folder=Path(folder); folder.mkdir(exist_ok=False)
    engine.save(folder/'initial.pt')
    write_json(folder/'manifest.json',dict(schema='regularized-batched-transactions-v1',
        contract=engine.contract,initial_sha=sha(folder/'initial.pt'),sources=sources(),
        torch_version=torch.__version__,threads=torch.get_num_threads(),device='cpu',
        parent_sha=engine.parent_sha,reference_sha=engine.reference_sha))


def inspect(folder):
    folder=Path(folder); manifest=json.loads((folder/'manifest.json').read_text())
    assert manifest['schema']=='regularized-batched-transactions-v1'
    assert manifest['sources']==sources(),'source changed'
    assert manifest['torch_version']==torch.__version__ and manifest['threads']==torch.get_num_threads()
    checkpoint=folder/'initial.pt'; previous=sha(checkpoint)
    assert previous==manifest['initial_sha']
    cursor=0; updates=0
    for index,directory in enumerate(sorted(folder.glob('update-*'))):
        assert directory.name==f'update-{index:06d}'
        intent=json.loads((directory/'intent.json').read_text())
        assert (directory/'commit.json').exists(),'unfinished transaction: preserve and reconcile; never auto replay'
        commit=json.loads((directory/'commit.json').read_text())
        assert intent['start']==cursor and intent['parent_checkpoint_sha']==previous
        assert commit['intent_sha']==sha(directory/'intent.json')
        assert commit['raw_sha']==sha(directory/'hands.jsonl')
        traces=[json.loads(line) for line in (directory/'hands.jsonl').read_text().splitlines()]
        assert len(traces)==intent['hands'] and commit['hands']==len(traces)
        for j,t in enumerate(traces):
            assert t['key']==online.key(manifest['contract']['namespace'],cursor+j)
        cursor+=len(traces); updates+=1
        checkpoint=directory/'checkpoint.pt'; previous=sha(checkpoint)
        assert previous==commit['checkpoint_sha'] and commit['cursor']==cursor
    return manifest,checkpoint,cursor,updates


def restore(folder):
    manifest,checkpoint,cursor,updates=inspect(folder)
    engine=online.Engine.restore(checkpoint,manifest['contract'])
    assert engine.cursor==cursor and engine.updates==updates
    assert engine.parent_sha==manifest['parent_sha'] and engine.reference_sha==manifest['reference_sha']
    return engine


def step(folder,engine,hands,fail_at=None):
    assert isinstance(hands,int) and hands>0
    folder=Path(folder)
    manifest,checkpoint,cursor,updates=inspect(folder)
    assert engine.contract==manifest['contract'] and engine.cursor==cursor and engine.updates==updates
    # Exclusive directory is the claim: competing owners cannot execute same batch.
    directory=folder/f'update-{updates:06d}'; directory.mkdir(exist_ok=False)
    write_json(directory/'intent.json',dict(start=cursor,hands=hands,parent_checkpoint_sha=sha(checkpoint)))
    if fail_at=='intent': raise RuntimeError('injected interruption after intent')
    started=time.perf_counter()
    traces,data=batch.collect(engine.model,engine.reference,engine.contract['namespace'],cursor,hands,engine.contract['eta_bb'])
    with (directory/'hands.jsonl').open('x',encoding='utf-8') as raw:
        for trace in traces: raw.write(json.dumps(trace)+'\n')
        raw.flush(); os.fsync(raw.fileno())
    if fail_at=='raw': raise RuntimeError('injected interruption after raw')
    torch.set_rng_state(engine.rng)
    stats=online.adapter.trinal_clip_ppo_update(engine.model,engine.optimizer,data,'cpu',
        epochs=1,mini_batch_size=16384,gamma=1,gae_lambda=1,critic_contract='critic_v2',
        effective_stack_divisor=200,entropy_coef=.005,entropy_floor=.05,value_coef=1)
    engine.rng=torch.get_rng_state()
    assert all(torch.isfinite(v).all() for v in engine.model.state_dict().values())
    engine.cursor+=hands; engine.updates+=1; engine.transition_rows+=len(data)
    engine.transition_hands+=sum(any(r['actor']==t['hero'] for r in t['rows']) for t in traces)
    engine.save(directory/'checkpoint.pt')
    with (directory/'checkpoint.pt').open('r+b') as handle: os.fsync(handle.fileno())
    if fail_at=='checkpoint': raise RuntimeError('injected interruption after checkpoint')
    write_json(directory/'commit.json',dict(cursor=engine.cursor,hands=hands,rows=len(data),
        intent_sha=sha(directory/'intent.json'),raw_sha=sha(directory/'hands.jsonl'),
        checkpoint_sha=sha(directory/'checkpoint.pt'),wall_seconds=time.perf_counter()-started,stats=stats))
    return traces


def main():
    torch.set_num_threads(1)
    inputs=json.loads((BASE.parent/'v6-independent-critic-two-seed-geometric-20260908/input_contract.json').read_text())
    reports=[]
    for seed in ('1','3'):
        e=online.Engine(inputs['parents'][seed]['path'],inputs['anchors']['standard10']['path'],
            f'durable-batch-qualification-20260908-seed{seed}',.1)
        assert e.parent_sha==inputs['parents'][seed]['sha256']
        folder=BASE/f'seed{seed}'; initialize(folder,e)
        step(folder,e,32)
        resumed=restore(folder)
        # Separate explicitly duplicated test branch shares the clean prefix.
        comparison=BASE/f'seed{seed}_comparison'; comparison.mkdir()
        import shutil
        for name in ('initial.pt','manifest.json'): shutil.copy2(folder/name,comparison/name)
        shutil.copytree(folder/'update-000000',comparison/'update-000000')
        a=step(folder,e,32); b=step(comparison,resumed,32)
        assert a==b
        assert online.adapter.equal(e.model.state_dict(),resumed.model.state_dict())
        assert online.adapter.equal(e.optimizer.state_dict(),resumed.optimizer.state_dict())
        assert torch.equal(e.rng,resumed.rng)
        checked=restore(folder); assert checked.cursor==64
        reports.append(dict(seed=seed,live_executions=96,unique_decks=64,exact_resume=True))
    guard_executions=0
    for failure in ('intent','raw','checkpoint'):
        e=online.Engine(inputs['parents']['1']['path'],inputs['anchors']['standard10']['path'],
            f'durable-batch-crash-20260908-{failure}',.1)
        folder=BASE/f'crash_{failure}'; initialize(folder,e)
        try: step(folder,e,8,fail_at=failure)
        except RuntimeError: pass
        else: raise AssertionError('fault not injected')
        try: restore(folder)
        except AssertionError as error: assert 'unfinished transaction' in str(error)
        else: raise AssertionError('unfinished tail accepted')
        guard_executions+=0 if failure=='intent' else 8
    write_json(BASE/'result.json',dict(passed=True,reports=reports,guard_cases=3,
        physical_executions=192+guard_executions,unique_decks=128+guard_executions,
        completed_optimizer_updates=7,scope='CPU batched clean-boundary exact replay and fail-closed interrupted tails; copied prefix artifacts are not new executions; no strength evidence.'))
    print(json.dumps(dict(passed=True,reports=reports,guard_executions=guard_executions)))


if __name__=='__main__': main()
