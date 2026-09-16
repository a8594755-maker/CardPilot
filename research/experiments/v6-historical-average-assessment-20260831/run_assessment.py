"""Fixed epoch12 offline assessment, no network or training operations."""
from collections import Counter
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import random
import shutil
import socket
import subprocess
import sys
import time
import traceback
from unittest.mock import patch

from assessment_contract import parent_gate, assert_parity, paired_difference, estimate

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
PARENT = ROOT/'research/experiments/v6-historical-average-distillation-20260831'
TRAIN = ROOT/'research/experiments/v6-selfplay75-transfer-pilot-r4-20260831'
READY = ROOT/'research/experiments/v6-source-live-readiness-20260831'
CORPUS = ROOT/'research/experiments/v6-common-state-retention-diagnostic-20260831/attempt01'
RUNTIME = READY/'execution_code/source_files/scripts'
PAIRS, SEED = 4096, 2026101101
TOTAL_HANDS = 81920
CORPUS_SHAS = dict(states='da6225edf2bdb16f10005ff7f0a839bdbe6a752f6c032daf67eab0f8fa43570d',
                   trajectories='9f130066b723a42a2745acdf277d1c4a6bae43e0f4a66ccf33ad78c92f46a6d9')
sys.path.insert(0, str(ROOT))
from research.experiment_log import atomic_json, capture_code_provenance, sha256_file


def sha(path): return sha256_file(Path(path))
def read(path): return json.loads(Path(path).read_text())
def write(path, value): atomic_json(Path(path), value)


def log(*args):
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                    *map(str, args)], cwd=ROOT, check=True, stdout=subprocess.DEVNULL)


def record(cmd): log('--command', subprocess.list2cmdline(['python', *map(str, cmd)]))


def validate_parent():
    review = read(PARENT/'reviewed_analysis.json')
    if not parent_gate(read(PARENT/'experiment.json'), review):
        raise ValueError('Parent fixed epoch12 fit is not independently admitted')
    assert sha(PARENT/'latest.pt') == review['model_sha256'] == sha(PARENT/'checkpoints/epoch12.pt')
    assert read(READY/'reviewed_analysis.json')['status'] == 'PASS'
    assert sha(READY/'reviewed_analysis.json') == 'd2a3f75b626fd09c3b08aabc66686dd568e78d603f3d8273115f4020e3f73f61'
    for name, expected in CORPUS_SHAS.items(): assert sha(CORPUS/f'{name}.jsonl') == expected
    for row in read(PARENT/'execution_code/copy_manifest.json'):
        assert sha(ROOT/row['copy']) == sha(ROOT/row['original']) == row['sha256']
    return review


def freeze_inputs(review):
    (BASE/'frozen').mkdir()
    source = PARENT/'teachers/teacher00.pt'
    paths = [('student', PARENT/'latest.pt'), ('source', source)]
    paths += [(f'anchor{i}', TRAIN/'frozen'/f'anchor{i}.pt') for i in range(5)]
    result = dict(models={}, dependencies=[])
    for label, path in paths:
        target = BASE/'frozen'/f'{label}.pt'
        shutil.copy2(path, target)
        result['models'][label] = dict(source=str(path), path=str(target), sha256=sha(target))
    assert result['models']['student']['sha256'] == review['model_sha256']
    assert result['models']['source']['sha256'] == result['models']['anchor0']['sha256'] == '944f5f6625e29c2d2562cc457206aafcf840ef0c7edd6accbd372e1362dd57b2'
    for path in [PARENT/'reviewed_analysis.json', PARENT/'collection_audit.json', PARENT/'input_manifest.json',
                 READY/'reviewed_analysis.json', READY/'loader_check.json', *[CORPUS/f'{n}.jsonl' for n in CORPUS_SHAS]]:
        result['dependencies'].append(dict(path=str(path), sha256=sha(path)))
    write(BASE/'input_manifest.json', result)
    log('--artifact', BASE/'input_manifest.json', *[v for row in result['models'].values() for v in ('--artifact', row['path'])])
    return result


def capture():
    directory = BASE/'execution_code'
    directory.mkdir()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted(BASE.iterdir()) if p.suffix in ('.py', '.md')]
    paths += ['research/experiment_log.py']
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for path in paths:
        target = directory/'source_files'/path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/path, target)
        copies.append(dict(original=path, copy=target.relative_to(ROOT).as_posix(), sha256=sha(target)))
    write(directory/'copy_manifest.json', copies)
    log(*[v for name in ('source_manifest.json', 'code.patch', 'copy_manifest.json') for v in ('--artifact', directory/name)])
    return copies


