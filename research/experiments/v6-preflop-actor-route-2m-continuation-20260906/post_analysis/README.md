# Prequalified one-shot terminal review

This directory is outside the live controller's frozen dependency set. Its
preparation neither changes the trainer nor writes the experiment logger while
the controller owns it. All below commands/artifacts are deferred attachments to
the SAME record after both controller and helper terminate.

The fixed-stage3 reviewer passed17 tests (qualification.json); the followthrough
passed7 tests (followthrough_qualification.json). Tests used synthetic fixtures,
not new poker hands or current model/evaluation outcomes. The statistical,
state/Adam, gradient-origin and training-health helpers remain the exact earlier
qualified implementations. AST comparisons verify that the raw parser and stage
statistics only change the preregistered cardinalities/evaluation seed binding.
Old experiments, old tests and old completed reviews were not rerun.

Actual preparation/launch commands:

    python -B research/experiments/v6-preflop-actor-route-2m-continuation-20260906/post_analysis/qualify_review.py
    python -B research/experiments/v6-preflop-actor-route-2m-continuation-20260906/post_analysis/qualify_followthrough.py
    powershell -NoProfile -ExecutionPolicy Bypass -File research/experiments/v6-preflop-actor-route-2m-continuation-20260906/post_analysis/launch_followthrough.ps1

The two qualification JSON reports preserve actual outer/nested pytest argv,
stdout/stderr, wall time, source hashes and test XML bindings. Followthrough
execution preserves its own actual argv and will preserve the review child's
exact argv/identity/exit. Attach these actual commands, not invented reruns.

Controller PID29304/create1788713773.5332272 is the only training/evaluation
logger owner. Helper launcher returned PID50980; use the helper's own
followthrough_execution.json create_time for exact-identity checks. The helper
waits on the original controller, treats observation failures as uncertainty,
and never restarts a process. Once the controller is absent it requires all8
jobs cleanly terminal, no controller error, unchanged source bindings, fixed
2M boundary and no earlier review output before launching terminal_review.py
exactly once. Failure or a partial boundary is preserved without retry.

Do NOT manually run a competing reviewer while this helper is live or after
post_terminal_review.json exists. A running status file alone is not liveness.
On normal completion wait for both owners and the reviewer child to be terminal,
read the preserved result, analyze both seeds/arms, compare with the existing1M
curve without rerunning old poker, then finish this SAME experiment through the
logger. All4 endpoints still require separately preregistered external calibration
before any larger allocation; internal scores cannot promote a model or satisfy
the Slumbot goal. Preserve unknown earlier lineage crash tails as unknown.

The reviewer independently reconstructs physical/transition/no-decision/tail
and replay accounting; verifies actual initial model/optimizer/replay/pool/RNG
restoration and final86-parameter Adam clocks; checks route origin, fresh attempt
namespaces, raw log prefixes and all recorded process exits; reaggregates4,096
unique common-deck identities /32,768 executions with original common parents,
both seats and four anchors; checks prior-corpus overlap and frozen hashes.
It writes no logger state or new poker requests. Its intervals remain conditional
deck-noise estimates, not seed-population inference or proof of general strength.

At closure also attach launch_observations.md and its corrected explicit-ISO
audit command; do not relabel the earlier348-record audit as a clean prelaunch
one-record audit. A separate explicit-ISO check passed one record/zero warnings.
