# Frozen sampled regularized-policy external development calibration

Evaluate both retained seeds, parent versus final 65,536-new-hand regularized
endpoint, using the four deploy-only exports and exact SHA256 in protocol.py.
No endpoint selection, weight updates, Slumbot action-label learning or special
action rules. This is development calibration, not final acceptance. Internal
confirmation was inconclusive; this run tests external alignment, not a presumed
gain. Parent comparisons avoid mistaking deterioration in a short-run training
control for improvement beyond the starting policy.

Each policy completes eight new sessions of 2,500 hands (20,000 per policy,
80,000 total). Four balanced waves have two sessions per policy; rotate starting
policy by wave. CPU sampled execution, temperature 1, legacy-v4 observations
bridged to physical v6 200bb rules. Full identifiers/seeds are in protocol.schedule.
Seeds control policy draws, not server deals; samples are not paired deals.
Freeze runtime, package versions, model exports, source hashes, exact commands
and prior-session inventory before the first server request.

No efficacy peeking, early success stopping, session replacement or repeat on
failure. On technical failure drain already-started sessions, start no new wave,
preserve all journals and report incomplete evidence. In-flight requests must not
be retried through an invented new session. Do not restart a missing controller
without reconciling child identities and durable request/hand evidence.

Primary family: four absolute means plus two within-seed candidate-minus-parent
contrasts. Report raw bb/100 and ordinary 95% intervals as well as Bonferroni
six-quantity intervals, independent-session t/Welch and wave sensitivity using
the retained four-policy statistics implementation. Report both seats separately
as descriptive results. No pooled four-policy result is a frozen-policy score.
The historical -11.4275 Standard10 greedy score is context, not a matched sampled
control; do not infer sampled superiority from a greedy baseline delta.

Require full decision/model/uniform replay, exact model and execution identity,
terminal chips-to-bb checks, all 32 planned session IDs and counts, token-chain
disjointness across policies and recorded prior evidence, and visible-stream
checks. Empirical independence checks cannot prove server RNG independence;
unreadable prior evidence must be disclosed, not treated as clean.

Resource decision: replicated candidate-parent direction, interval width, seat
breadth, internal/external agreement and measured training throughput determine
whether to allocate geometric continuation with broader opponents. Inconclusive
65k training is not mechanism failure. No automatic paper-scale allocation or
formal 100k acceptance run follows merely from one positive point estimate.