def verify(copies, inputs):
    for row in copies:
        assert all(sha(ROOT/row[k]) == row['sha256'] for k in ('original', 'copy'))
    for row in inputs['models'].values():
        assert sha(row['source']) == sha(row['path']) == row['sha256']
    for row in inputs['dependencies']:
        assert sha(row['path']) == row['sha256']
    for path, expected in read(READY/'loader_check.json')['runtime_sha256'].items():
        assert sha(path) == expected


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
    rng, counts, index, connections = random.Random(2026101102), Counter(), 0, []
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


def eval_command(label, anchor):
    return [str(RUNTIME/'alpha_holdem/v6_mirror_eval.py'), '--candidate', str(BASE/'frozen'/f'{label}.pt'),
        '--anchor', str(BASE/'frozen'/f'anchor{anchor}.pt'), '--pairs', str(PAIRS), '--seed', str(SEED),
        '--out-dir', str(BASE/'evaluation'/f'{label}_a{anchor}'), '--device', 'cpu']


def evidence_and_statistics(inputs):
    decks, generator = [], random.Random(SEED)
    for _ in range(PAIRS):
        deck = list(range(52))
        generator.shuffle(deck)
        decks.append(deck)
    assert len({tuple(d) for d in decks}) == PAIRS
    rows, absolutes = {}, {}
    for label in ('source', 'student'):
        for anchor in range(5):
            directory = BASE/'evaluation'/f'{label}_a{anchor}'
            summary = read(directory/'summary.json')
            assert summary['status'] == 'COMPLETED' and summary['pairs'] == PAIRS and summary['seed'] == SEED
            assert summary['candidate_sha256'] == inputs['models'][label]['sha256']
            assert summary['anchor_sha256'] == inputs['models'][f'anchor{anchor}']['sha256']
            assert summary['evaluation_hands'] == 2*PAIRS and summary['pairs_sha256'] == sha(directory/'pairs.jsonl')
            data = [json.loads(line) for line in (directory/'pairs.jsonl').read_text().splitlines()]
            assert len(data) == PAIRS
            for index, row in enumerate(data):
                assert row['pair_index'] == index and row['deck'] == decks[index]
                assert len(row['rewards_bb']) == len(row['decisions']) == 2
                assert all(math.isfinite(x) and abs(x) <= 200 for x in row['rewards_bb'])
                assert all(type(d) is int and d > 0 for d in row['decisions'])
            result = estimate([sum(r['rewards_bb'])*50 for r in data])
            assert math.isclose(result['bb_per_100'], summary['bb_per_100'], abs_tol=1e-7)
            assert all(math.isclose(a, b, abs_tol=1e-7) for a, b in zip(result['ci95'], summary['ci95']))
            rows[label, anchor] = data
            absolutes[f'{label}_a{anchor}'] = result
    assert all(sum(r['rewards_bb']) == 0 for r in rows['source', 0])
    effects = {f'anchor{a}': paired_difference(rows['student', a], rows['source', a]) for a in range(5)}
    return dict(status='PASS', seed=SEED, pairs_per_cell=PAIRS, cells=10, evaluation_hands=TOTAL_HANDS,
                absolute_internal_results=absolutes, paired_student_minus_source=effects,
                source_self_match_exact_zero=True, deck_pairing_verified=True,
                internal_return_used_for_admission=False)


