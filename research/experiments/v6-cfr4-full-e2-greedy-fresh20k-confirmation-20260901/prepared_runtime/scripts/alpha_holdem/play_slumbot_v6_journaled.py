"""Strict CPU v6 execution with durable request/response/hand evidence.

No retries, heuristic actions, resume, overwrite or failed-hand replacement.
Offline readiness is necessary but not sufficient for a live qualification run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import random
import sys
import time
import os
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha_holdem.execution_v6 import external_decision, load_policy, sha256_file
from alpha_holdem.policy_contract_v6 import METADATA, from_external, apply_incr
from alpha_holdem.slumbot_terminal_v6 import validate_terminal, _observed, _tokens
from alpha_holdem.slumbot_transport import close_transport, TRANSPORT_MODE
from alpha_holdem.play_slumbot import new_hand, act
from alpha_holdem.slumbot_journal_v6 import Journal, JOURNAL_VERSION, append_line, digest, public_response, token_hash


def check_response(response, previous=None, increment=None):
    seat, holes, board = _observed(response)
    if response.get('winnings') is not None:
        result = validate_terminal(response, previous=previous, increment=increment)
        if previous is None and not (seat == 0 and response['action'] == 'f'):
            raise ValueError('New hand response invents client actions')
        return result
    state = from_external(response['action'], response['hole_cards'], response['board'], seat)
    if previous is None:
        if increment is not None or any(e.player == seat for e in state.history):
            raise ValueError('New hand response invents client actions')
    else:
        old_seat, old_holes, old_board = _observed(previous)
        if previous.get('winnings') is not None or old_seat != seat or old_holes != holes or board[:len(old_board)] != old_board:
            raise ValueError('Invalid response continuity')
        old_state = from_external(previous['action'], previous['hole_cards'], previous['board'], seat)
        apply_incr(old_state, increment)
        old = [t for t in _tokens(previous['action']) if t != '/']+[increment]
        current = [t for t in _tokens(response['action']) if t != '/']
        if current[:len(old)] != old or any(e.player == seat for e in state.history[len(old):]):
            raise ValueError('Response does not extend exactly the sent client action')
    return None


def runtime_hashes():
    directory = Path(__file__).resolve().parents[1]
    result = {}
    for module in list(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path:
            path = Path(path).resolve()
            if path.suffix == '.py' and path.is_relative_to(directory) and path.parent.name in ('alpha_holdem', 'deep_cfr'):
                result[str(path)] = sha256_file(path)
    result[str(Path(__file__).resolve())] = sha256_file(Path(__file__).resolve())
    return dict(sorted(result.items()))


def run_session(model, model_path, model_sha256, *, hands, seed, session_id, out_dir,
                new_hand_fn=None, act_fn=None, command=None, policy_mode='sample',
                decision_fn=None, execution_metadata=None, frozen_artifacts=None):
    if type(hands) is not int or hands <= 0 or type(seed) is not int:
        raise ValueError('Positive fixed hand target and integer seed required')
    if not isinstance(session_id, str) or not __import__('re').fullmatch(r'[A-Za-z0-9_-]{1,120}', session_id):
        raise ValueError('Explicit unique safe session ID required')
    if policy_mode not in ('sample', 'greedy'):
        raise ValueError('policy_mode must be sample or greedy')
    decision_fn = decision_fn or external_decision
    if sha256_file(model_path) != model_sha256: raise ValueError('Model identity mismatch before session')
    frozen_artifacts = {
        str(Path(path).resolve()): value for path, value in (frozen_artifacts or {}).items()
    }
    if any(sha256_file(Path(path)) != value for path, value in frozen_artifacts.items()):
        raise ValueError('Additional frozen artifact identity mismatch before session')
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=False)
    started = time.time()
    source_hashes = runtime_hashes()
    metadata = dict(**METADATA, journal_version=JOURNAL_VERSION, session_id=session_id,
                    model_sha256=model_sha256, policy_seed=seed, target_hands=hands,
                    policy_mode=policy_mode, policy_temperature=1.0 if policy_mode == 'sample' else 0.0, device='cpu',
                    http_transport=TRANSPORT_MODE, runtime_sha256=source_hashes,
                    frozen_artifact_sha256=dict(sorted(frozen_artifacts.items())),
                    command=command or [], pid=os.getpid(), started_at=datetime.now(timezone.utc).isoformat())
    if execution_metadata:
        overlap = set(metadata).intersection(execution_metadata)
        if overlap:
            raise ValueError(f'Execution metadata cannot replace core contract fields: {sorted(overlap)}')
        metadata.update(execution_metadata)
    rng, token, attempted, completed, cumulative, requests = random.Random(seed), None, 0, 0, 0, 0
    journal, raw = None, None
    status, phase, error_type, frozen = 'FAILED', 'open_evidence', None, False
    initial_token_hash = None
    new_hand_fn, act_fn = new_hand_fn or new_hand, act_fn or act
    try:
        journal = Journal(out/'journal.jsonl')
        raw = (out/'hands.jsonl').open('xb', buffering=0)
        journal.append('session_start', **metadata)
        for index in range(1, hands+1):
            attempted = index
            phase = 'hand_start'
            journal.append('hand_start', hand=index)
            previous, increment, decision, response = None, None, None, None
            decisions = []
            while True:
                phase = 'request_intent'
                request_id = requests+1
                intent = journal.append('request_intent', hand=index, request_id=request_id,
                    method='new_hand' if previous is None else 'act', token_in_sha256=token_hash(token),
                    previous_response=previous, increment=increment, decision=decision)
                requests = request_id
                phase = 'request_call'
                try:
                    response = new_hand_fn(token) if previous is None else act_fn(token, increment)
                except BaseException as exc:
                    journal.append('request_error', hand=index, request_id=request_id, error_type=type(exc).__name__)
                    raise
                phase = 'response_evidence'
                returned = response.get('token') if isinstance(response, dict) else None
                token_present = isinstance(response, dict) and 'token' in response
                token_valid = (not token_present) or (isinstance(returned, str) and bool(returned))
                effective = returned if token_present and token_valid else token
                public = public_response(response, (token, returned))
                journal.append('request_response', hand=index, request_id=request_id,
                    token_present=token_present, token_valid=token_valid,
                    token_returned_sha256=token_hash(returned) if token_present and token_valid else None,
                    token_effective_sha256=token_hash(effective), response=public)
                phase = 'response_validation'
                if not token_valid or effective is None: raise ValueError('Missing or invalid session token')
                token = effective
                if initial_token_hash is None: initial_token_hash = token_hash(token)
                terminal = check_response(public, previous, increment)
                if terminal is not None:
                    if type(public.get('session_num_hands')) is not int or public['session_num_hands'] != index:
                        raise ValueError('Server hand counter is not this fresh contiguous session')
                    if type(public.get('session_total')) is not int or public['session_total'] != cumulative+public['winnings']:
                        raise ValueError('Server session total mismatch')
                    record = dict(attempted_hand=index, successful_hand=index, session_id=session_id,
                        model_sha256=model_sha256, policy_seed=seed, policy_mode=policy_mode,
                        policy_temperature=1.0 if policy_mode == 'sample' else 0.0,
                        policy_contract=METADATA['policy_contract'], strict_policy_execution=True,
                        http_transport=TRANSPORT_MODE, session_token_sha256=initial_token_hash,
                        final_token_sha256=token_hash(token), winnings_chips=public['winnings'],
                        winnings_bb=public['winnings']/100, cumulative_chips=cumulative+public['winnings'],
                        cumulative_bb=(cumulative+public['winnings'])/100,
                        terminal_response=public, terminal_validation=terminal, decisions=decisions,
                        terminal_request_id=request_id, terminal_response_event_sha256=journal.last_hash)
                    phase = 'hand_commit'
                    commit = journal.append('hand_commit', hand=index, record_sha256=digest(record))
                    phase = 'raw_hand_write'
                    append_line(raw, {**record, 'commit_event_sha256':commit['event_sha256']})
                    cumulative += public['winnings']
                    completed += 1
                    break
                phase = 'policy_decision'
                increment, info = decision_fn(
                    model, public, uniform=rng.random(), device='cpu',
                    policy_mode=policy_mode,
                )
                decision = dict(response=public, **info)
                decisions.append(decision)
                previous = public
        phase = 'frozen_identity'
        frozen = (sha256_file(model_path) == model_sha256 and
                  all(sha256_file(p) == v for p, v in source_hashes.items()) and
                  all(sha256_file(Path(p)) == v for p, v in frozen_artifacts.items()))
        if not frozen: raise RuntimeError('Frozen model or runtime changed')
        status = 'COMPLETED'
    except BaseException as exc:
        error_type = type(exc).__name__  # never emit exception text containing credentials
    finally:
        try: close_transport()
        except BaseException as exc:
            status, phase, error_type = 'FAILED', 'close_transport', type(exc).__name__
        if raw is not None: raw.close()
        ended = False
        if journal is not None:
            try:
                journal.append('session_end', status=status, successful_hands=completed,
                    attempted_hands=attempted, request_count=requests, cumulative_chips=cumulative,
                    frozen_identity_verified=frozen, error_type=error_type, phase=phase)
                ended = True
            except BaseException as exc:
                status, phase, error_type = 'FAILED', 'closing_evidence', type(exc).__name__
            finally: journal.close()
        summary = dict(**metadata, status=status, successful_hands=completed, attempted_hands=attempted,
            request_count=requests, cumulative_chips=cumulative, bb_per_100=cumulative/completed if completed else None,
            frozen_identity_verified=frozen, error_type=error_type, phase=phase,
            closing_event_persisted=ended, journal_final_sha256=journal.last_hash if journal else None,
            journal_sha256=sha256_file(out/'journal.jsonl') if (out/'journal.jsonl').exists() else None,
            hands_sha256=sha256_file(out/'hands.jsonl') if (out/'hands.jsonl').exists() else None,
            wall_time_seconds=time.time()-started, finished_at=datetime.now(timezone.utc).isoformat())
        with (out/'summary.json').open('xb', buffering=0) as handle: append_line(handle, summary)
    if status != 'COMPLETED':
        raise RuntimeError('Journaled session failed; preserve and inspect evidence') from None
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model', required=True)
    parser.add_argument('--hands', type=int, required=True)
    parser.add_argument('--seed', type=int, required=True)
    parser.add_argument('--session-id', required=True)
    parser.add_argument('--out-dir', required=True)
    parser.add_argument('--device', choices=['cpu'], default='cpu')
    parser.add_argument('--policy-mode', choices=['sample', 'greedy'], default='sample')
    parser.add_argument('--observation-bridge', choices=['none', 'legacy-v4', 'dual-contract'], default='none')
    parser.add_argument('--base-model')
    args = parser.parse_args()
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    frozen_artifacts = None
    if args.observation_bridge == 'legacy-v4':
        if args.base_model:
            parser.error('--base-model is only valid for --observation-bridge dual-contract')
        from alpha_holdem.legacy_observation_bridge_v6 import (
            BRIDGE_CONTRACT, external_decision as bridge_external_decision,
            load_policy as load_bridge_policy,
        )
        model = load_bridge_policy(args.model, 'cpu')
        model_hash = model.sha256
        decision_fn = bridge_external_decision
        execution_metadata = dict(
            observation_bridge_contract=BRIDGE_CONTRACT,
            model_obs_version='v4',
        )
    elif args.observation_bridge == 'dual-contract':
        if not args.base_model:
            parser.error('--observation-bridge dual-contract requires --base-model')
        from alpha_holdem.dual_contract_execution_v6 import (
            DUAL_CONTRACT, external_decision as dual_external_decision,
            load_policy as load_dual_policy,
        )
        model = load_dual_policy(args.model, args.base_model, 'cpu')
        model_hash = model.sha256
        decision_fn = dual_external_decision
        frozen_artifacts = {str(model.base_path): model.base_sha256}
        execution_metadata = dict(
            observation_bridge_contract=DUAL_CONTRACT,
            model_obs_version='legacy-v4+native-v6',
            base_checkpoint_sha256=model.base_sha256,
            source_residual_sha256=model.source_residual_sha256,
        )
    else:
        if args.base_model:
            parser.error('--base-model is only valid for --observation-bridge dual-contract')
        model, _, model_hash = load_policy(args.model, 'cpu')
        decision_fn = external_decision
        execution_metadata = None
    summary = run_session(model, args.model, model_hash, hands=args.hands, seed=args.seed,
        session_id=args.session_id, out_dir=args.out_dir, command=[sys.executable, *sys.argv],
        policy_mode=args.policy_mode, decision_fn=decision_fn,
        execution_metadata=execution_metadata, frozen_artifacts=frozen_artifacts)
    print(__import__('json').dumps(summary))


if __name__ == '__main__': main()
