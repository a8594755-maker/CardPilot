"""Actual final-weight native/public inference parity on an immutable old corpus."""
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

from parity_contract import assert_parity, assert_coverage

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
ACTIVE = ROOT/'research/experiments/v6-physical1m-independent-confirmation-20260831'
READY = ROOT/'research/experiments/v6-source-live-readiness-20260831'
CORPUS = ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01'
MODEL_SHA = 'bc4f62257a474ad438cd574d4c59b28ea009060749f0fb86e3e97c46120d0172'
INPUT_SHAS = {
    'analysis.json': '23564045b6876f848a6fb3e92b5d32a231dbec556803bdf1cb3cbc180b70557f',
    'states.jsonl': 'da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d',
    'trajectories.jsonl': '9f130066b723a42a2745acdf277d1c4a6bae43e0f4a66ccf33ad78c92f46a6d9',
}
READY_REVIEW_SHA = 'd2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
READY_LOADER_SHA = '080e33f000c59d1af5cdd6a55511d9f3887e0475895449f1e3b7eb536af9d352'
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def protect():
    copies = read(ACTIVE/'execution_code/copy_manifest.json')
    assert len(copies) == 76
    for row in copies: assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original', 'copy'])
    for row in [*read(ACTIVE/'model_manifest.json').values(), *read(ACTIVE/'anchor_manifest.json')]:
        assert sha(row['path']) == row['sha256'] == sha(row['source'])
    assert sha(ACTIVE/'frozen/final.pt') == MODEL_SHA
    assert sha(READY/'reviewed_analysis.json') == READY_REVIEW_SHA
    assert sha(READY/'loader_check.json') == READY_LOADER_SHA
    for path, expected in read(READY/'loader_check.json')['runtime_sha256'].items(): assert sha(path) == expected
    for name, expected in INPUT_SHAS.items(): assert sha(CORPUS/name) == expected
    assert read(CORPUS/'analysis.json')['status'] == 'PASS'
    return copies


