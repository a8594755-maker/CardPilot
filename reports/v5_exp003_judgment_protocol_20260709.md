# EXP-003 50M Judgment Protocol

Registered before any eligible post-408M mirror result was produced.

## Purpose

The previous queue design treated one usable candidate-vs-native-anchor mirror
as `DONE`. That proves only that a measurement is precise and in-distribution;
it does not isolate the causal effect of EXP-003. This protocol fixes the
measurement design without changing trainer behavior or extending the
registered training window.

## Frozen inputs

- EXP-003 cutover baseline: gate 21800 / `358,064,575` hands.
- Baseline checkpoint:
  `models/bench_v55_v5_v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709_iter21800_358M_promotion20k_checkpoint.pt`.
- Baseline SHA256:
  `60D3B7FFBFE750CC8C0D1E4DFCD80A308D6A3F406A4B5E5265B9D9563D8877D5`.
- Native anchor: 75M v55 checkpoint at iter/hands
  `4600 / 75,479,020`.
- Native-anchor checkpoint:
  `models/bench_v55_v5_v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1_iter4600_75M_quick5k_checkpoint.pt`.
- Native-anchor SHA256:
  `47318CF20388F0F2CFDC63D9D76BD6C5519D39DE54AB0E24589FCB1F90FC8F63`.
- Post checkpoint: the first saved checkpoint with gate `PASS` and total hands
  `>=408,064,575`. Freeze it once; do not substitute a later checkpoint after
  seeing a score.

## Fixed protocol

Run all three comparisons with `v5_mirror_eval.py`:

1. gate21800 candidate vs native75M anchor.
2. eligible post candidate vs native75M anchor.
3. the same post candidate directly vs gate21800.

For every role:

- pairs: `25,000`;
- seed: `20260709`;
- starting stack: `200` bb;
- policy: `greedy_argmax_both_sides`;
- device/priority: CPU and BelowNormal;
- anchor OOD validity threshold: `0.15`;
- frozen checkpoint hashes recorded in the result row;
- no Slumbot or other official eval may be displaced.

Suggested artifact prefixes:

- `v5_mirror_eval_exp003_pre_vs_native_gate21800_25kp`;
- `v5_mirror_eval_exp003_post_vs_native_<gate>_25kp`;
- `v5_mirror_eval_exp003_post_vs_pre_gate21800_<gate>_25kp`.

## Judgment

A role is usable only when its CI gate passes, its anchor OOD is `<=0.15`, and
all fixed protocol fields match. The bundle is review-ready only when all three
roles exist for the same post checkpoint.

- Native-axis improvement: post-vs-native point estimate must improve over
  pre-vs-native by more than the combined 95% CI half-width.
- Direct causal check: post-vs-pre point estimate must have a 95% CI lower bound
  above zero.
- Guards: health `PASS`, effective h/s decline no worse than 20% versus the
  registered baseline, empty stderr, `aiev_skip=0`, deterministic counters
  present, and no registered collapse/stream guard failure.
- The postflop action-shape change is a sanity/localization signal, not a
  substitute for the two mirror effect gates.
- A valid measurement bundle is not an ADOPT decision. Write a separate
  `v5_exp003_judgment*.json` with candidate checkpoint hands and explicit
  `ADOPT` or `ROLLBACK`, then append the Ops row.
- If the fixed 25k bundle is inconclusive, record `INCONCLUSIVE` and escalate
  the next measurement design before another behavior change. Do not extend
  the training checkpoint window or select a later checkpoint post hoc.

## Pre-result quantitative method-support gates (fixed 2026-07-09)

These definitions were frozen before the first eligible post-cutover checkpoint
or any 25k-pair result existed. They resolve the ledger's previously qualitative
"value loss clearly below trend" language without post-result discretion.

- Value-loss reference: the 200 parsed training rows ending at gate 21800 in the
  pre-cutover parent. Candidate: the 200 parsed rows ending at the first eligible
  frozen checkpoint. Compute `mean(pre) - mean(post)` and a deterministic 95%
  moving-block-bootstrap interval (20-row circular blocks, 5,000 replicates,
  seed `20260709`). `PASS` requires CI lower bound `> 0`; `REGRESSION` requires
  CI upper bound `< 0`; otherwise `INCONCLUSIVE`.
- Postflop action-shape support: over the same candidate 200-row window, mean
  `(xmix_raise + xmix_allin)` must be in `[0.30, 0.60]`. Below `0.05` or above
  `0.90` is a hard collapse; the intermediate unsupported bands are
  `INCONCLUSIVE`, not an automatic rollback.
- Entropy at the candidate checkpoint must be at least `0.3`. Candidate mean
  value loss above `10x` the pre-window mean is a hard-stop guard.
- `ADOPT` therefore requires both registered mirror gates, every hard guard, the
  value-loss `PASS`, and postflop-shape support. A valid bundle with no hard
  regression but an inconclusive method-support metric is `INCONCLUSIVE`.

Official Slumbot evidence remains required for any V4/L5/L6 strength claim.
