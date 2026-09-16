# Full-network continued learning: original rate versus half-rate control

Registered before new poker hands. This continues the current primary full-network
family. One major control changes only actual restored Adam LR by0.5. Both retained
Seed1/Seed3 endpoints are mandatory. No selected lucky seed, reset, heads-only third
training family, temperature scan, Slumbot labels or benchmark-specific actions.

## Fixed endpoints and qualification

Original full parents are the representation pilot's seed1_full_stage2/latest.pt
SHA3d7914ba11c5deaf9725afbd59f4a805fd7f0bead37a2c8eddb6bffa9038b8f3,
physical9445556/iteration1992 and seed3_full_stage2/latest.pt
SHA0a5e09c32dbdc098215fb29221a7f497a95755e2c5273060c8c01924d92d5cc0,
physical9441064/iteration1993. Half-rate copies are qualified by
v6-full-half-rate-qualification-20260905/qualification.json
SHAafe2955b7a5fd1d257cf0dbd66a86d703f9023315034855e7449515f33fa028b:
Seed1d9e029c30e58a9d0e3ca81f83bb5ee54103b7044bde359019b4b616384feacd7,
Seed3f3c2c58a8427896042d4dc0ea90ecc7eea9e5f1952018437f10c7e5ad9e8e3eb.
All86 parameter Adam states, weights, replay and counters are retained. The copies
are unstepped. Prior incomplete/unknown lineage crash tails remain recorded, not
invented new hand credit. Do not relabel older heads-only training as full training.

## Fixed training and budget

Arm names full=unchanged original actual LR approximately1e-4;
half=full-network comparator actual LR approximately5e-5. Both train all86 tensors.
Stage1+262144 physical hands per arm/seed from current parents, order
S1-full,S1-half,S3-half,S3-full. Stage2 cumulative+1048576 from the same current
parents, order S3-full,S3-half,S1-half,S1-full. Only final update-boundary overshoot
is allowed. This gives the original full learner about2.1M total representation
training hands. Four-branch new budget is4194304 plus boundary overshoots, not
one policy trained on that sum.7200s per job safe boundary; no automatic retry.

Unchanged production train_v5.py SHA1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b;
reuse qualified durable45s checkpoint publication. Physical200bb v6legacyv4obs,
GN/critic_v2/separate preflop, PPO2,targetKL.01, sourceKL1 current_to_reference,
fixed Standard10/refresh0, batch16384, replaydepth2/ratio.5,4096hands-per-iteration,
12workers x8envs, loss-kbest5,25%selfplay,8adaptive groups, same3initial opponents.
Hero samplingT1 for training; greedy execution for frozen evaluation. Preserve
original train/worker seeds,lineage IDs and fixed start indices. Every new arm and
stage uses an exclusive managed attempt namespace: statistical worker continuation,
not identical training trajectories or bitwise worker RNG resumption.

Reuse the prior same-regimen batch16384 CUDA memory qualification and eight actual
completed training jobs, rather than rerunning disposable memory probes. Actual
memory failures still stop without silent batch substitution or retry.
Each launch must capture and audit the real initial resumed checkpoint before
admitting subsequent jobs. Verify restored model/optimizer group LR and moments,
replay/counter/mainRNG/pool and static reference; preserve original trace prefixes.
Stage1 prefixes for BOTH arms come from original full parent directories, never
the derived-copy directory. Every per-parameter clock must advance from its own
history; no new Adam state IDs are expected. Reconstruct loss-kbest history and
assignments; report anchor retention, do not enforce non-existent retention rules.

## Untouched evaluation and scaling gates

At each stage compare each endpoint with its SAME current parent on2048 fresh
common decks per anchor, both seats. Four frozen anchors/SHA bindings reused from
representation pilot: Standard10,CFR4,legacy_iter16,mixed65k. Standard10 is also a
training reference, so do not call every anchor an unseen opponent. Same decks and
exact parent rewards across full/half; evaluation seeds S1stage1/2=20263911/20263912,
S3stage1/2=20263931/20263932. No earlier deck corpus reuse; verify inventoried raw
corpus and cross-stage/seed disjointness.131072 actual executions/stage,16384 unique
decks/stage. Paired repeated-parent executions are intentional, not independent
samples. No Slumbot or final qualification hands in this study.

Report half-minus-full and each endpoint-minus-parent; pooled, per-anchor and
per-seat paired-deck nominal95% intervals. Seeds remain separate; any average is
exploratory, not a seed-population CI. Report realized optimizer steps, actual
learning rates, PPO KL/early stops and reference KL, not just nominal LR.

After all stage1 cells, stop automatic stage2 for review if EITHER arm versus
parent OR half-versus-full has upper95%<-25bb100 on>=3of4anchors AND upper95%<0
on both seats in either seed. This severe broad-collapse gate is a safety boundary,
not proof one method can never work. Inconclusive early gain alone does not stop
the fixed stage2 allocation. Any mechanics/source/evidence failure stops at its
safe boundary with outputs intact; never silently retry/restart or change dose.

After stage2 require human-model research analysis of geometric slope, multiseed
and both-seat breadth, Standard10 preservation and cost before any larger scale
or external development test. Prior internal/external misranking, full-network
and sampled/temperature negatives remain relevant. Neither lower KL nor positive
internal point estimates imply stronger general play. No automatic16M/paper-scale
or final blind Slumbot test. Final qualification still needs a preregistered whole
frozen policy, fresh cohort and valid statistical stopping design.

## Ownership and evidence

One controller owns this record and frozen sources while live. Source-bound
process/drain/termination, initial-state, optimizer, pool and raw-deck helpers are
reused unchanged. The reused inspection module's dose and initial physical count
constants are explicitly rebound in this process only; its source and old record
are never edited. New arm names and record paths stay in this controller.
Update real counters while running; preserve exact commands/hashes, all namespaces,
trace prefixes and terminal identities. Log physical hands, trainable-transition
hands, no-decision/tail hands and replay rows separately. Finish this same record
only after terminal training/evaluation and research review or a terminal failure.
