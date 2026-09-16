# Matched source-KL weakening pilot

Decision: `WEAK_SOURCE_KL_ADMITS_CONFIRMATION`.

New physical training hands: 531,842. Frozen internal evaluation: 73,728 hands. Slumbot hands: 0.

| Arm | Physical hands | Updates | Source-KL coefficient | Adam steps | Partial steps | Max source KL |
|---|---:|---:|---|---:|---:|---:|
| control | 266,357 | 54 | 1.0 | 1570 | 106 | 0.001437 |
| weak | 265,485 | 54 | 0.01 | 1548 | 108 | 0.127484 |

Primary contrast: weak-KL minus matched control, bb/100; confidence intervals use mirrored pairs.

| Anchor | Delta | 95% CI | Bonferroni 98.333% CI |
|---|---:|---:|---:|
| standard10 | +27.1421 | [+6.1129, +48.1713] | [+1.4566, +52.8276] |
| slumbot_free | +9.3898 | [-10.9466, +29.7263] | [-15.4495, +34.2291] |
| corrected_cfr96 | +74.3967 | [+23.1618, +125.6316] | [+11.8175, +136.9760] |

Both session audits, frozen input/source hashes, raw paired statistics, finite model/Adam state, all-head changes, unchanged shared representation, and reconstructed-versus-saved Adam steps passed.

Limitations:

- Source-KL coefficient is the sole learning hyperparameter changed; one training seed cannot establish reproducibility.
- One training seed per arm; shared seeds do not ensure matched trajectories after policies/timing diverge.
- Finite physical budgets stop at PPO boundaries, with reported overshoot.
- Partial minibatches get one Adam update each like full minibatches; weighting differs with their sizes.
- Different trajectories can yield different update counts and training losses; these are not matched heldout critic quality.
- Three fixed training anchors are also assessment anchors; fresh deals test these opponents, not an untouched opponent population.
- All-heads-only, source-KL regularization and fixed/adaptive league differ from paper-scale AlphaHoldem.
- Admission requires a Bonferroni-adjusted positive primary lower bound and independent confirmation; this remains a small internal pilot.
- Internal sampled results are neither Slumbot bb/100 nor a proof of general strength.
- OOD validity is recomputed from aggregate decision/node counts; this is not a new per-action trace audit.

Next: independently confirm the exact frozen endpoints on preregistered fresh deals before promotion.

The long-term goal remains unachieved: the same frozen policy must still complete at least100000 fresh Slumbot hands with positive bb/100 and95% CI lower bound.
