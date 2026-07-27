#!/usr/bin/env python3
"""
Parallel driver for play_slumbot_llm.py (LLM vs Slumbot diagnostic benchmark).

Spawns W workers at BelowNormal priority, each playing hands/W hands in its own
Slumbot session, then merges the per-worker summaries into a pooled result.

Merging: pooled mean = hands-weighted mean of worker means; pooled variance via
combined within+between decomposition; CI95 = 1.96 * pooled_sd / sqrt(N).
A worker that aborts early still contributes its completed hands (its summary
reports only completed hands — the harness never silently skips).

Usage:
  python scripts/alpha_holdem/llm_bench_parallel.py --backend grok-cli \
      --model grok-build --total-hands 20000 --workers 20 --tag grok20k
"""

import argparse
import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent / 'play_slumbot_llm.py'

BELOW_NORMAL = 0x00004000  # Windows BELOW_NORMAL_PRIORITY_CLASS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', choices=('deepseek', 'grok-cli'), required=True)
    ap.add_argument('--model', default=None)
    ap.add_argument('--total-hands', type=int, required=True)
    ap.add_argument('--workers', type=int, default=10)
    ap.add_argument('--tag', required=True)
    ap.add_argument('--stagger-s', type=float, default=2.0)
    args = ap.parse_args()

    out_dir = REPO / 'tmp' / f'llm_bench_{args.tag}'
    out_dir.mkdir(parents=True, exist_ok=True)
    per_worker = max(1, args.total_hands // args.workers)

    procs = []
    for w in range(args.workers):
        prefix = out_dir / f'w{w:02d}'
        cmd = [sys.executable, str(HARNESS),
               '--backend', args.backend,
               '--hands', str(per_worker),
               '--out-prefix', str(prefix)]
        if args.model:
            cmd += ['--model', args.model]
        log_fh = open(f'{prefix}_driver.log', 'w')
        p = subprocess.Popen(cmd, stdout=log_fh, stderr=subprocess.STDOUT,
                             cwd=str(REPO), creationflags=BELOW_NORMAL,
                             env=os.environ.copy())
        procs.append((w, p, log_fh))
        time.sleep(args.stagger_s)

    print(f'[driver] {args.workers} workers x {per_worker} hands launched '
          f'(backend={args.backend} model={args.model})')

    t0 = time.time()
    while True:
        alive = [w for (w, p, _) in procs if p.poll() is None]
        done_summaries = list(out_dir.glob('w*_summary.json'))
        hands_done = 0
        for s in done_summaries:
            try:
                hands_done += json.loads(s.read_text()).get('hands', 0)
            except Exception:
                pass
        print(f'[driver] t={time.time()-t0:7.0f}s alive={len(alive):2d} '
              f'summaries={len(done_summaries)}/{args.workers} '
              f'hands_completed>={hands_done}', flush=True)
        if not alive:
            break
        time.sleep(60)

    for (_, _, fh) in procs:
        fh.close()

    # Merge
    means, sds, ns, fallbacks, decisions = [], [], [], 0, 0
    for s in sorted(out_dir.glob('w*_summary.json')):
        d = json.loads(s.read_text())
        if d.get('hands', 0) > 0:
            means.append(d['bb_per_100'])
            sds.append(d['sd_chips_per_hand'])
            ns.append(d['hands'])
            fallbacks += d.get('fallbacks', 0)
            decisions += d.get('decisions', 0)

    N = sum(ns)
    if N == 0:
        raise SystemExit('no completed hands across all workers')
    pooled_mean = sum(m * n for m, n in zip(means, ns)) / N
    # within + between variance
    within = sum((n - 1) * sd * sd for sd, n in zip(sds, ns))
    between = sum(n * (m - pooled_mean) ** 2 for m, n in zip(means, ns))
    pooled_var = (within + between) / max(N - 1, 1)
    pooled_sd = math.sqrt(pooled_var)
    ci = 1.96 * pooled_sd / math.sqrt(N)
    frate = fallbacks / max(decisions, 1)

    merged = {
        'backend': args.backend,
        'model': args.model,
        'workers': args.workers,
        'workers_reporting': len(ns),
        'hands': N,
        'bb_per_100': round(pooled_mean, 2),
        'ci95_bb_per_100': round(ci, 2),
        'sd_chips_per_hand': round(pooled_sd, 1),
        'decisions': decisions,
        'fallbacks': fallbacks,
        'fallback_rate': round(frate, 4),
        'valid': frate <= 0.02,
        'elapsed_s': round(time.time() - t0, 0),
        'evidence_class': 'llm_diagnostic',
        'out_dir': str(out_dir),
    }
    merged_path = out_dir / 'merged_summary.json'
    merged_path.write_text(json.dumps(merged, indent=2))
    print(json.dumps(merged, indent=2))


if __name__ == '__main__':
    main()
