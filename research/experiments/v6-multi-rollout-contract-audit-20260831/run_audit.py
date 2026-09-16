"""Fixed CPU-only real-worker contracts; no learned policy or production edits."""
from collections import Counter
from datetime import datetime, timezone
import argparse
import hashlib
import json
import math
import multiprocessing as mp
from multiprocessing import shared_memory
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
import traceback

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SEED, TARGET = 2026092200, 64
MODES = [('single', 1), ('multi', 1), ('multi', 4)]
REGIMES = ['passive_self', 'allin_self', 'fold_anchor']
sys.path.insert(0, str(ROOT))
from research.experiment_log import capture_code_provenance, sha256_file


def deny_network(*args, **kwargs): raise AssertionError('Network forbidden in rollout diagnostic')


def runtime():
    socket.socket.connect = deny_network
    socket.create_connection = deny_network
    sys.path.insert(0, str(ROOT/'scripts'))
    sys.path.insert(0, str(ROOT/'scripts/alpha_holdem'))
    import numpy as np
    import torch
    torch.set_num_threads(1)
    from alpha_holdem import train_v5 as trainer
    from alpha_holdem import environment_v6 as environment
    return np, trainer, environment


def canonical(value):
    if hasattr(value, 'tolist'): return canonical(value.tolist())
    if isinstance(value, (tuple, list)): return [canonical(v) for v in value]
    if isinstance(value, dict): return {str(k):canonical(v) for k, v in value.items()}
    if isinstance(value, float) and math.isnan(value): return None
    return value


def digest(value):
    return hashlib.sha256(json.dumps(canonical(value), separators=(',', ':'), sort_keys=True, allow_nan=False).encode()).hexdigest()


def write_rows(path, rows):
    with path.open('x') as output:
        for row in rows: output.write(json.dumps(canonical(row), allow_nan=False)+'\n')


def worker_entry(mode, slots, kwargs, events):
    _, trainer, environment = runtime()
    next_slot = [0]
    class ObservedEnvironment(environment.HUNLEnvironmentV6):
        def __init__(self, **values):
            super().__init__(**values)
            self.audit_slot = next_slot[0]
            next_slot[0] += 1
            self.audit_index = -1

        def reset_with_deck(self, deck):
            self.audit_index += 1
            self.audit_deck, self.audit_actions = list(deck), []
            return super().reset_with_deck(deck)

        def step(self, action):
            self.audit_actions.append(int(action))
            result = super().step(action)
            if result[2]:
                events.send(dict(slot=self.audit_slot, deal_index=self.audit_index,
                                 deck=self.audit_deck, actions=self.audit_actions,
                                 rewards_bb=[self.state.payoff(p) for p in [0, 1]],
                                 committed_bb=[self.chips_committed(p) for p in [0, 1]]))
            return result
    environment.HUNLEnvironment = ObservedEnvironment
    try:
        if mode == 'single': trainer.worker_process_v5(**kwargs)
        else: trainer.worker_process_v5_multi(envs_per_worker=slots, **kwargs)
    finally:
        events.send(None)
        events.close()


def choose(regime, legal):
    if regime == 'allin_self' and legal[8] > 0: return 8
    if regime == 'fold_anchor' and legal[0] > 0: return 0
    assert legal[1] > 0
    return 1


def replay_event(event, regime, requests, offset, trainer, environment, np):
    slot, deal_index = event['slot'], event['deal_index']
    assert event['deck'] == trainer.fixed_training_deck(SEED, slot, deal_index)
    env = environment.HUNLEnvironmentV6(starting_stack=200)
    obs = env.reset_with_deck(event['deck'])
    buffers = {0:[], 1:[]}
    hero = deal_index % 2
    selfplay = regime != 'fold_anchor'
    for action in event['actions']:
        player = obs['player']
        ci, ai = obs['card_info'].flatten(), obs['action_info'].flatten()
        ei = trainer.pack_position_extra(obs['extra_info'], player=player)
        mask = obs['legal_mask']
        request = requests[offset]
        offset += 1
        expected = np.concatenate([ci, ai, ei, mask])
        np.testing.assert_array_equal(expected, request['observation'])
        assert request['action'] == action == choose(regime, mask)
        assert request['model_id'] == (-1 if selfplay or player == hero else 0)
        if selfplay or player == hero:
            buffers[player].append((ci.copy(), ai.copy(), ei.copy(), mask.copy(), action, 0.0, 0.0))
        last_actor = player
        obs, reward, done = env.step(action)
    assert done
    assert event['rewards_bb'] == [env.state.payoff(p) for p in [0, 1]]
    chips = [env.chips_committed(p) for p in [0, 1]]
    assert event['committed_bb'] == chips
    rewards = {last_actor:reward, 1-last_actor:-reward}
    block, counted = [], False
    for player in [0, 1]:
        for i, row in enumerate(buffers[player]):
            ci, ai, ei, mask, action, logp, value = row
            final = i == len(buffers[player])-1
            marker = float(final and not counted)
            counted = counted or bool(marker)
            block.append((ci, ai, ei, mask, action, logp, rewards[player] if final else 0.0,
                          value, float(final), chips[player], chips[1-player], marker, float('nan'), float(player)))
    return block, offset


