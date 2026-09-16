# Action-RMS advantage pilot result

## Decision

Reject `action_rms` as the next general-policy improvement. It did not produce a
robust matched gain over the untouched global-normalization all-policy-heads
control, so no Slumbot benchmark was run.

## Training and integrity

- Smoke: 292 actual environment hands; the normalization gate passed.
- Production: 263,467 actual environment hands in 64 contiguous updates.
- Total new training: 263,759 actual environment hands.
- Fixed opponents, initialization, training deal stream, seeds, architecture,
  optimizer configuration, and evaluation schedule matched the control. The only
  treatment was `policy_advantage_normalization=action_rms` with a 32-row fallback.
- Terminal audit: PASS. The audit verified the manifest/checkpoint/metrics hand and
  iteration boundaries, all 64 hash-chained opponent assignments and restored RNG,
  the nonempty optimizer at step 1,832, all three fixed opponent SHA256 values, and
  the exact iter16/32/48/64 archive set.
- Training remained numerically stable: zero KL early stops, maximum source-policy
  KL 0.002071, and maximum PPO clip fraction 0.01954.

## Fresh matched frozen curve

Each checkpoint used seed 20260853, 1,024 mirrored pairs per anchor, greedy frozen
policies on both sides, and stored pair-level outcomes. All candidate and anchor OOD
rates were zero. Treatment-control deltas and paired 95% intervals are in bb/100.

| Iteration | Anchor | Delta | 95% CI |
|---:|---|---:|---:|
| 16 | Standard10 | +0.000 | [-1.053, +1.053] |
| 16 | slumbot_free | -0.463 | [-2.505, +1.579] |
| 16 | corrected CFR96 | -4.418 | [-16.325, +7.488] |
| 32 | Standard10 | +0.195 | [-0.958, +1.349] |
| 32 | slumbot_free | +0.063 | [-1.562, +1.687] |
| 32 | corrected CFR96 | -16.931 | [-38.741, +4.878] |
| 48 | Standard10 | -0.806 | [-1.821, +0.210] |
| 48 | slumbot_free | +0.234 | [-1.285, +1.754] |
| 48 | corrected CFR96 | -5.206 | [-16.885, +6.473] |
| 64 | Standard10 | -0.659 | [-1.529, +0.210] |
| 64 | slumbot_free | +1.025 | [-1.085, +3.134] |
| 64 | corrected CFR96 | +3.125 | [-18.592, +24.842] |

Across the 12 rows, 5 estimates were positive, 6 negative, and 1 exactly zero.
The mean delta was -1.987 bb/100 and the median was -0.231 bb/100. Every confidence
interval crossed zero. The terminal checkpoint's two positive anchor estimates were
therefore insufficient: it simultaneously regressed against Standard10, and none of
the three terminal lower bounds was positive.

The evaluation comprises 24,576 internal mirrored hands. It is an internal progress
signal only, not a Slumbot or formal benchmark claim.

## Research implication

Equalizing action-slot RMS changed the actor update as intended and remained stable,
but the intervention did not improve generalization. More budget on this treatment
has low expected information value. The next experiment should change the learned
signal or representation rather than continue another optimizer-normalization or
opponent-selection variant on the same 262k-hand recipe.
