#!/usr/bin/env python3
"""Path B Slumbot bench launcher — N parallel play_slumbot.py sessions.

Spawns N subprocesses, each runs `--hands K` against Slumbot, aggregates results.
Wraps the v55_supervisor pattern without pulling in the queue/promotion code.
"""
from __future__ import annotations

import argparse
import math
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLAY_SCRIPT = Path(__file__).parent / 'play_slumbot.py'
BB_CHIPS = 100  # 100 chips = 1 BB in Slumbot client


def parse_log(path: Path) -> dict | None:
    """Parse a play_slumbot.py log file. Returns {hands, total_chips} or None.

    Expected end-of-run format from play_slumbot.py:
        Results vs Slumbot (1,000 hands):
          Avg:          ±X.XXXX BB/hand
          ...
          Total:        ±XXX chips (X.X BB)
    """
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except FileNotFoundError:
        return None
    hands = None
    chips = None
    m = re.search(r'Results vs Slumbot\s*\(\s*([\d,]+)\s+hands?\s*\)', text)
    if m:
        hands = int(m.group(1).replace(',', ''))
    m = re.search(r'Total:\s*([+-]?\d[\d,]*)\s+chips?', text)
    if m:
        chips = int(m.group(1).replace(',', ''))
    if hands is None or chips is None:
        return None
    return {'hands': hands, 'total_chips': chips, 'log': str(path)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--model', default='')
    p.add_argument('--strategy', choices=['model', 'fold', 'call', 'random', 'heuristic', 'heuristic_v2', 'heuristic_v3', 'heuristic_v3_1'], default='model',
                   help='Baseline strategy (no model needed for fold/call/random/heuristic[_v2/_v3/_v3_1]).')
    p.add_argument('--sessions', type=int, default=8)
    p.add_argument('--hands-per-session', type=int, default=1000)
    p.add_argument('--tag', default='path_b_smoke')
    p.add_argument('--out-dir', default='eval_logs/path_b')
    p.add_argument('--device', default='cpu')
    p.add_argument('--dump-slumbot', action='store_true',
                   help='Write per-decision JSONL dumps (for SB/BB and per-street analysis).')
    args = p.parse_args()
    if args.strategy == 'model' and not args.model:
        p.error('--model is required when --strategy=model')

    out_dir = ROOT / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f'[Bench] strategy={args.strategy}  model={args.model or "(n/a)"}')
    print(f'[Bench] sessions={args.sessions} hands_per_session={args.hands_per_session}')
    print(f'[Bench] target_total={args.sessions * args.hands_per_session} hands')
    print(f'[Bench] out_dir={out_dir}')
    print()

    jobs = []
    t0 = time.time()
    for idx in range(1, args.sessions + 1):
        out = out_dir / f'{args.tag}_part{idx}.log'
        err = out_dir / f'{args.tag}_part{idx}_err.log'
        cmd = [
            sys.executable, '-X', 'utf8', '-u',
            str(PLAY_SCRIPT),
            '--strategy', args.strategy,
            '--hands', str(args.hands_per_session),
            '--device', args.device,
        ]
        if args.strategy == 'model':
            cmd.extend(['--model', str(args.model)])
        if args.dump_slumbot:
            dump_path = out_dir / f'{args.tag}_part{idx}_dump.jsonl'
            cmd.extend(['--dump-slumbot', str(dump_path)])
        out_f = out.open('wb')
        err_f = err.open('wb')
        proc = subprocess.Popen(cmd, cwd=str(ROOT), stdout=out_f, stderr=err_f)
        proc._files = (out_f, err_f)
        jobs.append((idx, proc, out))
        print(f'  Started part{idx} (pid={proc.pid}) → {out.name}')

    print(f'\nWaiting for {len(jobs)} sessions...')
    for idx, proc, _ in jobs:
        rc = proc.wait()
        proc._files[0].close()
        proc._files[1].close()
        print(f'  part{idx} exit={rc}  elapsed={time.time()-t0:.0f}s')

    print(f'\nAll sessions complete in {time.time()-t0:.0f}s.\n')

    # Aggregate
    parsed = []
    for _, _, log_path in jobs:
        r = parse_log(log_path)
        if r is not None:
            parsed.append(r)
        else:
            print(f'  WARN: could not parse {log_path}')

    if not parsed:
        print('No sessions parsed cleanly. Check session logs manually.')
        sys.exit(1)

    total_hands = sum(p['hands'] for p in parsed)
    total_chips = sum(p['total_chips'] for p in parsed)
    avg_bb = total_chips / total_hands / BB_CHIPS
    bb100 = avg_bb * 100
    ci_mbb = 700.0 * math.sqrt(2000.0 / max(total_hands, 1))
    ci_bb100 = ci_mbb / 10.0

    print('=' * 60)
    print(f'Sessions parsed:  {len(parsed)} / {args.sessions}')
    print(f'Total hands:      {total_hands:,}')
    print(f'Total chips:      {total_chips:+,}')
    print(f'Avg BB/hand:      {avg_bb:+.4f}')
    print(f'bb/100:           {bb100:+.2f}')
    print(f'rough CI:         +/- {ci_bb100:.1f} bb/100')
    print('=' * 60)

    summary = out_dir / f'{args.tag}_summary.txt'
    with summary.open('w', encoding='utf-8') as f:
        f.write(f'tag={args.tag}\n')
        f.write(f'model={args.model}\n')
        f.write(f'sessions={len(parsed)}\n')
        f.write(f'hands={total_hands}\n')
        f.write(f'total_chips={total_chips:+d}\n')
        f.write(f'avg_bb={avg_bb:+.4f}\n')
        f.write(f'bb100={bb100:+.2f}\n')
        f.write(f'ci_bb100_rough=+/-{ci_bb100:.1f}\n')
        for r in parsed:
            f.write(f'log={r["log"]}\n')
    print(f'Summary: {summary}')


if __name__ == '__main__':
    main()
