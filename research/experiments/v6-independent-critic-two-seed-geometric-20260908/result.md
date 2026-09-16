# Independent critic fixed-dose result

Both seeds and both arms completed both preregistered doses. All eight training
reviews and both raw evaluation reviews passed. This establishes execution
integrity within their documented scope, not bitwise worker RNG equivalence or
superior poker strength. Original checkpoints and raw evidence remain intact.

Accounting: 4,202,704 new physical terminal executions, 3,779,201 new
transition-bearing hands, 6,721,192 replay rows, and 3,664 optimizer steps summed
over eight jobs. These quantities are not interchangeable. Evaluation executed
262,144 hands on 32,768 distinct planned decks across both stages; matched arms
share decks deliberately, stages are disjoint. This trial used zero Slumbot hands.

## Strength and allocation

Independent minus control, paired conditional unadjusted 95% intervals, bb/100:

| Dose | Seed 1 | Seed 3 |
| --- | --- | --- |
| 262k | -7.82 [-19.87, 4.23] | 4.93 [-5.86, 15.71] |
| 1M | -3.03 [-15.02, 8.97] | 1.33 [-10.01, 12.67] |

At 1M, preservation-panel contrasts are +4.34 and +6.49, while transfer-panel
contrasts are -10.39 and -3.84. All four panel intervals cross zero. Seat 0/1
contrasts are +4.99/-11.04 for Seed 1 and -1.43/+4.08 for Seed 3. Own-parent
pooled changes are +3.71/+0.54 for control and +0.69/+1.87 for independent;
all four intervals cross zero. Full per-anchor intervals are in
stage2_raw_review.json; isolated nominal significance is not replicated breadth.

The preregistered directional-support criterion is NOT met. Neither arm meets
the replicated broad-collapse definition. There is no replicated positive
learning-curve signal supporting unchanged scale-up. This is insufficient
evidence of benefit at this dose, NOT a universal rejection of independent
critics or proof that larger-scale learning cannot work.

Measured training job wall time: control 4,164.505 seconds, independent
5,430.308 seconds, approximately 30.4% additional time at nearly equal physical
dose. Total training job time is 9,594.813 seconds; experiment wall time also
includes preparation, reviews and evaluation. Added cost has no demonstrated
strength payoff here. Do not promote the independent critic or automatically
allocate 4M/2.7B or a final Slumbot cohort.

These eight known learned anchors include shared ancestry. Their transfer panel
is not evidence of lifetime-unseen opponent generalization. Training used sampled
execution whereas this fixed evaluation used the preregistered greedy execution;
the result is specifically about that deployment contract.

Next resource decision: a bounded method-allocation review of training-versus-
deployment objective alignment, using this completed trial and existing external
calibration. Choose at most one material learned-policy intervention, rather than
another unmotivated local architecture tweak or unchanged scale-up. In particular,
distinguish sampled policy learning progress from greedy-only evaluation plateaus
before interpreting this line as unable to learn. No new training is authorized by
this report alone; preregister the chosen experiment and retain the existing
lineages. Held-out-family evidence and predeclared external calibration remain
required before a subsequent major scale allocation.
