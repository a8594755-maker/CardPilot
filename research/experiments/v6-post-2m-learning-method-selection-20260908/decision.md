# Decision: one independent observable-state critic control

This zero-hand review is complete. Select an independently trainable copy of the
current public-observation encoder for the value function as the sole major
control against the unchanged retained PPO recipe. Here public-observation means
the player's legal information, including its own hole cards, never villain hole
cards or future board cards. This is an architectural hypothesis, not a finding
that critic error caused the plateau.

## Evidence and limits

The fixed two-seed additional 1M trial produced 2,101,842 physical executions and
no replicated positive broad direction. Pool, replay and temporal aggregation
controls already supply little reason for another such sweep. Current frozen
network.py passes `h.detach()` to critic_v2's 256-256-128-1 value head: value
training cannot improve the encoder features, while actor updates can move them.
An independently trained encoder can address this representational restriction
without feeding value gradients into the actor. It may instead overfit or add
cost with no benefit; neither moving features nor detachment proves a defect.

The corrected centralized-critic smoke was only 136,844 training hands across
two arms. Treatment-control was +29.2133 bb/100, CI [-3.1669, 61.5935], with four
of five positive anchor means. Its gate failed on median critic MSE (treatment
0.053674 versus control 0.049474). It used privileged opponent cards, head-only
actor learning, fresh optimizer and a different weak source-KL recipe. Thus its
NOT_PROMISING label is not broad evidence against the proposed present-regimen
observable-state encoder. Conversely its positive point is not proof of benefit.

The earlier three-seed high-pot audit did not establish the preregistered
high-pot defect: squared-error changes were negative in seeds 1 and 2, positive
in seed 3, with all intervals crossing zero. Do not add high-pot oversampling or
reset the critic on that evidence. The older Deep CFR and phased fictitious-play
controls remain informative, not universal algorithm refutations; neither is
selected now because changing learning family would introduce substantially more
unqualified sampling/optimization assumptions than this single control.

## Next implementation and qualification contract

Use isolated candidate code; preserve both completed fixed2M endpoints and all
their source/Adam/replay evidence. Clone each endpoint's card encoder, action
encoder, stack encoder and fusion trunk into an independent value tower. Retain
the existing value head and its Adam state. Initialize only newly introduced
encoder optimizer states explicitly; preserve all existing named states and LR,
actor weights, counters, replay, reference and pool. This is a declared
architecture derivation, not an exact unchanged resume. Use the existing managed
statistical-continuation namespace contract for real workers.

Before any pilot, test initial actor AND value forward parity on real retained
states, encoder storage independence, value-only gradients absent from actor,
actor-only gradients absent from value tower, nonzero value-encoder update,
all-street/seat shapes, checkpoint roundtrip and optimizer named-state coverage.
Test the actual worker inference and PPO path, not just a stand-alone network.
No extra privileged transition fields or Slumbot-derived labels are permitted.
No warmup that silently consumes new poker hands. Document any required replay
value handling; do not silently discard or reinterpret retained replay.

Following qualification, preregister one matched control/treatment continuation
from each same fixed2M parent (seeds 1 and 3), retaining all other current recipe
settings. Intended geometric doses are +262,144 and +1,048,576 physical hands per
arm, with no claim that the smaller dose establishes convergence. Freeze exact
evaluation seeds, opponents, execution contracts, counts and stopping rules before
launch. Use matched two-seat multi-opponent evaluations, and separate known-anchor
preservation from genuinely held-out heterogeneity; ancestral siblings alone do
not establish unseen-family generalization. Measure actual throughput overhead.

Critic held-out residuals and explained variance are mechanistic diagnostics,
not poker-strength promotion gates by themselves. Replicated broad learning
direction and preservation justify more scale even with negative absolute external
scores; broad regression or numerical/resume failure triggers analysis. No
automatic Slumbot test or 2.7B allocation. New external development calibration
must be predeclared, and final qualification remains an independent frozen
100,000-plus-hand test with valid positive lower CI.

Accounting for this selection review: zero new training/evaluation/Slumbot hands.
No new stronger policy exists as a result of this review. Next work is the
isolated implementation and real-path qualification, not another method survey.
