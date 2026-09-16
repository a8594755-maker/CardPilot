# Matched causal-TCN reward pilot

The causal-TCN smoke completed 35,294 physical v6 hands with all health gates
passing and scored -7.8024 bb/100 against untouched source anchor0, above its
fixed -20 bb/100 admission threshold. This admits one matched scale test; it is
not external-strength evidence.

Train two policies independently from the same legacy Standard10 SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.
Both arms use at least 262,144 physical environment hands, workers12/multi8,
seed20261037/worker2026103700, the same fixed deal stream, five frozen learned
anchors, adaptive opponent league, sampled hero and selfplay0.25, lr3e-5, PPO2,
target-KL0.01, advantage clip3, source KL0.01, entropy0.005/floor0.05, and fresh
optimizer/critic/counters. Control updates the existing preflop/postflop heads and
critic only. Treatment updates the causal token projection, three causal dilated
convolutions, normalization, two seat residual experts, and critic only. No
replay, continuation, endpoint selection, or smoke checkpoint reuse.

Require exact physical-hand accounting, five-opponent assignment provenance,
finite metrics, checkpoint architecture/optimizer/frozen-source scope, session
audit, code snapshots and hashes. Freeze both terminal checkpoints.

Evaluate frozen source, control, and treatment independently against each of the
same five untouched anchors using 4,096 mirrored pairs per cell and common seed
20261038/decks: 15 cells, 122,880 evaluation hands. Primary estimand is the
per-deck average treatment-control contrast over five anchors. The gate passes
only when its 95% CI lower bound is above zero, the analogous treatment-source
CI lower bound is above zero, at least 3/5 per-anchor treatment-control point
estimates are positive, and all evidence gates pass. Passing admits an independent
training-seed confirmation before external testing. Failure closes sequence
residual variants and redirects to centralized-critic/EMA actor-critic work.
Slumbot hands=0.
