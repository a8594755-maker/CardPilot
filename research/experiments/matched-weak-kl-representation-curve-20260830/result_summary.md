# Matched weak-KL representation-scope curve

Decision: `REPRESENTATION_SCOPE_ADMITS_CONFIRMATION`.

Curve checkpoints are fixed by physical counters only; only final endpoints determine admission.

New physical training hands: 1,054,555. Frozen internal evaluation: 163,840 hands. Slumbot hands: 0.

| Arm | Physical hands | Updates | Source-KL coefficient | Adam steps | Partial steps | Max source KL |
|---|---:|---:|---|---:|---:|---:|
| heads | 526,534 | 107 | 0.01 | 3096 | 214 | 0.217620 |
| full | 528,021 | 105 | 0.01 | 2531 | 168 | 1.091584 |

Primary contrast: full_final minus heads_final, bb/100; confidence intervals use mirrored pairs.

| Anchor | Delta | 95% CI | Bonferroni 98.75% CI |
|---|---:|---:|---:|
| standard10 | +134.1957 | [+45.9688, +222.4226] | [+21.7647, +246.6268] |
| slumbot_free | +349.9419 | [+257.8805, +442.0032] | [+232.6244, +467.2593] |
| corrected_cfr96 | +561.2466 | [+441.9834, +680.5097] | [+409.2648, +713.2283] |
| heldout_weak | +262.8925 | [+166.8930, +358.8920] | [+140.5565, +385.2285] |

Descriptive curve versus the same original source; no midpoint promotion or optional selection:

| Candidate | Actual physical training hands | Standard10 delta | Free delta | CFR96 delta | Heldout weak delta |
|---|---:|---:|---:|---:|---:|
| heads_mid | 280,240 | -2.2453 | +7.9314 | +63.7860 | +8.6038 |
| heads_final | 526,534 | +21.8929 | +22.6540 | +104.4483 | +25.9236 |
| full_mid | 266,797 | +122.3442 | +245.2219 | +437.3837 | +239.2990 |
| full_final | 528,021 | +156.0886 | +372.5958 | +665.6949 | +288.8161 |

All descriptive per-opponent paired intervals and within-arm mid-to-final contrasts are retained in completed_analysis.json; the four final full-minus-heads contrasts alone determine the primary gate.

Both session audits, frozen input/source hashes, raw paired statistics, finite model/Adam state, all-head changes, heads-only frozen versus full-network changed representation, and reconstructed-versus-saved Adam steps passed.

Limitations:

- Parameter scope is the sole learning intervention; it changes both actor and critic representation gradients, not actor capacity alone.
- One training seed per arm; shared seeds do not ensure matched trajectories after policies/timing diverge.
- Finite physical budgets stop at PPO boundaries, with reported overshoot.
- Partial minibatches get one Adam update each like full minibatches; weighting differs with their sizes.
- Different trajectories can yield different update counts and training losses; these are not matched heldout critic quality.
- Three assessment anchors are training opponents; fourth weak policy is excluded only from this run and shares earlier source/league lineage.
- This fixed/adaptive league and physical budget are not a faithful paper-scale AlphaHoldem or NashPG reproduction.
- Admission requires two adjusted positive lower bounds including Standard10 or heldout weak, all four positive primary points, no negative source point, then independent confirmation.
- Internal sampled results are neither Slumbot bb/100 nor a proof of general strength.
- OOD validity is recomputed from aggregate decision/node counts; this is not a new per-action trace audit.

Next: independently confirm the exact frozen endpoints on preregistered fresh deals before promotion.

The long-term goal remains unachieved: the same frozen policy must still complete at least100000 fresh Slumbot hands with positive bb/100 and95% CI lower bound.
