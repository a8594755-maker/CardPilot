"""Corrected-contract mirrored evaluation. Missing metadata fails closed.

Both policies must explicitly bind to v6. Legacy weights may be rebound only as
a separate, recorded artifact; never silently interpreted as the old policy.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import random
import sys
import time
import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alpha_holdem.execution_v6 import decide, load_policy, sha256_file
from alpha_holdem.rules_v6 import ChipState
from alpha_holdem.policy_contract_v6 import METADATA, apply_incr
from alpha_holdem.v5_mirror_eval import action_uniform


def play_pair(
    candidate, anchor, deck, seed, pair_index, device='cpu',
    policy_mode='sample',
):
    outcomes, decisions = [], []
    for candidate_seat in (0, 1):
        state = ChipState.new(deck)
        seat_counts = [0, 0]
        while not state.terminal:
            p = state.actor
            uniform = action_uniform(seed, pair_index, p, seat_counts[p])
            incr, _ = decide(
                candidate if p == candidate_seat else anchor,
                state,
                uniform=uniform,
                device=device,
                policy_mode=policy_mode,
            )
            seat_counts[p] += 1
            state = apply_incr(state, incr)
        outcomes.append(state.payoffs()[candidate_seat]/100)
        decisions.append(sum(seat_counts))
    return dict(pair_index=pair_index, deck=list(deck), rewards_bb=outcomes, decisions=decisions)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--candidate', required=True)
    p.add_argument('--anchor', required=True)
    p.add_argument('--pairs', type=int, required=True)
    p.add_argument('--seed', type=int, required=True)
    p.add_argument('--out-dir', required=True)
    p.add_argument('--device', default='cpu')
    p.add_argument('--policy-mode', choices=['sample', 'greedy'], default='sample')
    args = p.parse_args()
    if args.pairs < 2:
        p.error('At least2 mirrored pairs required')
    torch.set_num_threads(1)
    torch.set_num_interop_threads(1)
    candidate, _, candidate_sha = load_policy(args.candidate, args.device)
    anchor, _, anchor_sha = load_policy(args.anchor, args.device)
    out = Path(args.out_dir)
    out.mkdir(exist_ok=False, parents=True)
    started = time.time()
    rng = random.Random(args.seed)
    values = []
    with (out/'pairs.jsonl').open('x') as handle:
        for index in range(args.pairs):
            deck = list(range(52))
            rng.shuffle(deck)
            result = play_pair(
                candidate, anchor, deck, args.seed, index, args.device,
                args.policy_mode,
            )
            handle.write(json.dumps(result)+'\n')
            values.append(np.mean(result['rewards_bb'])*100)
            if (index+1)%1024 == 0:
                handle.flush()
                print(json.dumps(dict(completed_pairs=index+1, target_pairs=args.pairs)), flush=True)
    if sha256_file(args.candidate) != candidate_sha or sha256_file(args.anchor) != anchor_sha:
        raise RuntimeError('Frozen checkpoint changed during evaluation')
    mean = float(np.mean(values))
    half = float(1.96*np.std(values, ddof=1)/np.sqrt(len(values)))
    summary = dict(**METADATA, status='COMPLETED', candidate_sha256=candidate_sha, anchor_sha256=anchor_sha,
        seed=args.seed, pairs=args.pairs, evaluation_hands=2*args.pairs,
        policy_mode=args.policy_mode,
        bb_per_100=mean, ci95=[mean-half, mean+half], ci_unit='independent mirrored pair average',
        wall_time_seconds=time.time()-started, command=[sys.executable, *sys.argv],
        completed_at=datetime.now(timezone.utc).isoformat(), pairs_sha256=sha256_file(out/'pairs.jsonl'))
    (out/'summary.json').write_text(json.dumps(summary, indent=2)+'\n')
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
