# Representation-scope independent confirmation

Decision: `REPRESENTATION_SCOPE_REPLICATION_PASSED`.

196,608 new internal hands; zero new training or Slumbot hands. Discovery hands excluded.

| Anchor | Full minus heads bb/100 | 95% CI | Bonferroni 98.75% CI |
|---|---:|---|---|
| standard10 | +110.7298 | [+47.8083, +173.6514] | [+30.5464, +190.9133] |
| slumbot_free | +314.4709 | [+249.9921, +378.9496] | [+232.3031, +396.6387] |
| corrected_cfr96 | +593.3699 | [+508.3893, +678.3504] | [+485.0758, +701.6639] |
| heldout_weak | +156.2946 | [+88.2466, +224.3426] | [+69.5784, +243.0108] |

All raw pair/seat statistics, OOD count checks, frozen input/source hashes and paired contrasts passed post-exit review.

- Independent deal/action randomness, not an independent training seed.
- Three anchors were training opponents; fourth was excluded only from the current training run and shares historical source/league lineage.
- Normal paired CIs and a four-primary-contrast Bonferroni gate; no discovery pooling.
- Passing admits only a separately preregistered fixed20k Slumbot pilot, not100k qualification.

Next: preregister one fixed20k strict native-sampled Slumbot pilot of exactly this full checkpoint.

The100k fresh Slumbot positive-bb/100 and positive95%lower-bound goal remains unachieved.
