# Fresh V4 Direct Slumbot Baseline - 2026-07-09

## Result

- Benchmark: `models/alpha_holdem_v4_final.pt` vs Slumbot, current hardened `bench_model_vs_slumbot.py` / `play_slumbot.py` path
- Policy: greedy, obs `v4`
- Hands: 20,400 total = 12 workers x 1,700
- Corrected result: **-71.383 bb/100**, 95% CI **[-92.222, -50.543]**
- SD: 1518.600 chips/hand

## Unit Check

`*_hands.jsonl` was deduplicated by `hand_idx`, using `winnings_hero` once per hand. At `BIG_BLIND = 100`, `mean_chips_per_hand` equals bb/100 because `(chips/hand / 100) * 100 = chips/hand`.

The per-worker summary field named `bb_per_100` is not used for the final number because `bench_model_vs_slumbot.py` writes it as `mean / BIG_BLIND`, which is BB/hand, not bb/100. The exact hand dumps avoid that field-name bug.

## Comparison Context

- Old V4 baseline from 2026-05-07: -49.7 bb/100 is superseded by this current-harness run; it is outside the final CI upper bound (-50.543).
- Latest V5 formal100k remains -100.248 bb/100, CI [-112.407, -88.088], L0.
- V5 minus fresh V4 point gap: -28.865 bb/100, approximate independent combined CI +/-24.127.

This report is comparison context only. It is not L5/L6 evidence and does not support a V5 strength claim.

## Validation

- Hands files: 12
- Summary files: 12
- All workers complete: True
- Winnings conflicts within per-decision dumps: 0
