# Standard10 weight-space opponent population smoke

The frozen raw parent is the best learned checkpoint observed under generic
greedy Slumbot execution (-9.4188 bb/100 on fresh 5k, with a wide interval).
Standard10 remains the mature external reference: -11.4275 bb/100 under the
historical greedy contract but -48.9778 under strict sampled execution.  The
older single imitation-teacher result (about -18.5025 on fresh 20k) is negative
evidence, so this experiment does not use imitation targets or hero-side rules.

Create a learned opponent population by copying the exact Standard10 network,
explicitly rebinding the copies to the v6 contract, and adding deterministic
Gaussian perturbations to exactly these tensors:

- `policy_head.weight`, `policy_head.bias`
- `preflop_policy_head.weight`, `preflop_policy_head.bias`

Every other model tensor must remain bitwise equal to Standard10.  For each
actor tensor, noise standard deviation is the tensor's own finite sample
standard deviation times the selected scale.  Select one scale from
`[0.25, 0.5, 1.0, 2.0]` using only a fixed outcome-free synthetic state cohort:
choose the scale whose median mean total variation over calibration seeds
2026110001--2026110003 is closest to 0.12.  Poker returns, Slumbot data, and
downstream evaluation cannot affect this choice.

Training seeds are 2026110101--2026110105.  Untouched evaluation seeds are
2026110201--2026110205.  They are disjoint and fixed before generation.  Resume
the exact raw parent SHA256
`9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`
without resetting optimizer, optimizer LR, hand counters, EMA, or lineage.
Continue the fixed deal stream at physical hand 132553 until target 198089,
which is 65536 additional completed environment hands before bounded shutdown
overshoot.  Use LR inherited from the optimizer (1e-5), source KL 0.1 to the
exact parent, all-policy-heads-only training, sampled rollouts, self-play 0.25,
five frozen perturbed opponents, per-group adaptive assignment, seed 20261103,
worker seed base 2026110300, and no replay, imitation, privileged critic,
benchmark rule, or endpoint selection.

After the endpoint is frozen and the training session audit passes, evaluate
the unchanged parent and candidate against all five untouched perturbations in
greedy mode with 1024 mirrored pairs per cell and common seed 20261104.  The
primary contrast is candidate minus parent averaged per deck over the five
anchors.  Also replay both policies outcome-free on every decision from the
already audited parent generic-greedy fresh5k Slumbot cohort.

The experiment passes only if all evidence checks pass, the aggregate paired
95% CI lower bound is above zero, at least four of five per-anchor point
contrasts are positive, parent-state mean total variation is at most 0.02, and
parent-state greedy disagreement is at most 0.02.  A pass permits only a new,
separately logged fresh5k generic-greedy Slumbot gate.  A failure stops this
population route before new Slumbot hands.  No result here can satisfy the Goal.