def main():
    import psutil
    if sys.argv[1:] or any((BASE/n).exists() for n in ['execution_code','analysis.json','parity.jsonl','frozen']):
        raise ValueError('No repeated corpus, restart or overwrite')
    active_copies = protect()
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
    started = time.time()
    report = dict(status='RUNNING', pid=psutil.Process().pid, started_at=datetime.now(timezone.utc).isoformat(),
                  new_training_hands=0, evaluation_hands=0, slumbot_hands=0,
                  states_checked=0, model_queries=0, replayed_validation_trajectories=0, new_unique_decks=0)
    write(BASE/'analysis.json', report)
    copies, runtime, connections = [], {}, []
    try:
        directory = BASE/'execution_code'
        directory.mkdir()
        paths = [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in {'.py','.md'}]
        paths += ['research/experiment_log.py']
        capture_code_provenance(ROOT, directory, paths)
        for relative in paths:
            target = directory/'source_files'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT/relative, target)
            copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
        write(directory/'copy_manifest.json', copies)
        log(*[v for n in ['source_manifest.json','code.patch','copy_manifest.json'] for v in ['--artifact',directory/n]])
        cmd = ['-m','pytest',str(BASE/'test_parity.py'),'-q',f'--junitxml={BASE/"tests.xml"}']
        log('--command',subprocess.list2cmdline(['python',*cmd]))
        subprocess.run([sys.executable,*cmd],cwd=ROOT,check=True)
        log('--artifact',BASE/'tests.xml')
        (BASE/'frozen').mkdir()
        model_path = BASE/'frozen/final.pt'
        shutil.copy2(ACTIVE/'frozen/final.pt',model_path)
        assert sha(model_path) == MODEL_SHA
        log('--artifact',model_path)
        snapshot = READY/'execution_code/source_files/scripts'
        sys.path.insert(0,str(snapshot))
        def deny(*a, **kw):
            connections.append('blocked_connection_attempt')
            raise AssertionError('Offline parity prohibits network')
        with patch.object(socket.socket,'connect',deny), patch.object(socket.socket,'connect_ex',deny), \
                patch.object(socket,'create_connection',deny), (BASE/'parity.jsonl').open('x') as output:
            import torch
            from alpha_holdem import play_slumbot_v6_journaled as client
            from alpha_holdem import v6_mirror_eval as mirror
            from alpha_holdem.execution_v6 import load_policy
            from alpha_holdem.policy_contract_v6 import observation, from_external, apply_incr
            from alpha_holdem.rules_v6 import ChipState
            from deep_cfr.hand_eval import card_to_str
            torch.set_num_threads(1)
            torch.set_num_interop_threads(1)
            model, payload, identity = load_policy(model_path,'cpu')
            assert identity == MODEL_SHA and not model.training and len(payload['model']) == 86
            assert all(torch.isfinite(v).all() for v in payload['model'].values())
            include_position = bool(getattr(model,'requires_position_feature',False)) or any(
                int(getattr(model,key,0)) > 0 for key in ('position_adapter_hidden','position_value_adapter_hidden'))
            runtime = client.runtime_hashes()
            expected_runtime = {row['original']:row['sha256'] for row in active_copies}
            for path, expected in runtime.items():
                relative = 'scripts/'+Path(path).relative_to(snapshot).as_posix()
                assert sha(path) == expected == expected_runtime[relative]
            for path, expected in read(READY/'loader_check.json')['runtime_sha256'].items():
                assert runtime[path] == expected
            write(BASE/'input_manifest.json',dict(model_sha256=MODEL_SHA,
                corpus={str(CORPUS/n):h for n,h in INPUT_SHAS.items()}, runtime_sha256=runtime,
                active_copy_manifest_sha256=sha(ACTIVE/'execution_code/copy_manifest.json'),
                readiness_review_sha256=READY_REVIEW_SHA, readiness_loader_sha256=READY_LOADER_SHA))
            log('--artifact',BASE/'input_manifest.json')
            traces = [json.loads(line) for line in (CORPUS/'trajectories.jsonl').read_text().splitlines()]
            states = [json.loads(line) for line in (CORPUS/'states.jsonl').read_text().splitlines()]
            assert len(traces) == 512 and len(states) == 4202
            assert [r['hand_index'] for r in traces] == list(range(512))
            assert [r['state_index'] for r in states] == list(range(4202))
            assert len({tuple(r['deck']) for r in traces}) == 512
            rng, strata, index = random.Random(20261003), Counter(), 0
            for trace in traces:
                state, prefix = ChipState.new(trace['deck']), ''
                assert trace['states'] == len(trace['actions'])
                for decision_index, action in enumerate(trace['actions']):
                    row = states[index]
                    assert row['hand_index'] == trace['hand_index'] and row['decision_index'] == decision_index
                    assert row['behavior_increment'] == action and row['action'] == prefix
                    assert row['seat'] == state.actor and row['street'] == state.street
                    assert row['hole_cards'] == [card_to_str(c) for c in state.holes[state.actor]]
                    assert row['board'] == [card_to_str(c) for c in state.board]
                    response = dict(action=prefix,hole_cards=row['hole_cards'],board=row['board'],client_pos=state.actor)
                    rebuilt = from_external(prefix,row['hole_cards'],row['board'],state.actor)
                    left, left_table = observation(state,include_position=include_position)
                    right, right_table = observation(rebuilt,include_position=include_position)
                    uniform = rng.random()
                    native = mirror.decide(model,state,uniform=uniform,device='cpu')
                    public = client.external_decision(model,response,uniform=uniform,device='cpu')
                    report['model_queries'] += 2
                    assert_parity(left,left_table,right,right_table,native,public)
                    strata[f'street{state.street}_seat{state.actor}'] += 1
                    output.write(json.dumps(dict(state_index=index,hand_index=trace['hand_index'],
                        decision_index=decision_index,street=state.street,seat=state.actor,uniform=uniform,
                        observation_equal=True,action_table_equal=True,decision_equal=True,
                        decision=public[1]),allow_nan=False)+'\n')
                    old = state.street
                    state = apply_incr(state,action)
                    prefix += action
                    if state.street > old and not state.terminal: prefix += '/'
                    index += 1
                    report['states_checked'] = index
                assert state.terminal and state.folded == trace['folded'] and list(state.board) == trace['terminal_board']
                report['replayed_validation_trajectories'] += 1
                if (trace['hand_index']+1)%64 == 0:
                    output.flush()
                    write(BASE/'analysis.json',report)
                    print(json.dumps({k:report[k] for k in ['states_checked','model_queries','replayed_validation_trajectories']}),flush=True)
            assert_coverage(strata)
            assert index == 4202 and report['model_queries'] == 8404
            assert not connections
            report['strata'] = dict(strata)
        protect()
        assert sha(model_path) == MODEL_SHA
        for row in copies: assert all(sha(ROOT/row[k]) == row['sha256'] for k in ['original','copy'])
        for path, expected in runtime.items(): assert sha(path) == expected
        report.update(status='PASS',decision='FROZEN_FINAL_OFFLINE_DEPLOYMENT_PARITY_PASS',
                      model_sha256=MODEL_SHA,network_connection_attempts=0,unchanged_active_source_pairs=76,
                      source_copy_pairs=len(copies),runtime_files=len(runtime),policy_modified=False,
                      strength_assessed=False,qualification_admitted=False,
                      parity_sha256=sha(BASE/'parity.jsonl'),corpus_outcomes_used=False,
                      limitation='Fixed old synthetic-corpus input/inference equality only; not live compatibility or poker strength.')
    except BaseException:
        report.update(status='FAILED',error=traceback.format_exc(),network_connection_attempts=len(connections))
        raise
    finally:
        report.update(finished_at=datetime.now(timezone.utc).isoformat(),wall_time_seconds=time.time()-started)
        write(BASE/'analysis.json',report)
        log('--artifact',BASE/'analysis.json',*[v for n in ['parity.jsonl','input_manifest.json'] if (BASE/n).exists() for v in ['--artifact',BASE/n]],
            '--metric',f"replayed_validation_trajectories={report['replayed_validation_trajectories']}",
            '--metric',f"states_checked={report['states_checked']}",'--metric',f"model_queries={report['model_queries']}",
            '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0')
    (BASE/'result_summary.md').write_text('# Frozen final offline deployment parity\n\n'
        'PASS on4202states from512preserved model-independent trajectories:8404model calls, exact native/public observations, probabilities and actions. '
        'All8street/seat strata covered. Zero new training/evaluation/Slumbot hands and zero network attempts.\n\n'
        'The live-audited runtime matches the ongoing confirmation source snapshot; all76active source/copy pairs and frozen weights are unchanged. '
        'This is not a strength result or an admission decision. Await the separately registered fixed confirmation.\n')
    log('--artifact',BASE/'result_summary.md')
    subprocess.run([sys.executable,str(ROOT/'research/experiment_log.py'),'finish',BASE.name,'--status','COMPLETED',
        '--summary','Exact final-weight native/public inference parity passed4202preserved synthetic states with8404model calls and zero new strength hands.',
        '--conclusion','Candidate-specific fixed-corpus deployment parity passed; active confirmation evidence unchanged and no live compatibility/strength claim.',
        '--decision',report['decision'],'--next-step','Finish the existing independent confirmation; only its passing gate can admit a separately registered live pilot.',
        '--count','new_training_hands=0','--count','evaluation_hands=0','--count','slumbot_hands=0'],cwd=ROOT,check=True)
    print(json.dumps(report))


if __name__ == '__main__': main()
