# Frozen final sampled independent confirmation

Decision: `INDEPENDENT_INTERNAL_REPLICATION_FAILED`.

New evaluation: **98,304 internal hands**, seed20260894,8192 mirrored pairs per anchor for control and final. **Zero new training/Slumbot hands.** Parent147456 discovery hands are excluded.

| Anchor | Discovery delta (95% CI) | Independent delta (95% CI) | Independent Bonferroni98.333% CI |
|---|---:|---:|---:|
| standard10 | +0.548 [-0.346, +1.442] | +1.913 [-0.508, +4.335] | [-1.044, +4.871] |
| slumbot_free | +0.514 [-5.694, +6.723] | -1.276 [-5.375, +2.824] | [-6.283, +3.732] |
| corrected_cfr96 | +17.136 [+3.753, +30.520] | +12.192 [+1.462, +22.923] | [-0.914, +25.299] |

All numbers are treatment-minus-original-Standard10-control bb/100; CIs use mirrored pairs, not individual seats. Discovery and independent intervals are shown separately, never pooled.

Nominal registered gate: **False**. Multiplicity-adjusted secondary gate: **False**.
The nominal one-of-three positive-lower-bound gate is not familywise significance. The current result is internal evidence only, not a Slumbot benchmark, exploitability estimate, or proof of general superiority.

Fixed policy SHA256: `ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3`. No checkpoint/mode was changed after discovery admission.
Validation: complete raw arrays, seeds/physical action streams, paired-seat arithmetic, source/model hashes and independently recomputed paired statistics passed. The original evaluation process ended before this report was written.

## Next action

Do not promote this checkpoint to a Slumbot test or scale the unchanged training configuration. Follow the registered branch: a separately logged fixed-weight, whole-hand-group actor-gradient-noise diagnostic, distinguishing PPO noise from regularizer effects before selecting an optimizer-batch treatment. Do not retest an alternative discovery checkpoint or merge data to rescue this result.

The long-term goal remains unachieved: one frozen policy still needs at least100000 fresh Slumbot hands above0bb/100 with positive95% CI lower bound.
