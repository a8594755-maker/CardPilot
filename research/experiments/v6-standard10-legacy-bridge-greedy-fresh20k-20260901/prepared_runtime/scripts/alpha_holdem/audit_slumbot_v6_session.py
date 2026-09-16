"""Read-only semantic audit of journaled v6 sessions, including failed prefixes.

Hash chains detect accidental edits, not a malicious actor who can replace all
evidence. Model replay and protocol semantics provide additional checks. Distinct
token chains do not by themselves prove independence of the server's RNG.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
import random
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha_holdem.execution_v6 import external_decision, sha256_file, load_policy
from alpha_holdem.policy_contract_v6 import METADATA, from_external, action_table
from alpha_holdem.play_slumbot_v6_journaled import check_response
from alpha_holdem.slumbot_journal_v6 import JOURNAL_VERSION


def need(condition, message):
    if not condition: raise ValueError(message)


def hash_object(value):
    data = json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(data).hexdigest()


def read_lines(path):
    if not path.exists(): return [], True
    data = path.read_bytes()
    partial = bool(data and not data.endswith(b'\n'))
    pieces = data.split(b'\n')[:-1]
    def unique(items):
        result = {}
        for key, value in items:
            need(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def bad_constant(value): raise ValueError('Nonfinite JSON value')
    return [json.loads(p, object_pairs_hook=unique, parse_constant=bad_constant) for p in pieces], partial


def validate_decision(row, response, rng, model, policy_mode, decision_fn=external_decision):
    need(isinstance(row, dict) and row.get('response') == response, 'Decision context mismatch')
    need(row.get('uniform') == rng.random(), 'Policy RNG stream mismatch')
    temperature = 1.0 if policy_mode == 'sample' else 0.0
    need(row.get('policy_mode') == policy_mode and row.get('temperature') == temperature and
         row.get('policy_contract') == METADATA['policy_contract'], 'Policy execution mode mismatch')
    state = from_external(response['action'], response['hole_cards'], response['board'], response['client_pos'])
    mask, table = action_table(state)
    need(row.get('legal_mask') == mask.tolist() and row.get('action_table') == table, 'Physical action contract mismatch')
    probs, slot, uniform = row.get('behavior_probs'), row.get('selected_action_slot'), row['uniform']
    need(isinstance(probs, list) and len(probs) == 9 and all(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1 for p in probs), 'Invalid behavior probabilities')
    need(abs(math.fsum(probs)-1) < 1e-12 and all(p == 0 for p, legal in zip(probs, mask) if not legal), 'Invalid legal probability mass')
    need(type(slot) is int and slot in range(9) and table[slot] is not None, 'Illegal selected slot')
    if policy_mode == 'sample':
        cumulative = 0
        selected = None
        for index, p in enumerate(probs):
            cumulative += p
            if p and uniform < cumulative:
                selected = index
                break
        if selected is None: selected = max(i for i, p in enumerate(probs) if p)
    else:
        model_probs = row.get('model_probs')
        need(isinstance(model_probs, list) and len(model_probs) == 9 and
             all(type(p) in (int, float) and math.isfinite(p) and 0 <= p <= 1 for p in model_probs),
             'Invalid greedy model probabilities')
        need(abs(math.fsum(model_probs)-1) < 1e-12 and
             all(p == 0 for p, legal in zip(model_probs, mask) if not legal),
             'Invalid greedy model probability mass')
        selected = max((index for index in range(9) if mask[index]), key=lambda index: model_probs[index])
        need(probs == [float(index == selected) for index in range(9)] and
             row.get('greedy_action_slot') == selected,
             'Greedy behavior is not deterministic legal argmax')
    need(selected == slot and row.get('direct_increment') == table[slot] and
         row.get('behavior_action_probability') == probs[slot], 'Sampled action mismatch')
    if model is not None:
        _, info = decision_fn(model, response, uniform=uniform, device='cpu', policy_mode=policy_mode)
        need(all(row.get(k) == v for k, v in info.items()), 'Frozen model decision replay mismatch')


def audit_session(directory, *, model=None, expected_model_sha256=None,
                  decision_fn=external_decision, expected_observation_bridge=None):
    directory = Path(directory)
    events, partial_journal = read_lines(directory/'journal.jsonl')
    hands, partial_hands = read_lines(directory/'hands.jsonl')
    if not events:
        return dict(status='INCOMPLETE', directory=str(directory), successful_hands=0, reason='No complete start event')
    head = '0'*64
    for index, event in enumerate(events, 1):
        need(type(event.get('sequence')) is int and event['sequence'] == index and event.get('previous_sha256') == head, 'Broken journal order/link')
        body = {k:v for k, v in event.items() if k != 'event_sha256'}
        need(hash_object(body) == event.get('event_sha256'), 'Journal event hash mismatch')
        head = event['event_sha256']
    start = events[0]
    need(start['event'] == 'session_start', 'Missing session start')
    need(all(start.get(k) == v for k, v in METADATA.items()) and start.get('journal_version') == JOURNAL_VERSION, 'Contract/version mismatch')
    need(start.get('observation_bridge_contract') == expected_observation_bridge,
         'Observation bridge contract mismatch')
    need(start.get('policy_mode') in ('sample', 'greedy') and
         start.get('policy_temperature') == (1.0 if start.get('policy_mode') == 'sample' else 0.0) and
         start.get('device') == 'cpu', 'Wrong frozen execution')
    need(type(start.get('target_hands')) is int and start['target_hands'] > 0 and type(start.get('policy_seed')) is int, 'Invalid target/seed')
    need(isinstance(start.get('session_id'), str) and re.fullmatch(r'[A-Za-z0-9_-]{1,120}', start['session_id']), 'Invalid session ID')
    need(isinstance(start.get('command'), list) and bool(start['command']), 'Missing exact command')
    need(isinstance(start.get('runtime_sha256'), dict) and bool(start['runtime_sha256']), 'Missing runtime identity')
    if expected_model_sha256 is not None: need(start['model_sha256'] == expected_model_sha256, 'Wrong frozen checkpoint')
    rng = random.Random(start['policy_seed'])
    token, first_token, tokens = None, None, set()
    requests, attempts, commits, verified, total, decision_count = 0, 0, 0, 0, 0, 0
    active, pending, last_response, terminal, ended = False, None, None, None, None
    decisions, problems, last_response_hash = [], [], None
    for event in events[1:]:
        kind = event['event']
        need(ended is None, 'Event after session close')
        if kind == 'hand_start':
            need(not active and pending is None and commits == verified and not problems, 'Hand started before prior evidence completed')
            need(type(event.get('hand')) is int and event['hand'] == commits+1 <= start['target_hands'], 'Wrong hand-attempt prefix')
            attempts, active, last_response, terminal, decisions = event['hand'], True, None, None, []
        elif kind == 'request_intent':
            need(active and pending is None and terminal is None and not problems, 'Invalid request ordering')
            need(event.get('hand') == attempts and type(event.get('request_id')) is int and event['request_id'] == requests+1, 'Request counter mismatch')
            need(event.get('token_in_sha256') == token and event.get('previous_response') == last_response, 'Request context/token mismatch')
            expected_method = 'new_hand' if last_response is None else 'act'
            need(event.get('method') == expected_method, 'Unexpected request method')
            if expected_method == 'new_hand':
                need(event.get('decision') is None and event.get('increment') is None, 'New-hand request contains an action')
            else:
                validate_decision(event.get('decision'), last_response, rng, model, start['policy_mode'], decision_fn)
                decision_count += 1
                need(event.get('increment') == event['decision']['direct_increment'], 'Sent increment mismatch')
                decisions.append(event['decision'])
            requests, pending = event['request_id'], event
        elif kind in ('request_response', 'request_error'):
            need(pending is not None and not pending.get('_error') and event.get('hand') == attempts and event.get('request_id') == requests, 'Response has no matching request')
            if kind == 'request_error':
                pending = {**pending, '_error':True}
                problems.append(dict(hand=attempts, request_id=requests, kind='request_error'))
                continue
            need(type(event.get('token_present')) is bool and type(event.get('token_valid')) is bool, 'Invalid token flags')
            returned = event.get('token_returned_sha256')
            if event['token_present'] and event['token_valid']:
                need(isinstance(returned, str) and re.fullmatch('[0-9a-f]{64}', returned), 'Invalid returned token hash')
                token = returned
            else: need(returned is None, 'Unexpected returned token hash')
            need(event.get('token_effective_sha256') == token, 'Broken token transition')
            if token is not None:
                tokens.add(token)
                if first_token is None: first_token = token
            last_response = event.get('response')
            last_response_hash = event['event_sha256']
            try:
                need(event['token_valid'] and token is not None, 'Invalid token')
                terminal = check_response(last_response, pending['previous_response'], pending['increment'])
                if terminal is not None:
                    need(type(last_response.get('session_num_hands')) is int and last_response['session_num_hands'] == attempts, 'Server hand counter mismatch')
                    need(type(last_response.get('session_total')) is int and last_response['session_total'] == total+last_response['winnings'], 'Server total mismatch')
            except (ValueError, TypeError, KeyError):
                terminal = None
                problems.append(dict(hand=attempts, request_id=requests, kind='invalid_response'))
            pending = None
        elif kind == 'hand_commit':
            need(active and pending is None and terminal is not None and not problems and event.get('hand') == attempts, 'Commit without valid terminal evidence')
            record = dict(attempted_hand=attempts, successful_hand=attempts, session_id=start['session_id'],
                model_sha256=start['model_sha256'], policy_seed=start['policy_seed'],
                policy_mode=start['policy_mode'], policy_temperature=start['policy_temperature'],
                policy_contract=METADATA['policy_contract'], strict_policy_execution=True, http_transport=start['http_transport'],
                session_token_sha256=first_token, final_token_sha256=token, winnings_chips=last_response['winnings'],
                winnings_bb=last_response['winnings']/100, cumulative_chips=total+last_response['winnings'],
                cumulative_bb=(total+last_response['winnings'])/100, terminal_response=last_response,
                terminal_validation=terminal, decisions=decisions, terminal_request_id=requests,
                terminal_response_event_sha256=last_response_hash)
            need(hash_object(record) == event.get('record_sha256'), 'Hand commit digest mismatch')
            commits += 1
            if len(hands) >= commits:
                need(hands[commits-1] == {**record, 'commit_event_sha256':event['event_sha256']}, 'Raw hand differs from journal commit')
                verified += 1
                total += last_response['winnings']
            active, terminal = False, None
        elif kind == 'session_end':
            need(event.get('status') in ('COMPLETED', 'FAILED'), 'Invalid closing status')
            need(event.get('successful_hands') == verified and event.get('cumulative_chips') == total and
                 event.get('attempted_hands') == attempts and event.get('request_count') == requests, 'Closing accounting mismatch')
            if event['status'] == 'COMPLETED':
                need(not active and pending is None and not problems and verified == commits == start['target_hands'] and
                     event.get('frozen_identity_verified') is True and event.get('error_type') is None, 'Invalid completed session')
            ended = event
        else: raise ValueError('Unknown journal event')
    need(len(hands) == verified, 'Uncommitted raw hands')
    summary_path = directory/'summary.json'
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else None
    complete = bool(ended and ended['status'] == 'COMPLETED' and summary is not None and not partial_journal and not partial_hands)
    if summary is not None:
        for key, value in start.items():
            if key not in ('event', 'sequence', 'previous_sha256', 'event_sha256', 'timestamp'):
                need(summary.get(key) == value, 'Summary metadata mismatch')
        need(summary.get('successful_hands') == verified and summary.get('attempted_hands') == attempts and
             summary.get('request_count') == requests and summary.get('cumulative_chips') == total, 'Summary accounting mismatch')
        need(summary.get('bb_per_100') == (total/verified if verified else None), 'Summary score mismatch')
        need(summary.get('journal_final_sha256') == head and summary.get('journal_sha256') == sha256_file(directory/'journal.jsonl') and
             summary.get('hands_sha256') == sha256_file(directory/'hands.jsonl'), 'Summary artifact hash mismatch')
        if summary.get('status') == 'COMPLETED':
            need(complete and summary.get('closing_event_persisted') is True and summary.get('frozen_identity_verified') is True, 'Summary claims incomplete success')
        else: complete = False
    if complete:
        need(all(sha256_file(p) == h for p, h in start['runtime_sha256'].items()), 'Current runtime differs from frozen evidence')
    return dict(status='PASS' if complete else 'INCOMPLETE', directory=str(directory), session_id=start['session_id'],
                model_sha256=start['model_sha256'], policy_seed=start['policy_seed'], successful_hands=verified,
                target_hands=start['target_hands'], attempted_hands=attempts, cumulative_chips=total,
                request_count=requests, decision_replays=decision_count if model is not None else 0,
                policy_draws_verified=decision_count,
                token_sha256=sorted(tokens), initial_token_sha256=first_token, protocol_failures=problems,
                pending_request_id=pending['request_id'] if pending else None,
                committed_without_raw=commits-verified, partial_journal=partial_journal, partial_hands=partial_hands,
                source_files_verified=len(start['runtime_sha256']) if complete else 0,
                journal_sha256=sha256_file(directory/'journal.jsonl'), hands_sha256=sha256_file(directory/'hands.jsonl') if (directory/'hands.jsonl').exists() else None)


def audit_sessions(directories, *, model=None, expected_model_sha256=None,
                   decision_fn=external_decision, expected_observation_bridge=None):
    results = [audit_session(p, model=model, expected_model_sha256=expected_model_sha256,
               decision_fn=decision_fn, expected_observation_bridge=expected_observation_bridge) for p in directories]
    need(len(results) >= 2 and all(r['status'] == 'PASS' for r in results), 'Need at least two complete valid sessions')
    for key in ['session_id', 'policy_seed', 'journal_sha256']:
        need(len({r[key] for r in results}) == len(results), 'Repeated independent session identity/seed/evidence')
    need(len({r['model_sha256'] for r in results}) == 1, 'Mixed frozen checkpoints')
    seen = set()
    for result in results:
        need(result['token_sha256'] and not seen.intersection(result['token_sha256']), 'Overlapping session token chains')
        seen.update(result['token_sha256'])
    return dict(status='PASS', sessions=len(results), successful_hands=sum(r['successful_hands'] for r in results),
                model_sha256=results[0]['model_sha256'], token_chains_disjoint=True,
                server_rng_independence_proven=False, results=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session-dir', action='append', required=True)
    parser.add_argument('--model')
    parser.add_argument('--observation-bridge', choices=['none', 'legacy-v4'], default='none')
    args = parser.parse_args()
    model, expected = None, None
    decision_fn, expected_bridge = external_decision, None
    if args.model:
        import torch
        torch.set_num_threads(1)
        torch.set_num_interop_threads(1)
        if args.observation_bridge == 'legacy-v4':
            from alpha_holdem.legacy_observation_bridge_v6 import (
                BRIDGE_CONTRACT, external_decision as bridge_external_decision,
                load_policy as load_bridge_policy,
            )
            model = load_bridge_policy(args.model, 'cpu')
            expected, decision_fn, expected_bridge = model.sha256, bridge_external_decision, BRIDGE_CONTRACT
        else:
            model, _, expected = load_policy(args.model, 'cpu')
    elif args.observation_bridge != 'none':
        raise ValueError('--observation-bridge requires --model for replay')
    result = (audit_sessions(args.session_dir, model=model, expected_model_sha256=expected,
              decision_fn=decision_fn, expected_observation_bridge=expected_bridge) if len(args.session_dir) > 1 else
              audit_session(args.session_dir[0], model=model, expected_model_sha256=expected,
              decision_fn=decision_fn, expected_observation_bridge=expected_bridge))
    print(json.dumps(result))
    if result['status'] != 'PASS': raise SystemExit(1)


if __name__ == '__main__': main()
