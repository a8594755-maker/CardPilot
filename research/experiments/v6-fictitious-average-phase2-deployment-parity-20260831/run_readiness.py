"""Offline fixed epoch08 deployment parity; never sends a network request."""
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-fictitious-average-phase2-20260831'
READY = ROOT/'research/experiments/v6-source-live-readiness-20260831'
CORPUS = ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01'
RUNTIME = READY/'execution_code/source_files/scripts'
MODEL_SHA = 'c60dfc881ff1b97245219b226eabb5f4c00c1a3d421f71681b63097f45bfa3ea'
FIT_REVIEW_SHA = '9f76cf2c0ae6109ee366f05839d98d0e578e5a7dce994aae9d58fe8a62674293'
READY_SHA = 'd2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
CORPUS_SHAS = dict(states='da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d',
                   trajectories='9f130066b723a42a2745acdf277d1c4a6bae43e0f4a66ccf33ad78c92f46a6d9')
sys.path.insert(0,str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file
from parity_contract import assert_parity, fit_gate


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path,value): atomic_json(Path(path),value)


def log(*args):
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'update',BASE.name,*map(str,args)],
                   cwd=ROOT,check=True,stdout=subprocess.DEVNULL)


def require_admission():
    if MODEL_SHA is None or FIT_REVIEW_SHA is None:
        raise ValueError('Parent epoch08 and review hashes not frozen; no model queries or output creation')
    assert sha(PARENT/'reviewed_analysis.json') == FIT_REVIEW_SHA
    review = read(PARENT/'reviewed_analysis.json')
    assert fit_gate(read(PARENT/'experiment.json'),review,MODEL_SHA)
    assert sha(PARENT/'latest.pt') == sha(PARENT/'checkpoints/epoch08.pt') == MODEL_SHA
    assert read(PARENT/'collection_audit.json')['status'] == 'PASS'
    assert sha(READY/'reviewed_analysis.json') == READY_SHA
    assert read(READY/'reviewed_analysis.json')['status'] == 'PASS'
    for name,digest in CORPUS_SHAS.items():
        assert sha(CORPUS/f'{name}.jsonl') == digest
    for row in read(PARENT/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy']) == sha(ROOT/row['original']) == row['sha256']
    for path,digest in read(READY/'loader_check.json')['runtime_sha256'].items():
        assert sha(path) == digest


def capture():
    directory = BASE/'execution_code'
    directory.mkdir()
    paths = ['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py','.md')]
    capture_code_provenance(ROOT,directory,paths)
    rows = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/relative,target)
        rows.append(dict(original=relative,copy=target.relative_to(ROOT).as_posix(),sha256=sha(target)))
    write(directory/'copy_manifest.json',rows)
    log(*[v for name in ('source_manifest.json','code.patch','copy_manifest.json') for v in ('--artifact',directory/name)])
    return rows


def verify(copies,inputs):
    require_admission()
    for row in copies:
        assert sha(ROOT/row['original']) == sha(ROOT/row['copy']) == row['sha256']
    for row in inputs['models'].values():
        assert sha(row['source']) == sha(row['path']) == row['sha256']
    for row in inputs['dependencies']:
        assert sha(row['path']) == row['sha256']


