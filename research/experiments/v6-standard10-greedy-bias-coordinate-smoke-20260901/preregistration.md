# Preregistration: direct greedy-utility actor-bias coordinate smoke

## Motivation and hypothesis

Sampled PPO repeatedly produced policies whose probabilities and weights differed but
whose deployed greedy physical-v6 behavior collapsed to the same aggressive basin.
ELO only changed opponents or selected checkpoints, and its top survivor failed
heldout cross-play.  This experiment asks whether exact greedy tournament utility can
directly train a small, general subset of learned weights.

Starting from frozen Standard10, optimize only the nine postflop and nine preflop
policy-head biases.  These are ordinary network weights shared across all states; no
state-, opponent-, hand-, or benchmark-specific action rule is added.  The hypothesis
is that a conservative derivative-free update can improve a robust multi-opponent
objective and transfer to unseen policies/deals without destroying the source.

The historical single imitation-teacher fresh20k result (-18.5025 bb/100), Action-Q
formal100k failure, counterfactual-soft-policy failure, and average-policy failures
remain negative controls.  This run performs none of those updates.

## Search contract

- Source: `models/baseline/standard10/latest.pt`, legacy-v4 observation bridge.
- Search anchors:
  1. Standard10 itself (legacy-v4);
  2. fresh-zero no-KL-stop terminal policy (legacy-v4);
  3. externally failed raw learned actor (native v6);
  4. frozen slumbot-free learned anchor (legacy-v4).
- Exact physical-v6 greedy mirrored play with each policy's own observation contract.
- One deterministic coordinate pass in fixed order:
  `policy_head.bias[0:9]`, then `preflop_policy_head.bias[0:9]`.
- At each coordinate evaluate current, +0.05, and -0.05.  The current point is reused;
  the two treatments use 64 mirrored pairs per anchor and fixed per-anchor seeds.
- Score each treatment using its candidate-minus-source bb/100 vector:
  `mean(delta) - 0.5 * population_std(delta)`.  Stable tie-breaking keeps current.
- Raw pair outcomes, summaries, offsets, hashes, and every coordinate choice are
  immutable evidence.

The search consumes 18,944 physical environment training hands: 512 source-baseline
hands plus 36 treatments x four anchors x 128 hands.  These are training hands because
their outcomes directly select weights.  There are no PPO hands or offline samples.

## Mechanism and validation gates

Run untouched validation only if all are true:

1. at least one bias changes;
2. final robust search score is positive;
3. at least three of four search deltas are nonnegative; and
4. no search delta is below -10 bb/100.

Validation freezes the candidate before observing new outcomes.  Compare frozen
candidate and unchanged Standard10 on identical new 512-pair deal streams against:

1. Standard10 (new deal seed);
2. native-v6 procedural-soup policy;
3. legacy-contract mixed-league iter16 policy;
4. physical-1M final policy; and
5. the fresh-zero KL-stop policy.

These policy/deal cells do not influence search.  Validation support requires all five
paired candidate-minus-source point estimates positive, at least three individual 95%
CI lower bounds positive, and the pooled paired 95% CI lower bound positive.  Failure
means reject this bias-only direct-utility route without Slumbot or scale.  Passing
would admit a separately preregistered larger-seed internal confirmation only; it is
not sufficient for an external claim.
