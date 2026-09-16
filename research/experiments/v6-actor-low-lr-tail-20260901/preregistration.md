# Actor-head low-LR convergence tail

The externally strongest learned candidate so far is the raw actor endpoint from
`v6-actor-ema-terminal-smoke-20260831`: generic greedy deployment scored
-9.4188 bb/100 over a fresh 5,000-hand Slumbot pilot, with a wide interval that
crossed zero.  Earlier full-network 265k/1m scale-ups transferred badly, while
the raw actor run ended with positive league reward, a 1e-5 Adam learning rate,
and only 132,553 completed physical environment hands.  This experiment tests
one deeper-convergence control without changing the learned-policy objective.

Resume the exact raw checkpoint SHA256
`9fd38ad30ba25f46a80d2a103b55bb5a64affb7979a2fa47504cc187d38a2bf4`.
Preserve model, Adam moments, inherited 1e-5 optimizer LR, legacy training-hand
counter, actor EMA state, five-member adaptive league state, and the verified
assignment RNG chain.  Copy the prior run evidence into a new experiment-owned
run directory, then append to it.  Keep all original configuration and seeds.
Use fixed-deal start index 132,553 so every worker/environment deck index in the
tail is disjoint from the entire earlier physical prefix.  Stop at at least
262,144 completed physical lineage hands.  Replay is disabled, so there is no
ephemeral buffer boundary.

Freeze the raw tail endpoint.  Require contiguous metrics from iteration 1,
strictly increasing physical accounting, inherited optimizer step counts and
LR, exact frozen input hashes, a passing fixed-pool/session audit, and no resets.
Then evaluate source, parent, and tail under generic greedy execution against
the same five league members, 2,048 mirrored pairs per cell with common seed
20261101.  This matrix is only a convergence/mechanism check because all five
opponents participated in training; it is not held-out generalization evidence.

Admit one independent fresh 5,000-hand greedy Slumbot pilot only if tail-minus-
parent five-anchor paired mean is positive with raw 95% CI lower bound above
zero, tail-minus-source mean is positive, at least 3/5 per-anchor tail-minus-
parent point estimates are positive, and every integrity gate passes.  Otherwise
close as not promising with zero Slumbot hands.  No old or current Slumbot hands
are pooled, and neither endpoint can satisfy the 100k Goal in this experiment.

