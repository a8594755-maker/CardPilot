# Parent-KL conservative actor tail

Resume the externally strongest learned parent SHA256
`9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`
with its exact ten Adam states, inherited 1e-5 LR, counters, actor EMA, adaptive
league, assignment RNG, and a fixed-deal start index of 132,553.  Continue only
to at least 196,608 physical lineage hands (about 64k new hands).  Keep the
original five opponents, seeds, all-policy-head scope, sampled rollout, entropy,
critic, PPO, and source architecture unchanged.

The sole learning intervention is policy preservation: replace the Standard10
KL reference at coefficient 0.01 with the exact parent actor itself at coefficient
0.1.  This tests whether useful league learning remains possible inside a tighter
trust region around the best external learned policy.  No replay, imitation,
Slumbot outcome labels, or benchmark-specific action rule is allowed.

Require continuous physical/legacy metrics, optimizer and LR preservation,
disjoint fixed deals, a passing fixed-pool/session audit, and exact hashes.  Freeze
the raw treatment endpoint.  Evaluate source, parent, and treatment with generic
greedy execution against the five training opponents using 1,024 common mirrored
pairs per cell, seed 20261101.  This is a mechanism gate, not held-out evidence.

Call the treatment internally promising only if treatment-minus-parent five-
anchor paired mean and raw 95% CI lower bound are positive, treatment-minus-source
is positive, and at least 3/5 per-anchor treatment-minus-parent points are
positive.  No Slumbot hands are allocated here; a passing endpoint first requires
an outcome-free parent-drift check in a separate record.

