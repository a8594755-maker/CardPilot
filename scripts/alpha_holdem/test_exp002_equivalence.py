#!/usr/bin/env python3
"""
EXP-002 registered equivalence gate (ledger blocker 2, option a).

Runs train_v5_exp002.py twice on CPU with W=1 and identical seeds:
  A) --rollout-mode single
  B) --rollout-mode multi --rollout-envs-per-worker 1
and byte-compares the transition digest streams for the first N poker hands.

The comparison truncates both traces at the N-th hand_marker because the PPO
trigger boundary depends on OS scheduling (a run may drain a few extra
deterministic hands before the update fires); the pre-update stream itself is
fully deterministic, so the N-hand prefix must match exactly.

PASS criteria: both traces contain >= N hand markers AND the digest prefixes
up to the N-th marker are byte-identical.
"""

import argparse
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
TRAINER = Path(__file__).resolve().parent / 'train_v5_exp002.py'


def run_mode(mode: str, envs: int, hands: int, seed: int, wseed: int, tag: str,
             opp_phase: bool = False) -> Path:
    run_dir = REPO / 'tmp' / f'exp002_eq_{tag}'
    trace = run_dir / 'transitions.trace'
    if opp_phase:
        # Opp-mode coverage: snapshot after iter 1, then iter 2 runs pure
        # opp-mode (self-play-fraction 0). Total = 2 * hands.
        iter_hands, total, snap, spf = hands, hands * 2, 1, '0.0'
    else:
        iter_hands, total, snap, spf = hands, hands, 1000000, '0.2'
    cmd = [
        sys.executable, str(TRAINER),
        '--device', 'cpu',
        '--workers', '1',
        '--rollout-mode', mode,
        '--rollout-envs-per-worker', str(envs),
        '--hands-per-iter', str(iter_hands),
        '--total-hands', str(total),
        '--self-play-fraction', spf,
        '--ppo-epochs', '1',
        '--mini-batch-size', '256',
        '--snapshot-every', str(snap),
        '--save-interval', '1000000',
        '--seed', str(seed),
        '--worker-seed-base', str(wseed),
        '--run-dir', str(run_dir),
        '--run-id', f'exp002_eq_{tag}',
        '--overwrite',
        '--max-runtime-seconds', '1800',
        '--trace-transitions-file', str(trace),
        '--validate-stream',
    ]
    print(f'[eq] running {tag}: mode={mode} M={envs} hands={hands}')
    res = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO))
    if res.returncode != 0:
        print(res.stdout[-2000:])
        print(res.stderr[-2000:])
        raise SystemExit(f'{tag} run failed rc={res.returncode}')
    return trace


def prefix_until_n_markers(trace_path: Path, n: int):
    lines = trace_path.read_text().splitlines()
    out, markers = [], 0
    for ln in lines:
        out.append(ln)
        if ln.endswith(' 1'):
            markers += 1
            if markers >= n:
                break
    return out, markers


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--hands', type=int, default=1000)
    ap.add_argument('--seed', type=int, default=20260707)
    ap.add_argument('--worker-seed', type=int, default=777)
    args = ap.parse_args()

    t_single = run_mode('single', 1, args.hands, args.seed, args.worker_seed, 'single')
    t_multi = run_mode('multi', 1, args.hands, args.seed, args.worker_seed, 'multi')

    a, ma = prefix_until_n_markers(t_single, args.hands)
    b, mb = prefix_until_n_markers(t_multi, args.hands)

    print(f'[eq] single: {ma} hands / {len(a)} transitions in prefix')
    print(f'[eq] multi : {mb} hands / {len(b)} transitions in prefix')

    if ma < args.hands or mb < args.hands:
        raise SystemExit(f'FAIL: insufficient hands (need {args.hands}, got {ma}/{mb})')
    if a != b:
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                raise SystemExit(f'FAIL: first divergence at transition {i}: {x} vs {y}')
        raise SystemExit(f'FAIL: prefix length mismatch {len(a)} vs {len(b)}')

    print(f'PASS(self-play): {args.hands} hands / {len(a)} transitions byte-identical '
          f'between single and multi(M=1) with seed={args.seed} worker_seed={args.worker_seed}')

    # Phase 2 — opp-mode coverage: iter 1 self-play seeds one pool snapshot,
    # iter 2 is pure opp-mode (self_play_fraction=0). Compare the full 2-iter
    # prefix (2*hands markers): identical iter-1 data => identical PPO update
    # => identical snapshot => comparable opp-mode stream.
    n2 = args.hands // 2
    t_single2 = run_mode('single', 1, n2, args.seed, args.worker_seed, 'single_opp', opp_phase=True)
    t_multi2 = run_mode('multi', 1, n2, args.seed, args.worker_seed, 'multi_opp', opp_phase=True)

    a2, ma2 = prefix_until_n_markers(t_single2, n2 * 2)
    b2, mb2 = prefix_until_n_markers(t_multi2, n2 * 2)
    print(f'[eq] opp-phase single: {ma2} hands / {len(a2)} transitions')
    print(f'[eq] opp-phase multi : {mb2} hands / {len(b2)} transitions')
    if ma2 < n2 * 2 or mb2 < n2 * 2:
        raise SystemExit(f'FAIL(opp): insufficient hands (need {n2 * 2}, got {ma2}/{mb2})')
    if a2 != b2:
        for i, (x, y) in enumerate(zip(a2, b2)):
            if x != y:
                raise SystemExit(f'FAIL(opp): first divergence at transition {i}: {x} vs {y}')
        raise SystemExit(f'FAIL(opp): prefix length mismatch {len(a2)} vs {len(b2)}')

    print(f'PASS(opp-mode): {n2 * 2} hands (incl. pure opp-mode iteration) byte-identical '
          f'between single and multi(M=1)')


if __name__ == '__main__':
    main()
