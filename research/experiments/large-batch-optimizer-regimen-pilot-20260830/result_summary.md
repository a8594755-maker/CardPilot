# Matched optimizer-regimen pilot

Decision: `JOINT_REGIMEN_NOT_ADMITTED`.

New physical training hands: 274,832. Frozen internal evaluation: 73,728 hands. Slumbot hands: 0.

| Arm | Physical hands | Updates | Batch / initial LR | Adam steps | Partial steps | Max source KL |
|---|---:|---:|---|---:|---:|---:|
| control | 137,268 | 14 | 1024 / 3e-05 | 784 | 28 | 0.000801 |
| large | 137,564 | 14 | 16384 / 0.0003 | 56 | 28 | 0.003340 |

Primary contrast: large minus matched control, bb/100; confidence intervals use mirrored pairs.

| Anchor | Delta | 95% CI | Bonferroni 98.333% CI |
|---|---:|---:|---:|
| standard10 | -0.3359 | [-0.7883, +0.1164] | [-0.8885, +0.2166] |
| slumbot_free | +0.8341 | [-4.7437, +6.4119] | [-5.9787, +7.6469] |
| corrected_cfr96 | +3.3549 | [-4.6154, +11.3252] | [-6.3801, +13.0900] |

Both session audits, frozen input/source hashes, raw paired statistics, finite model/Adam state, all-head changes, unchanged shared representation, and reconstructed-versus-saved Adam steps passed.

Limitations:

- Joint minibatch/LR regimen; neither batch nor LR is isolated causally.
- One training seed per arm; shared seeds do not ensure matched trajectories after policies/timing diverge.
- Finite physical budgets stop at PPO boundaries, with reported overshoot.
- Partial minibatches get one Adam update each like full minibatches; weighting differs with their sizes.
- The joint regimen changes critic optimization steps too. Printed value losses are descriptive training losses, not heldout critic quality or a causal explanation.
- Three fixed training anchors are also assessment anchors; fresh deals test these opponents, not an untouched opponent population.
- All-heads-only, source-KL regularization and fixed/adaptive league differ from paper-scale AlphaHoldem.
- Nominal one-of-three CI gate is exploratory, not familywise significance; independent confirmation required.
- Internal sampled results are neither Slumbot bb/100 nor a proof of general strength.

Do not promote or scale this regimen; select a new evidence-driven diagnostic or treatment after reviewing the contrasts and training health.

The long-term goal remains unachieved: the same frozen policy must still complete at least100000 fresh Slumbot hands with positive bb/100 and95% CI lower bound.
