# All-in runout EV variance-reduction pilot result

## Decision

Reject scaling all-in runout EV as a standalone policy improvement. The
intervention was active, stable, and auditable, but did not produce a robust matched
multi-anchor gain over the untouched sampled-runout all-policy-heads control. No
Slumbot evaluation was run.

## Training and intervention integrity

- Unit tests: 9/9 passed for exact equity, deterministic bounded sampling,
  zero-sum rewards, cap accounting, and skip conditions.
- Smoke: 4,111 actual hands; 16 EV replacements using 2,108 runouts; audit PASS.
- Production: 263,472 actual hands in 64 contiguous updates.
- Total new training: 267,583 actual environment hands.
- Production EV evidence: all 64 updates contained replacements; 1,698 sampled
  all-in payoffs were replaced using 212,148 deterministic runouts (124.94 mean),
  with zero skipped. Mirror-deal variance reduction remained disabled.
- Terminal session audit: PASS for manifest/checkpoint/metric boundaries, all 64
  assignment hash-chain/RNG records, optimizer step 1,820, the three fixed anchor
  hashes, and the exact iter16/32/48/64 archives.
- Training remained stable: zero KL early stops, maximum source-policy KL 0.001777,
  and maximum PPO clip fraction 0.0000326.

## Fresh matched frozen curve

Each checkpoint used seed 20260853, 1,024 mirrored pairs per anchor, greedy frozen
policies on both sides, and stored pair-level outcomes. All OOD rates were zero.
Treatment-control deltas and paired 95% intervals are in bb/100.

| Iteration | Anchor | Delta | 95% CI |
|---:|---|---:|---:|
| 16 | Standard10 | +0.049 | [-0.940, +1.038] |
| 16 | slumbot_free | -0.895 | [-2.187, +0.398] |
| 16 | corrected CFR96 | -0.461 | [-3.599, +2.677] |
| 32 | Standard10 | +0.049 | [-0.705, +0.802] |
| 32 | slumbot_free | -0.164 | [-1.049, +0.721] |
| 32 | corrected CFR96 | -10.383 | [-28.841, +8.074] |
| 48 | Standard10 | -0.171 | [-0.522, +0.181] |
| 48 | slumbot_free | -0.366 | [-1.132, +0.400] |
| 48 | corrected CFR96 | +9.815 | [-8.638, +28.268] |
| 64 | Standard10 | +0.439 | [-0.171, +1.049] |
| 64 | slumbot_free | -0.358 | [-1.510, +0.793] |
| 64 | corrected CFR96 | +9.358 | [-9.080, +27.796] |

Five estimates were positive and seven negative. The mean delta was +0.576 bb/100,
but the median was -0.167 bb/100 and every interval crossed zero. The positive mean
was driven by the high-variance late CFR96 rows. The lower-variance slumbot_free row
was negative at every checkpoint, while terminal Standard10 was positive but still
had a negative lower bound.

The 24,576 evaluation hands are an internal progress signal only, not a Slumbot or
formal benchmark claim.

## Research implication

Runout EV is a sound variance-reduction primitive and may remain enabled in future
large training recipes, but the isolated 262k-hand causal test does not justify
additional budget or promotion. The next experiment should target broader return
variance or richer counterfactual learning rather than deepen this treatment based
on noisy CFR96 point estimates.