def parity(inputs):
    sys.path.insert(0, str(RUNTIME))
    import torch
    from alpha_holdem import play_slumbot_v6_journaled as client
    from alpha_holdem import v6_mirror_eval as mirror
    from alpha_holdem.execution_v6 import load_policy
    from alpha_holdem.rules_v6 import ChipState
    from alpha_holdem.policy_contract_v6 import observation, from_external, apply_incr
    from deep_cfr.hand_eval import card_to_str
    model, _, identity = load_policy(inputs['models']['student']['path'], 'cpu')
    assert identity == inputs['models']['student']['sha256']
    assert not getattr(model, 'requires_position_feature', False)
    runtime = client.runtime_hashes()
    parent_sources = {r['original']: r['sha256'] for r in read(PARENT/'execution_code/copy_manifest.json')}
    for path, expected in runtime.items():
        assert sha(path) == expected == parent_sources['scripts/'+Path(path).relative_to(RUNTIME).as_posix()]
    traces = [json.loads(line) for line in (CORPUS/'trajectories.jsonl').read_text().splitlines()]
    states = [json.loads(line) for line in (CORPUS/'states.jsonl').read_text().splitlines()]
    assert len(traces) == 512 and len(states) == 4202
    rng, counts, index, connections = random.Random(2026102101), Counter(), 0, []
    def deny(*args, **kwargs):
        connections.append(True)
        raise RuntimeError('Offline assessment prohibits network')
    with patch.object(socket.socket, 'connect', deny), patch.object(socket.socket, 'connect_ex', deny), \
         patch.object(socket, 'create_connection', deny), (BASE/'parity.jsonl').open('x') as handle:
        for hand_index, trace in enumerate(traces):
            assert trace['hand_index'] == hand_index
            state, prefix = ChipState.new(trace['deck']), ''
            for decision_index, action in enumerate(trace['actions']):
                row = states[index]
                assert row['state_index'] == index and row['hand_index'] == hand_index and row['decision_index'] == decision_index
                assert row['action'] == prefix and row['behavior_increment'] == action
                assert row['seat'] == state.actor and row['street'] == state.street
                assert row['hole_cards'] == [card_to_str(c) for c in state.holes[state.actor]]
                assert row['board'] == [card_to_str(c) for c in state.board]
                rebuilt = from_external(prefix, row['hole_cards'], row['board'], state.actor)
                response = dict(action=prefix, hole_cards=row['hole_cards'], board=row['board'], client_pos=state.actor)
                left, lt = observation(state)
                right, rt = observation(rebuilt)
                uniform = rng.random()
                native = mirror.decide(model, state, uniform=uniform, device='cpu')
                public = client.external_decision(model, response, uniform=uniform, device='cpu')
                assert_parity(left, lt, right, rt, native, public)
                counts[f'street{state.street}_seat{state.actor}'] += 1
                handle.write(json.dumps(dict(state_index=index, hand_index=hand_index, decision_index=decision_index,
                    observation_equal=True, action_table_equal=True, decision_equal=True, uniform=uniform, decision=public[1]), allow_nan=False)+'\n')
                old = state.street
                state = apply_incr(state, action)
                prefix += action
                if state.street > old and not state.terminal: prefix += '/'
                index += 1
            assert state.terminal and list(state.board) == trace['terminal_board'] and state.folded == trace['folded']
    assert index == 4202 and not connections
    assert set(counts) == {f'street{s}_seat{p}' for s in range(4) for p in range(2)} and all(v > 0 for v in counts.values())
    result = dict(status='PASS', model_sha256=identity, states_checked=index, model_queries=2*index,
        replayed_validation_trajectories=512, new_unique_hands=0, runtime_sha256=runtime,
        strata=dict(counts), parity_sha256=sha(BASE/'parity.jsonl'), network_connection_attempts=0)
    write(BASE/'parity_analysis.json', result)
    log('--artifact', BASE/'parity_analysis.json', '--artifact', BASE/'parity.jsonl', '--count', 'parity_model_queries=8404')
    return result


def main():
    require_admission()
    import psutil
    import torch
    if sys.argv[1:] or any((BASE/n).exists() for n in ('execution.json','execution_code','frozen','parity.jsonl')):
        raise ValueError('No repeated parity or overwrite')
    for process in psutil.process_iter(['name','cmdline']):
        if process.pid != psutil.Process().pid and (process.info['name'] or '').lower().startswith('python') and any(
            Path(a).name in ('train_v5.py','run_distillation.py','run_pilot.py','v6_mirror_eval.py','run_assessment.py','play_slumbot_v6_journaled.py')
            for a in process.info['cmdline'] or []):
            raise ValueError('Another poker workload is active')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    started = time.monotonic()
    execution = dict(status='PREPARING',pid=psutil.Process().pid,create_time=psutil.Process().create_time(),
                     started_at=datetime.now(timezone.utc).isoformat(),new_training_hands=0,evaluation_hands=0,slumbot_hands=0)
    write(BASE/'execution.json',execution)
    success=False
    try:
        copies=capture()
        (BASE/'frozen').mkdir()
        source,target=PARENT/'latest.pt',BASE/'frozen/student.pt'
        shutil.copy2(source,target)
        dependencies=[PARENT/'reviewed_analysis.json',PARENT/'collection_audit.json',READY/'reviewed_analysis.json',
                      READY/'loader_check.json',*[CORPUS/f'{name}.jsonl' for name in CORPUS_SHAS]]
        inputs=dict(models={'student':dict(path=str(target),source=str(source),sha256=sha(target))},
                    dependencies=[dict(path=str(p),sha256=sha(p)) for p in dependencies])
        write(BASE/'input_manifest.json',inputs)
        log('--artifact',BASE/'input_manifest.json','--artifact',target)
        cmd=['-m','pytest',str(BASE/'test_parity.py'),'-q',f'--junitxml={BASE/"prerun_tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'prerun_tests.xml')
        verify(copies,inputs)
        execution['status']='OFFLINE_PARITY'
        write(BASE/'execution.json',execution)
        result=parity(inputs)
        verify(copies,inputs)
        write(BASE/'completed_analysis.json',dict(status='COMPLETED_PENDING_REVIEW',decision='ADMIT_SEPARATE_FRESH20K',
            candidate_sha256=MODEL_SHA,parity=result,new_training_hands=0,evaluation_hands=0,slumbot_hands=0,
            qualification_hands=0,goal_achieved=False,internal_return_used_for_admission=False))
        success=True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        print(traceback.format_exc(),flush=True)
    finally:
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
            finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.monotonic()-started)
        write(BASE/'execution.json',execution)
        artifacts=[p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json','code.patch','source_manifest.json')]
        log(*[v for p in artifacts for v in ('--artifact',p)],'--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0')
        print(json.dumps(execution),flush=True)
    if not success: raise SystemExit(1)


if __name__=='__main__': main()
