# Current-regimen fresh-only control qualification

Question: does removing stale replay improve current general learned-weight
progress per physical hand and per wall second? This is not a claim that replay
caused prior regressions. The old alpha-replay-buffer-pilot-20260830 found no
robust gain at263k on a different contract/regimen; it does not settle the
current full-network/connected-preflop/static-current-KL/anchor-recent regime.

Choose both flat capacity9 stage2 endpoints of the completed family-allocation
trial by treatment identity, not the higher-scoring seed. Preserve original
weights, named Adam state/LR, counters, replay entries/RNG and pool identities.
Only future replay sampling ratio changes from0.5 to0; buffer length remains2
and the rolling buffer continues to be populated and serialized. No reset.
Changing to buffer0 would silently drop retained replay/counters on current
resume code and is not the intended experiment.

An isolated SHA-bound in-memory parser guard change allows this combination;
no frozen trainer file changes and no objective or sampler changes. Actual
metrics must record ratio0 and zero new replay rows. Cumulative replay count
must retain its historical value, not be reset. Qualification first checks
syntax/guard scope and real parent replay sampling/RNG preservation with no
hands. A later real-worker smoke must check initial state, current rolling
buffer, Adam updates, assignment replay and managed namespaces before any scale.

If qualified, one primary replay0.5 line and one fresh-only control, both seeds,
with fixed262k then1M additional physical hands and whole-iteration overshoot.
Use explicit-panel paired reporting, preservation plus non-trained opponents,
both seats, own-parent contrasts and wall cost. No Slumbot until a fixed
development calibration is justified. A smoke is mechanics evidence, not a
strength elimination gate. Do not launch production from smoke descendants.
