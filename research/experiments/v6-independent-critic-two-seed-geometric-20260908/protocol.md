# Matched independent-critic learning curve

## Frozen research question and inputs

One primary/control recipe, one architectural treatment, two retained independent
seed lineages. Seeds 1 and 3 start from the ORIGINAL fixed-regimen-two-seed-2m
endpoints, never qualification smoke descendants. Seed1 SHA256
52501761b214aafc00caea3cba14e6d51c8f176d33c612914d6916fd939bbcf2; Seed3
c23b7db58802e67c1bcb94f7418ff980db7ec981cab9ca171bb37cc574514d94.

Control retains detached shared actor features into critic_v2. Treatment clones
the card/action/stack/fusion encoder and trains that independent encoder with the
existing value head. Initial actor and value outputs are exact. The treatment
retains all 86 existing Adam states and adds 76 lazy-zero new states. Both retain
their actual Adam LR1e-4, all actor weights, reference, replay/RNG, pool and hand
counters. Global gradient clipping stays unchanged; extra critic gradients can
affect its magnitude. This is an architecture bundle, not isolated proof that
prediction error or direct feature capacity causes policy gains.

Keep all other parent settings: physical200bb legacy-v4 observation contract,
sampled hero/opponents T1, connected preflop actor, full network, 12 workers x8
environments, 4096 transition hands/iteration, PPO2/minibatch16384, current-to-
Standard10 KL1 static reference, entropy .005/floor .05, replay ratio .5/window2,
cap9 anchor-latest seven fixed/two recent, existing adaptive allocation and seeds.
No source rules, privileged inputs, action-Q or head-only gradient path.

## Dose and order

Actual physical target increments relative to each original parent: 262144 then
1048576 per arm. Complete whole PPO iterations; report overshoot, never relabel
transition/replay counts as physical executions. At each stage train in fixed
order S1 control, S1 independent, S3 independent, S3 control. Continue stage2 from
each stage1 endpoint with full retained state. Each job has a7200-second cap;
natural under-target termination is reviewed, not automatically retried/reset.
Use distinct managed attempt namespaces and preserve exact assignment/metric
prefixes. Capture and validate initial payload before first new update, including
declared first-derivation differences versus exact extended resume/control.

## Frozen internal evaluation

At each stage compare every endpoint to its own original parent on common decks;
join paired parent comparisons to compute independent-minus-control. Retain the
eight named anchors and their fixed order from fixed2M: Standard10, CFR4, legacy
iter16, legacy mixed65k, mixture seed1/3, heads-only seed1/3. Bind exact paths/hashes
in the machine input contract before launch. No anchor chosen from this trial.
Use greedy physical200bb legacy-v4 execution, both seats and1024 mirrored deck
pairs per anchor. Base seeds: S1 stage1=202609084101, S3 stage1=202609084301,
S1 stage2=202609085101, S3 stage2=202609085301; anchor stride1000003. Same deck set
for both arms within a seed/stage. Across seed/stage require unique decks and zero
overlap with retained evaluation corpus. Each endpoint evaluation executes32768
hands; eight evaluations total262144, with32768 unique planned decks.

Use raw per-deck seat averages for paired differences and conditional95% CIs;
report each seed, each seat, preservation(first4)/transfer(last4) panels, each
anchor, and own-parent changes. These are heterogeneous KNOWN learned opponents,
not lifetime-unseen families: sibling models share ancestry. Do not present this
panel alone as proof of generalization or justification for paper-scale compute.
Before a subsequent major scale allocation, require additional held-out-family
stress evidence and predeclared external calibration. No Slumbot hands in this
trial, and no final blind cohort can be relabeled from development evidence.

## Decisions

The262k milestone is not an absolute win gate. Unless a mechanical failure or
replicated broad collapse occurs, complete the already registered1M dose despite
negative absolute strength or inconclusive early differences. Broad collapse:
in both seeds, both-seat own-parent pooled CI upper<0 and at least3 anchors have
own-parent CI upper<-25bb/100. Do not stop for a single noisy anchor.

At1M, directional support requires treatment-control positive pooled and both
panel means in both seeds, with no consistent negative seat direction; assess
own-parent changes and throughput alongside it. Stronger claims require CIs and
independent replication, not positive points alone. Mixed results mean insufficient
evidence or unfavorable allocation, not universal failure of independent critics.
Do not scale unchanged solely because losses are finite or value loss decreases.
No automatic4M, external cohort, or2.7B allocation. Complete this record with raw
accounting, hashes, wall costs, uncertainty and the next resource decision.
