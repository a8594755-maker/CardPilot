# Weak-source-KL independent confirmation

Decision: `WEAK_KL_REPLICATION_PASSED`.

147,456 new internal hands; zero new training or Slumbot hands. Discovery hands excluded.

| Anchor | Weak minus control bb/100 | 95% CI | Bonferroni 98.333% CI |
|---|---:|---|---|
| standard10 | +3.6799 | [-10.9943, +18.3541] | [-14.2435, +21.6033] |
| slumbot_free | +6.5710 | [-10.3507, +23.4928] | [-14.0975, +27.2396] |
| corrected_cfr96 | +64.8487 | [+31.6730, +98.0244] | [+24.3273, +105.3701] |

All raw pair/seat statistics, OOD count checks, frozen input/source hashes and paired contrasts passed post-exit review.

- Independent deal/action randomness, not an independent training seed.
- Anchors were training opponents, not a new opponent population.
- Normal paired CIs and a three-primary-contrast Bonferroni gate; no discovery pooling.
- Passing admits only a separately preregistered fixed20k Slumbot pilot, not100k qualification.

Next: preregister one fixed20k strict native-sampled Slumbot pilot of exactly this weak checkpoint.

The100k fresh Slumbot positive-bb/100 and positive95%lower-bound goal remains unachieved.
