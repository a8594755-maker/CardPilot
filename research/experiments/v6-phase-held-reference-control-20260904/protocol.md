# One phase-held-reference control after static4M external calibration

Prospective protocol, before any hands in this experiment. Keep one static main comparator and one reference-regimen treatment; do not open a temperature, teacher-imitation, full-network or opponent-distribution sweep.

## Question and scope

The original incident-unaffected Seed1 4M endpoint was clearly negative in fixed20k external play, while its2M-to-4M internal slope was uncertain. Compare continued static Standard10 regularization against a reference that starts at the current4M actor and remains fixed for substantial inner phases before refreshing. This tests a reference-regimen package, including initial rebasing, not the isolated causal effect of refresh cadence. The treatment's initial reference differs from the unchanged static comparator; do not claim otherwise.

Both arms start from the exact same original Seed1 checkpoint SHA2567ea4d74d0fcf881c75c4c99bdc0cbe84f82a55001ba277c01aafec6dc5a98f3f, iteration882, physical4,197,976, transition-bearing3,632,466. Preserve weights, optimizer/LR, replay entries/RNG/counts, historical league and assignment evidence. Do not use the GPU diagnostic descendants or reset counters. The static arm keeps explicit Standard10 reference SHA91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428. The treatment uses the trainer's existing current-actor moving-reference initialization and refreshes every256 completed PPO calls. Subsequent treatment resumes must restore the serialized reference and its activation/update/round counters, never initialize it again.

Other training settings are identical to the qualified current recipe:12 workers, multi8,4096 transition-bearing hands/update, all policy heads plus critic_v2, frozen trunk, sampled heroT1, KL(current||reference) coefficient1, preserved optimizerLR1e-4, PPO2 epochs,targetKL.01,minibatch16384,replay depth2/ratio.5,loss-K-best5,25% current self-play, eight adaptive groups and the same three training anchors. This is a local regularized learned-policy control, not full-network AlphaHoldem or faithful joint-policy, long-inner-loop NashPG reproduction.

256 updates is deliberately much slower than the already-tested interval1 recipe: approximately1.2M physical executions per phase at the recent hand/update ratio, with actual phase lengths measured rather than assumed. At the maximum additional4M budget the treatment should cross multiple phase boundaries. No inference about eventual convergence follows from merely crossing those boundaries.

## Budget and order

Fixed Seed1 pilot. Stage1 targets original physical count+2,097,152 (6,295,128); stage2 targets original+4,194,304 (8,392,280), each arm. Report boundary overshoot. Maximum planned new executions8,388,608 across both arms, plus overshoot, not a new8M policy trained from zero. Order: static1,moving1, evaluate stage1, moving2,static2,evaluate stage2. Training runs are sequential on the GPU. This ordered pilot is not independent-seed replication; reserve original Seed3 for an independent replication if the direction merits it, never the incident-affected Seed2.

Every launch reserves a fresh durable attempt namespace before workers. Training arms share initial state and seeds but not deterministic decks across namespaces; label statistically matched initialization, not common-deck or bitwise paired training. Preserve complete raw prefixes and serialized optimizer/replay. Record physical executions, no-decision counts, transition-bearing hands, replay rows, unknown crash suffixes and worker tails separately. Use atomic completed-update checkpoints and preserve all interrupted attempts.

Per-attempt runtime guard7200s. A natural below-target boundary is a safe interruption, not a failed algorithm or permission to redo hands. Preserve it and stop the controller for researcher cost/resume review; no automatic restart or overwrite. Include startup/save/shutdown in realized wall cost; the short GPU speedup is not a guarantee of a multi-hour rate. No paid compute.

## Frozen evaluations

At each completed stage evaluate both endpoints versus the same frozen4M parent on the same fresh common-deck seed (20263411 for stage1,20263412 for stage2),2048 pairs per each of Standard10,CFR4,legacy_iter16,legacy_mixed65k, both seats and greedy execution. Reuse the existing paired evaluator without changing its poker contract. This executes65,536 physical internal hands/stage,131,072 total. The4M-parent portions intentionally repeat across the two paired comparisons; do not count them as independent samples in the derived moving-minus-static difference. Compute that difference by joining raw anchor/deck/seat identities and subtracting the two deltas; require exact repeated-parent rewards and hashes. Check earlier-corpus deck disjointness and account for the intentional within-stage pairing.

Retain absolute anchor results, each endpoint-minus4M slope, moving-minus-static contrasts, both seats, cross-anchor breadth and conditional paired CIs. The four anchors share some lineage/representation and do not by themselves establish heterogeneous population generalization.

At each stage run20,000 Standard10-parent drift states per arm, using the same state seed within stage (20263421/20263422), total80,000 offline states. Report scope, meanTV and greedy disagreement without interpreting preservation as strength.

## Decision rules

Stop and preserve on nonfinite training, wrong updates/counters/namespace/replay/reference state, source/hash drift, incomplete hand evidence or surviving worker ownership. Before stage2, an unambiguous broad treatment collapse can terminate further treatment allocation: moving-minus-static upper95% bound below-25bb/100 in at least3/4 anchors AND negative upper95% bounds in both seats. This is a predeclared practical-risk rule, not a generic algorithm impossibility claim. Source drift alone, a few negative point estimates, or CIs crossing zero are not reasons to terminate this planned geometric test.

Otherwise complete stage2 despite inconclusive early point estimates. Do not promote from this single seed or use the old invalid public-behavior-clone proxy. Following valid completion, use a separately fixed external development comparison of both endpoints regardless of internal rank; do not pick a lucky seed or5k winner. A repeatable broad learning slope, source capability, external alignment and measured cost can justify independent Seed3 replication and later larger scale even while absolute scores remain negative. A clear external reversal or collapse changes allocation. Final >=100k frozen-policy blind qualification is a separate prospective experiment; nothing here marks the goal complete.

## Implementation handoff

Build a one-owner controller around the existing qualified GPU command/verification helpers and paired evaluator, with per-stage frozen artifacts, real resume checks and live accounting. Existing helpers can be reused as functions, not by rerunning their completed diagnostic. Extend verification to moving-reference cadence/state and capped league-history windows. Preregistered first command: `python research/experiments/v6-phase-held-reference-control-20260904/run_control.py --preflight-only`. Training cannot launch until the controller and these checks exist and pass. This document is a plan, not a claim of started training.
