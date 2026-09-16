"""Strict sampled v6 deployment; no heuristics, retries, or illegal fallbacks.

This new entry point uses the shared physical/observation contract. Validation
must finish before any external benchmark is preregistered/launched.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import sys
import time
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha_holdem.execution_v6 import external_decision, load_policy, sha256_file
from alpha_holdem.policy_contract_v6 import METADATA
from alpha_holdem.slumbot_transport import close_transport, TRANSPORT_MODE
from alpha_holdem.play_slumbot import new_hand, act


def play_one(model, token, rng, *, device='cpu', new_hand_fn=new_hand, act_fn=act):
    response = new_hand_fn(token)
    if not response.get('token'):
        raise ValueError('Missing session token')
    token = response['token']
    initial_token_hash = hashlib.sha256(token.encode()).hexdigest()
    decisions = []
    while response.get('winnings') is None:
        incr, info = external_decision(model, response, uniform=rng.random(), device=device)
        decisions.append(dict(action=response['action'], hole_cards=response['hole_cards'],
                              board=response.get('board', []), client_pos=response['client_pos'], **info))
        response = act_fn(token, incr)
        token = response.get('token', token)
    if type(response['winnings']) is not int:
        raise ValueError('Terminal reward must be integer chips')
    terminal = {key: value for key, value in response.items() if key != 'token'}
    return token, dict(winnings_chips=response['winnings'], terminal_response=terminal,
                       decisions=decisions, session_token_sha256=initial_token_hash,
                       strict_policy_execution=True, http_transport=TRANSPORT_MODE)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--model', required=True)
    p.add_argument('--hands', type=int, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--device', default='cpu')
    args = p.parse_args()
    if args.hands < 0:
        p.error('Hands must be nonnegative')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    model, _, digest = load_policy(args.model, args.device)
    out = Path(args.out_dir)
    out.mkdir(exist_ok=False, parents=True)
    started = time.time()
    rng, token, completed, cumulative = random.Random(args.seed), None, 0, 0
    status = 'FAILED'
    try:
        with (out/'hands.jsonl').open('x') as handle:
            for index in range(args.hands):
                token, record = play_one(model, token, rng, device=args.device)
                cumulative += record['winnings_chips']
                record.update(attempted_hand=index+1, successful_hand=index+1,
                              model_sha256=digest, policy_seed=args.seed,
                              policy_mode='sample', policy_temperature=1.0,
                              policy_contract=METADATA['policy_contract'],
                              winnings_bb=record['winnings_chips']/100,
                              cumulative_chips=cumulative, cumulative_bb=cumulative/100)
                handle.write(json.dumps(record)+'\n')
                handle.flush()
                completed += 1
        if sha256_file(args.model) != digest:
            raise RuntimeError('Frozen checkpoint changed')
        status = 'COMPLETED'
    finally:
        close_transport()
        summary = dict(**METADATA, status=status, successful_hands=completed, target_hands=args.hands,
            model_sha256=digest, policy_seed=args.seed, cumulative_chips=cumulative,
            bb_per_100=(cumulative/completed if completed else None),
            wall_time_seconds=time.time()-started, command=[sys.executable, *sys.argv],
            finished_at=datetime.now(timezone.utc).isoformat())
        (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print(json.dumps(summary))


if __name__ == '__main__':
    main()
