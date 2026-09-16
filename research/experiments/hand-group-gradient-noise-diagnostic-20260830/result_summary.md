# Whole-hand gradient-noise diagnostic

Decision: `WHOLE_HAND_NOISE_SUPPORTS_BOUNDED_BATCH_TREATMENT`.

New measured physical training hands: 40,155. No strength-evaluation or Slumbot hands.

| Cohort | Updates | Physical hands | PPO noisy/unresolved fraction | PPO median noise/signal | Actor median noise/signal |
|---|---:|---:|---:|---:|---:|
| source | 4 | 19,688 | 1.000 | 26.480930127998217 | 58.744989176828774 |
| mature | 4 | 20,467 | 1.000 | 36.53804630289885 | 18.268519562654355 |

All retained Gram matrices were used to recompute the noise statistics; hand grouping/counts and both session audits passed. The mature Adam state advanced from its unchanged input; its local hand counter reset belongs only to this new diagnostic.

Limitations:
- Pre-Adam gradients, not effective optimizer directions.
- Equal-hand clusters have variable transition counts; common normalization preserves transition-weighted objective.
- Full-batch normalized/clipped advantages and adaptive league can correlate groups. This is not a formal IID critical-batch estimate.
- Cohorts have different model/optimizer/league histories and fresh seeds; differences are descriptive, not a randomized causal model-age effect.
- Zero evaluation/Slumbot hands; no poker-strength claim.

A positive diagnostic gate only admits a separately preregistered bounded optimizer-batch experiment, with explicit learning-rate/update-count tradeoffs and independent poker evaluation. It does not justify paper-scale training.
