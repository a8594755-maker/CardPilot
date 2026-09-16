# Frozen residual-scale control analysis

The control reused the exact frozen residual bundle and Standard10 checkpoint;
it generated zero training hands.  Six ascending scales consumed 24,576
development evaluation hands.  Scale `0.01` was the smallest preregistered dose
with 1--25% maximum greedy disagreement, a positive Standard10 point direction,
and four positive anchor points, so it alone advanced to 16,384 disjoint
confirmation hands.

On confirmation, scale `0.01` changed only 0.81--1.74% of Standard10 greedy
decisions.  It retained positive deltas against call-station (`+6.7627`), uniform
(`+181.5947`), and min-bet (`+68.2661`) anchors.  Uniform and min-bet had positive
paired 95% lower bounds.  This confirms that a very small residual can express
repeatable state-conditioned exploitation without erasing the base policy.

The decisive learned-anchor gate failed: candidate versus Standard10 was
`-1.0010 bb/100`, paired 95% CI `[-9.5199, +7.5180]`.  The result is compatible
with parity, but the preregistered rule required a positive point estimate.
Generic-anchor gains therefore cannot promote this frozen policy or justify
Slumbot allocation.

Decision: `REJECT_FROZEN_RESIDUAL_SCALE_TRANSFER`.  The useful remaining
mechanistic question is whether training *under* the preservation-scale strategy
distribution, instead of training at scale 1 and shrinking only at deployment,
produces learned-anchor improvement.  Any such test must be matched at the same
small root budget first and must use learned-policy anchors for promotion.
