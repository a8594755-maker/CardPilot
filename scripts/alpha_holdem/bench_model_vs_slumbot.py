#!/usr/bin/env python3
"""
Standalone model-vs-Slumbot benchmark (DIAGNOSTIC) — re-verify a checkpoint's
direct Slumbot bb/100 with the CURRENT hardened harness, independent of any
training run or mirror eval.

Motivation: the mirror-vs-V4 instrument broke for aggressive candidates (anchor
cap-1 emulation artifact at 55% OOD). This utility re-runs a model vs Slumbot
fresh with the same play_slumbot.py play loop used for V5's official evals.

One worker = one Slumbot session playing N hands greedy. Winnings come from
Slumbot's own field (chips == bb/100 at BB=100). No silent skips: a hand that
errors aborts that worker (its completed hands still count).

Usage (parallel via a launcher, or single):
  python scripts/alpha_holdem/bench_model_vs_slumbot.py \
    --model models/alpha_holdem_v4_final.pt --hands 2500 --out-prefix tmp/v4slum/w00
"""

import argparse
import json
import math
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
import torch  # noqa: E402
from alpha_holdem.network import AlphaHoldemNet  # noqa: E402
from alpha_holdem.environment import NUM_ACTIONS  # noqa: E402
from alpha_holdem.play_slumbot import play_hand, resolve_obs_version, BIG_BLIND  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--model', required=True)
    ap.add_argument('--hands', type=int, default=2500)
    ap.add_argument('--device', default='cpu')
    ap.add_argument('--policy-mode', default='greedy')
    ap.add_argument('--obs-version', default='auto')
    ap.add_argument('--out-prefix', required=True)
    args = ap.parse_args()

    ckpt = torch.load(args.model, map_location=args.device, weights_only=False)
    norm = ckpt.get('norm_layer', 'bn')
    model = AlphaHoldemNet(num_actions=NUM_ACTIONS, norm_layer=norm).to(args.device)
    # Build the lazy trunk with one dummy forward before loading weights.
    dc = torch.zeros(1, 6, 4, 13, device=args.device)
    da = torch.zeros(1, 25, 4, 5, device=args.device)
    de = torch.zeros(1, 2, device=args.device)
    with torch.no_grad():
        model(dc, da, de)
    model.load_state_dict(ckpt['model'])
    model.eval()
    obs_version = resolve_obs_version(ckpt, args.obs_version)

    out_prefix = args.out_prefix
    os.makedirs(os.path.dirname(out_prefix) or '.', exist_ok=True)
    dump_fp = open(f'{out_prefix}_hands.jsonl', 'w', encoding='utf-8')

    token = None
    winnings = []
    for h in range(args.hands):
        try:
            token, w = play_hand(
                model, token, args.device,
                verbose=False, greedy=True, obs_version=obs_version,
                policy_mode=args.policy_mode, dump_fp=dump_fp, hand_idx=h,
            )
        except Exception as e:  # noqa: BLE001
            sys.stderr.write(f'ABORT hand {h}: {e}\n')
            break
        winnings.append(w)
    dump_fp.close()

    n = len(winnings)
    mean = sum(winnings) / n if n else 0.0
    var = sum((x - mean) ** 2 for x in winnings) / max(n - 1, 1) if n > 1 else 0.0
    sd = math.sqrt(var)
    ci = 1.96 * sd / math.sqrt(n) if n else 0.0
    bb_per_100 = (mean / BIG_BLIND) * 100.0
    ci95_bb_per_100 = (ci / BIG_BLIND) * 100.0
    summary = {
        'model': args.model,
        'obs_version': obs_version,
        'policy_mode': args.policy_mode,
        'hands': n,
        'bb_per_100': round(bb_per_100, 2),
        'mean_chips_per_hand': round(mean, 1),
        'ci95_bb_per_100': round(ci95_bb_per_100, 2),
        'sd_chips_per_hand': round(sd, 1),
    }
    json.dump(summary, open(f'{out_prefix}_summary.json', 'w'), indent=2)
    print(json.dumps(summary))


if __name__ == '__main__':
    main()
