# Current full-network actor objective probe

Question: do actual current-regimen PPO minibatches show reference-gradient
domination/cancellation warranting an objective change, or leave scale as the
unresolved question? Retained mixture diagnostics showed no update shutdown;
latest full-network replay endpoint logs have empty gradient diagnostics.
Old August/early-September gradient experiments concerned different training
states/contracts and do not identify the current actor update geometry.

One bounded probe, seeds1/3 exact fresh-only-trial replay-control final parents.
Preserve weights, all Adam state/LR, replay entries/RNG, reference and opponent
allocation. Reuse existing frozen trainer and managed namespace lifecycle.
Only enable gradient-diagnostic-minibatches=1. Fixed16384 additional physical
hands per seed (whole-iteration overshoot reported), no automatic retries.
These are real additional training executions, not final qualification or
strength evidence. Save outputs separately; no changes to original checkpoints.

Report actual diagnostic fields, per-seed minibatch variability, update integrity,
physical/transition/replay counts and wall cost. Do not infer gradient dominance
from loss magnitudes. A single endpoint/cohort is only local mechanistic evidence;
do not change KL solely because its gradient norm is larger. If fields do not
cover the proposed mechanism, state it rather than inventing a causal conclusion.
No opponent-seat diagnostics or extra objective enabled. No Slumbot labels.

After completion decide one main learned-weight path; do not start a diagnostic
parameter sweep. Original parents remain available; probe descendants are not
silently substituted into future preregistered production continuations.
