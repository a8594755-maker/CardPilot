# Privileged centralized-critic matched smoke

Sequence residuals are closed: causal-TCN lost to a same-seed head-only control
by -50.0073 bb/100 with CI95 [-98.6231,-1.3915] and only2/5 positive anchors.
The next mechanism test changes credit assignment, not deployed policy capacity.

Implement centralized training with decentralized execution (CTDE). At each
trainable decision, attach a 52-way one-hot encoding of the opponent private
cards to the transition only. Add a training-only critic head over the frozen
public256-wide trunk plus these52 privileged inputs:308->256->256->1. The actor
never receives private cards; deployment without privileged inputs uses the
unchanged public value path. For centralized PPO, recompute rollout baselines
from the frozen-at-collection actor/critic before GAE, then use the centralized
head for value loss. The source actor must migrate behavior-exactly. The
treatment optimizer updates the same four actor-head tensors as control plus six
centralized-critic tensors; control updates those four actor tensors plus the six
public-critic tensors. Thus both arms have ten optimizer states.

After unit/regression tests, train matched control and treatment independently
from legacy Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428
for at least65,536 physical v6 hands each with seed20261039/worker2026103900,
identical fixed deal stream, five frozen learned anchors, adaptive league,
sampled hero/selfplay0.25, lr3e-5, PPO2, target-KL0.01, advantage clip3, source
KL0.01, entropy0.005/floor0.05, fresh optimizer/critic/counters. No replay,
continuation, EMA, endpoint selection, sequence adapter, or smoke weight reuse.

Freeze and audit both endpoints. Evaluate source, control, treatment against all
five untouched anchors with2,048 mirrored pairs per cell, common seed20261040:
15 cells/61,440 hands. This smoke admits a262,144-hand matched CTDE pilot only if
the per-deck five-anchor-average treatment-control point estimate exceeds
-10bb/100, treatment-source point estimate is positive, at least3/5 per-anchor
treatment-control points are positive, median treatment pre-update critic MSE
over the final half of updates is below control, and all evidence gates pass.
Failure rejects this privileged critic design and moves to an EMA actor target
test. Slumbot hands=0.