def main():
    import psutil
    import torch
    if sys.argv[1:] or any((BASE/n).exists() for n in ('execution.json', 'execution_code', 'frozen', 'evaluation')):
        raise ValueError('No restart/repeated assessment')
    review = validate_parent()
    for process in psutil.process_iter(['name', 'cmdline']):
        if process.pid != psutil.Process().pid and (process.info['name'] or '').lower().startswith('python') and any(
            Path(arg).name in ('run_distillation.py', 'train_v5.py', 'run_transfer.py', 'play_slumbot_v6_journaled.py', 'v6_mirror_eval.py') for arg in process.info['cmdline'] or []):
            raise ValueError('Another poker workload is active')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    psutil.Process().nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
    started = time.time()
    execution = dict(status='PREPARING', pid=psutil.Process().pid, create_time=psutil.Process().create_time(),
                     started_at=datetime.now(timezone.utc).isoformat(), children=[], evaluation_hands=0)
    write(BASE/'execution.json', execution)
    children, handles, success = [], [], False
    try:
        copies, inputs = capture(), freeze_inputs(review)
        cmd = ['-m', 'pytest', str(BASE/'test_assessment.py'), '-q', f'--junitxml={BASE/"prerun_tests.xml"}']
        record(cmd)
        subprocess.run([sys.executable, *cmd], cwd=ROOT, check=True)
        log('--artifact', BASE/'prerun_tests.xml')
        verify(copies, inputs)
        execution['status'] = 'PARITY'
        write(BASE/'execution.json', execution)
        parity_result = parity(inputs)
        verify(copies, inputs)
        execution['status'] = 'INTERNAL_EVALUATION'
        jobs = [(label, anchor, eval_command(label, anchor)) for label in ('source', 'student') for anchor in range(5)]
        for _, _, cmd in jobs: record(cmd)
        write(BASE/'evaluation_commands.json', [dict(label=l, anchor=a, command=[sys.executable, *c]) for l, a, c in jobs])
        log('--artifact', BASE/'evaluation_commands.json')
        pending = list(jobs)
        previous = -1
        while pending or any(child.poll() is None for child, _ in children):
            for child, info in children: info['exit_code'] = child.poll()
            if any(info['exit_code'] not in (None, 0) for _, info in children):
                raise RuntimeError('Internal evaluation failed; no replacements')
            while pending and sum(child.poll() is None for child, _ in children) < 6:
                label, anchor, cmd = pending.pop(0)
                output = (BASE/f'{label}_a{anchor}_stdout.log').open('x')
                handles.append(output)
                child = subprocess.Popen([sys.executable, *cmd], cwd=ROOT, stdout=output, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0)
                psutil.Process(child.pid).nice(psutil.BELOW_NORMAL_PRIORITY_CLASS if sys.platform == 'win32' else 5)
                info = dict(label=label, anchor=anchor, pid=child.pid, create_time=psutil.Process(child.pid).create_time(),
                            command=[sys.executable, *cmd], exit_code=None)
                children.append((child, info))
                execution['children'].append(info)
            count = sum(p.read_bytes().count(b'\n')*2 for p in (BASE/'evaluation').glob('*/pairs.jsonl')) if (BASE/'evaluation').exists() else 0
            execution['evaluation_hands'] = count
            write(BASE/'execution.json', execution)
            if count != previous:
                log('--count', f'evaluation_hands={count}')
                previous = count
            time.sleep(5)
        for child, info in children: info['exit_code'] = child.wait()
        assert len(children) == 10 and all(info['exit_code'] == 0 for _, info in children)
        analysis = evidence_and_statistics(inputs)
        verify(copies, inputs)
        write(BASE/'completed_analysis.json', dict(status='COMPLETED_PENDING_REVIEW',
              decision='ADMIT_SEPARATE_FRESH20K', internal=analysis, parity=parity_result,
              candidate_sha256=inputs['models']['student']['sha256'], new_training_hands=0,
              evaluation_hands=TOTAL_HANDS, slumbot_hands=0, goal_achieved=False))
        success = True
    except BaseException:
        (BASE/'failure.txt').write_text(traceback.format_exc())
        print(traceback.format_exc(), flush=True)
    finally:
        for child, info in children:
            if child.poll() is None: info['exit_code'] = child.wait()
        for handle in handles: handle.close()
        count = sum(p.read_bytes().count(b'\n')*2 for p in (BASE/'evaluation').glob('*/pairs.jsonl')) if (BASE/'evaluation').exists() else 0
        execution.update(status='COMPLETED_PENDING_REVIEW' if success else 'FAILED_PRESERVED',
                         evaluation_hands=count, finished_at=datetime.now(timezone.utc).isoformat(), wall_time_seconds=time.time()-started)
        write(BASE/'execution.json', execution)
        artifacts = [p for p in BASE.iterdir() if p.is_file() and p.name not in ('experiment.json', 'source_manifest.json', 'code.patch')]
        artifacts += list((BASE/'evaluation').glob('*/*.json'))+list((BASE/'evaluation').glob('*/*.jsonl'))
        log(*[v for p in artifacts for v in ('--artifact', p)], '--count', f'evaluation_hands={count}', '--count', 'new_training_hands=0', '--count', 'slumbot_hands=0')
        print(json.dumps(dict(status=execution['status'], evaluation_hands=count)), flush=True)
    if not success: raise SystemExit(1)


if __name__ == '__main__': main()
