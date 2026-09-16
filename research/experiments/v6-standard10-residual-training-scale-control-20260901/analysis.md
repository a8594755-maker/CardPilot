# Matched residual training-scale control analysis

Both arms completed the same eight-root training budget, 16,384 evaluation
hands, and 512 optimizer steps per seat/iteration using identical seeds.  Total
accounting was 16 physical training roots, 32,768 evaluation hands, and 37,631
exact-v6 decision nodes.

Training and deploying at scale `0.01` solved the preservation problem.  Its
greedy disagreement from Standard10 stayed between 0.73% and 1.95%, compared
with 61.6%--69.7% for scale `1`.  The direct Standard10 point moved from
`-206.6846` at scale `1` to `+1.2207 bb/100` at scale `0.01`, a directional
improvement of `+207.9053`.  The scale-0.01 Standard10 interval
`[-16.6627, +19.1041]` is consistent with parity, not demonstrated superiority.

The broader gate failed.  Scale `0.01` was positive only against Standard10 and
call-station.  It lost `-106.4907 bb/100` to uniform and `-88.6577 bb/100` to
min-bet; the latter paired interval `[-167.5484, -9.7671]` was wholly negative.
The mean four-anchor delta was `-47.4565 bb/100`.  This is the reverse of the
posthoc-shrink bundle's generic-anchor pattern and shows strong root/deal
sensitivity at the tiny traversal budget.

Decision: `REJECT_STANDARD10_RESIDUAL_REGRET_ROUTE`.  The mechanism can preserve
Standard10 and can express state-conditioned changes, but the accumulated
matched and disjoint evidence does not support general improvement.  Do not
tune another scale or expand CFR roots under this formulation.