def run_case(mode, slots, regime, out):
    np, trainer, environment = runtime()
    out.mkdir()
    ctx = mp.get_context('spawn')
    memory = [shared_memory.SharedMemory(create=True, size=size) for size in
              [slots*trainer.OBS_SIZE*4, slots*trainer.RESULT_SIZE*4, slots*4, 4, slots*4]]
    obs = np.ndarray((slots, trainer.OBS_SIZE), dtype=np.float32, buffer=memory[0].buf)
    result = np.ndarray((slots, trainer.RESULT_SIZE), dtype=np.float32, buffer=memory[1].buf)
    status = np.ndarray((slots,), dtype=np.int32, buffer=memory[2].buf)
    assigned = np.ndarray((1,), dtype=np.int32, buffer=memory[3].buf)
    model_request = np.ndarray((slots,), dtype=np.int32, buffer=memory[4].buf)
    obs[:] = 0; result[:] = 0; status[:] = trainer.IDLE; assigned[:] = 0 if regime == 'fold_anchor' else -1
    model_request[:] = -1
    receive, send = ctx.Pipe(duplex=False)
    event_receive, event_send = ctx.Pipe(duplex=False)
    stop = ctx.Event()
    counter = ctx.Array('q', 2, lock=True)
    kwargs = dict(worker_id=0, obs_shm_name=memory[0].name, result_shm_name=memory[1].name,
                  status_shm_name=memory[2].name, assigned_opp_shm_name=memory[3].name,
                  request_model_shm_name=memory[4].name, transition_pipe=send, stop_event=stop,
                  epsilon_value=ctx.Value('d', 0), starting_stack=200, env_version='v6', worker_seed=SEED,
                  fixed_training_deal_stream=True, environment_hand_counters=counter)
    process = ctx.Process(target=worker_entry, args=(mode, slots, kwargs, event_send))
    packets, events, requests = [], [], [[] for _ in range(slots)]
    ended, event_ended = False, False
    started = time.monotonic()
    error, terminated = None, False
    process.start()
    send.close(); event_send.close()
    def drain():
        nonlocal ended, event_ended
        while not ended and receive.poll():
            value = receive.recv()
            if value is None: ended = True
            else: packets.append(value)
        while not event_ended and event_receive.poll():
            value = event_receive.recv()
            if value is None: event_ended = True
            else: events.append(value)
    try:
        while process.is_alive() or not (ended and event_ended):
            drain()
            if time.monotonic()-started > 60: raise TimeoutError('Fixed diagnostic case exceeded60seconds')
            if counter[0] >= TARGET: stop.set()
            if not stop.is_set():
                for slot in range(slots):
                    if status[slot] != trainer.WAITING: continue
                    observation = obs[slot].copy()
                    action = choose(regime, observation[-9:])
                    requests[slot].append(dict(slot=slot, observation=observation.tolist(),
                                               model_id=int(model_request[slot]), action=action))
                    result[slot] = [action, 0.0, 0.0]
                    status[slot] = trainer.READY
            time.sleep(.0005)
        process.join(1)
    except BaseException:
        error = traceback.format_exc()
    finally:
        stop.set()
        deadline = time.monotonic()+5
        while process.is_alive() and time.monotonic() < deadline:
            try: drain()
            except (EOFError, OSError): break
            process.join(.02)
        if process.is_alive():
            terminated = True
            process.terminate()  # only this newly-created diagnostic child
            process.join(2)
        try: drain()
        except (EOFError, OSError): pass
        receive.close(); event_receive.close()
        for item in memory:
            item.close(); item.unlink()
    write_rows(out/'worker_events.jsonl', events)
    write_rows(out/'transition_packets.jsonl', packets)
    write_rows(out/'inference_requests.jsonl', [row for slot in requests for row in slot])
    process_info = dict(pid=process.pid, exit_code=process.exitcode, terminated=terminated,
                        transition_sentinel=ended, event_sentinel=event_ended,
                        completed_hands=int(counter[0]), no_decision_hands=int(counter[1]),
                        wall_time_seconds=time.monotonic()-started, error=error)
    (out/'process.json').write_text(json.dumps(process_info, indent=2)+'\n')
    assert error is None and not terminated and process.exitcode == 0 and ended and event_ended, process_info
    assert counter[0] >= TARGET and len(events) == counter[0]
    offsets, expected_blocks, event_blocks = [0]*slots, [], []
    per_slot_deals = [[] for _ in range(slots)]
    for event in events:
        slot = event['slot']
        assert event['deal_index'] == len(per_slot_deals[slot])
        per_slot_deals[slot].append(event['deal_index'])
        block, offsets[slot] = replay_event(event, regime, requests[slot], offsets[slot], trainer, environment, np)
        if block: expected_blocks.append(digest(block))
        event_blocks.append(dict(slot=slot, deal_index=event['deal_index'], block_sha256=digest(block),
                                 training_rows=len(block), deck_sha256=digest(event['deck']), rewards_bb=event['rewards_bb']))
    block_size = {'passive_self':8, 'allin_self':2, 'fold_anchor':1}[regime]
    actual_blocks, transitions, league_hands = [], 0, 0
    for packet in packets:
        if isinstance(packet, list):
            assert len(packet) % block_size == 0, 'A whole hand was interleaved or cut across packets'
            transitions += len(packet)
            actual_blocks += [digest(packet[start:start+block_size]) for start in range(0, len(packet), block_size)]
        elif packet.get('type') == 'league_metrics': league_hands += sum(packet['hands'].values())
    assert Counter(actual_blocks) == Counter(expected_blocks), 'Serialized hand blocks differ from event replay'
    no_decision = sum(row['training_rows'] == 0 for row in event_blocks)
    assert no_decision == counter[1] and len(expected_blocks)+no_decision == counter[0]
    assert league_hands == counter[0]
    assert all(per_slot_deals), 'Every configured slot must actually run'
    if regime == 'fold_anchor': assert 0 < no_decision < counter[0]
    else: assert no_decision == 0
    write_rows(out/'replayed_hand_blocks.jsonl', event_blocks)
    summary = dict(status='PASS', mode=mode, slots=slots, regime=regime,
                   worker_validation_hands=int(counter[0]), reference_replay_hands=len(events),
                   no_decision_hands=no_decision, transition_bearing_hands=len(expected_blocks),
                   transitions=transitions, consumed_observation_checks=sum(offsets),
                   issued_requests=sum(len(row) for row in requests), per_slot_completed=[len(row) for row in per_slot_deals],
                   target_overshoot=int(counter[0])-TARGET, process=process_info,
                   raw_sha256={name:sha256_file(out/name) for name in ['worker_events.jsonl', 'transition_packets.jsonl', 'inference_requests.jsonl', 'replayed_hand_blocks.jsonl']})
    (out/'analysis.json').write_text(json.dumps(summary, indent=2)+'\n')
    return summary, event_blocks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--attempt', default='attempt01')
    args = parser.parse_args()
    if not re.fullmatch(r'attempt\d{2}', args.attempt): raise ValueError('Numbered diagnostic attempt required')
    out = BASE/args.attempt
    out.mkdir(exist_ok=False)
    def log(*items):
        subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'update', BASE.name,
                        *map(str, items)], cwd=ROOT, check=True)
    started = time.time()
    paths = [p.relative_to(ROOT).as_posix() for p in sorted((ROOT/'scripts/alpha_holdem').glob('*.py'))]
    paths += [f'scripts/deep_cfr/{name}.py' for name in ['__init__', 'game_state', 'hand_eval']]
    paths += ['research/experiment_log.py']+[p.relative_to(ROOT).as_posix() for p in BASE.iterdir() if p.suffix in {'.py', '.md'}]
    directory = out/'execution_code'
    directory.mkdir()
    capture_code_provenance(ROOT, directory, paths)
    copies = []
    for relative in paths:
        target = directory/'source_files'/relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT/relative, target)
        copies.append(dict(original=relative, copy=target.relative_to(ROOT).as_posix(), sha256=sha256_file(target)))
    (directory/'copy_manifest.json').write_text(json.dumps(copies, indent=2)+'\n')
    log('--command', f'python research/experiments/{BASE.name}/run_audit.py --attempt {args.attempt}',
        *[v for name in ['source_manifest.json', 'code.patch', 'copy_manifest.json'] for v in ['--artifact', directory/name]])
    cases, blocks, error = [], {}, None
    try:
        for mode, slots in MODES:
            for regime in REGIMES:
                key = f'{mode}{slots}_{regime}'
                result, event_blocks = run_case(mode, slots, regime, out/key)
                cases.append(result)
                blocks[mode, slots, regime] = event_blocks
                log('--artifact', out/key/'analysis.json', '--metric', f'{args.attempt}_completed_cases={len(cases)}')
        common = {}
        for regime in REGIMES:
            a, b = blocks['single', 1, regime], blocks['multi', 1, regime]
            n = min(len(a), len(b))
            assert n >= TARGET and a[:n] == b[:n]
            common[regime] = n
        for item in copies:
            assert all(sha256_file(ROOT/item[key]) == item['sha256'] for key in ['original', 'copy'])
        report = dict(status='PASS', decision='V6_FIXED_ACTION_WORKER_CONTRACT_VALIDATED', cases=cases,
                      common_single_multi1_hands=common, source_pairs_verified=len(copies),
                      worker_validation_hands=sum(r['worker_validation_hands'] for r in cases),
                      reference_replay_hands=sum(r['reference_replay_hands'] for r in cases),
                      additional_training_hands=0, additional_evaluation_hands=0, slumbot_hands=0,
                      full_gpu_batching_or_resume_validated=False)
    except BaseException:
        error = traceback.format_exc()
        report = dict(status='NEEDS_REVIEW', cases=cases, error=error,
                      additional_training_hands=0, additional_evaluation_hands=0, slumbot_hands=0)
    report.update(finished_at=datetime.now(timezone.utc).isoformat(), wall_time_seconds=time.time()-started)
    (out/'analysis.json').write_text(json.dumps(report, indent=2)+'\n')
    artifacts = [p for p in out.rglob('*') if p.is_file() and 'execution_code' not in p.parts]
    log(*[v for p in artifacts for v in ['--artifact', p]], '--note',
        f'{args.attempt} fixed real-worker diagnostic ended{report["status"]};no production source/GPU/model updates or benchmark hands. Preserve all case evidence.')
    print(json.dumps(report))
    if error: raise RuntimeError('Diagnostic needs review; no automatic retries')
    log('--metric', f'worker_validation_hands={report["worker_validation_hands"]}',
        '--metric', f'reference_replay_hands={report["reference_replay_hands"]}',
        '--metric', 'fixed_cases_passed=9', '--metric', f'source_pairs_verified={len(copies)}')
    subprocess.run([sys.executable, str(ROOT/'research/experiment_log.py'), 'finish', BASE.name,
                    '--status', 'COMPLETED', '--summary', f'Nine real-worker fixed-action cases passed;{report["worker_validation_hands"]}worker validation hands plus matching reference replays;0training/evaluation/Slumbot hands.',
                    '--conclusion', 'v6 single/M1 multi and M4 shared-memory observations,whole-hand blocks and physical/no-decision counters agree in fixed-action fixtures. This does not validate learned GPU inference,PPO scalability,assignment changes or multi-slot resume.',
                    '--decision', report['decision'], '--next-step', 'After learning evidence supports scaling, separately validate real multi-env inference/PPO throughput and per-slot resume;do not change the running source-KL pilot.',
                    '--count', 'new_training_hands=0', '--count', 'evaluation_hands=0', '--count', 'slumbot_hands=0'], cwd=ROOT, check=True)


if __name__ == '__main__': main()
