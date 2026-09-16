# Exact-v6 ChipState Deep CFR adapter smoke

Decision: `ADMIT_BOUNDED_EXACT_V6_NEURAL_REGRET_SMOKE`.

The adapter uses the canonical integer-chip `ChipState`, shared nine-slot
`action_table`, and `apply_incr`; it does not use or modify the rejected legacy
HUNL rules engine. Sixteen unique sampled root deals alternated traverser seats.
They produced 48,016 decision nodes, 5,344 traverser information sets, 42,672
sampled opponent nodes, and 37,352 terminal rollouts at maximum depth 11.

Both traverser buffers contain 2,672 samples. Every encoded state and target is
finite, all illegal-slot targets are exactly zero, both seats were exercised,
and terminal payoffs are expressed in BB from exact zero-sum chip payoffs.
Regression tests additionally prove that changing only unobserved opponent hole
cards leaves the acting player's encoding unchanged, while changing the acting
player's private cards changes it.

Accounting deliberately records zero `environment_training_hands`: this was a
mechanism traversal with fixed passive network weights, not weight optimization.
The root-deal, decision-node, and terminal-rollout counts remain separate.

Next step: run a small matched neural regret optimization with deterministic
seeds and explicit root-deal/node accounting. Admission should require loss and
target health, checkpoint reload parity, behavioral movement away from the
passive initialization, and untouched exact-v6 evaluation against simple fixed
policies before any larger budget.
