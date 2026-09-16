# Exact-v6 exploration and SD-CFR average-strategy control

Decision: `REJECT_EPSILON_0_1_AS_SUFFICIENT`.

The matched epsilon-0.1 arm achieved its structural purpose: every seat had
traverser coverage in every iteration and mean log imbalance fell from 0.939 to
0.288. Its buffers were also balanced at 3,257/3,473 samples versus
8,064/2,511 for epsilon 0. However, the correct iteration-weighted per-hand
snapshot policy was worse on two of three generic anchors. Its three-anchor mean
was -42.05 versus +178.19 bb/100 for epsilon 0, a -220.23 delta. Intervals remain
wide even at 256 pairs, so this is a rejection of sufficiency, not a precise
strength ranking.

Post-run primary-source audit of Brown et al. (2019), Algorithm 2, shows that
Deep CFR samples opponent actions directly from the regret-matched current
strategy. The paper does not introduce epsilon mixing in external sampling.
Algorithm 1 also collects traversals for one player and then trains that player's
value network from scratch before moving to the next player. Section 5.2 reports
that fresh random initialization each CFR iteration improved convergence. Thus:

- epsilon 0.1 is a repository-specific biased behavior-policy variant, not a
  paper-faithful correction;
- the earlier claim that within-iteration sequential updates were inherently a
  bug was incorrect;
- the current warm-update regimen is a larger paper-contract deviation than the
  ordering issue.

The average-strategy correction remains valid: the paper explicitly states that
the average strategy converges and describes sampling a stored value network at
play time to avoid average-policy approximation error. This experiment is the
first in this route to evaluate that per-hand snapshot contract.

Next step: matched epsilon-0 sequential Deep CFR with warm versus fresh-random
value-network training from the same initial strategy, common decks, sampling
seeds, buffer, and iteration-weighted snapshot evaluation. Admission should
favor paper-faithful fresh reinitialization only if it improves coverage balance
and/or snapshot-policy transfer; do not revive epsilon solely for coverage.

Primary source: https://proceedings.mlr.press/v97/brown19b.html
