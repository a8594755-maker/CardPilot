# Current-regimen representation learning: prospective matched pilot

Main candidate: train the existing full representation and heads. Single major
control: continue heads/critic-only learning. Both static8M Seed1 and Seed3 parents
are mandatory, not selected by their external results. This is real reward-based
learning, not Slumbot-label imitation. The long frozen-policy goal is unchanged.

## Parents and inherited evidence

Use the original and derived artifacts qualified by
`v6-current-kl-scope-transfer-20260905/real_parent_qualification.json` (SHA256
`c35191054e22401c207f3384b851b7c9f5c790500cf8ebdaead12dd0dadebd92`).
Seed1 original SHA41ff38496167424fa71373028e9291a0d8bd595315f7121d8fa303e6b15a3372,
full SHA44d332a0e234b7806933680417095d6d2bcc0daf2779119d5b72bb36ca8c589f.
Seed3 original SHA36aa1d935179570e76499a0a0c1c81ccd75384b0411b9c7d9cca56c9a2c14b69,
full SHA12ac34ea420a6907add175c50e862d8a8f3b1f6e179c80bba9eb9eea60e55d9a.
Original counters8395752/8392377, optimizer moments, replay, RNG and pool history
remain intact. Full-stage1 traces come from the ORIGINAL heads parent directory,
not from the derived-copy directory. New representation Adam states start on their
first gradient. Existing parameter clocks must advance individually; comparing
the global minimum new Adam step to the maximum old head step is invalid.
Earlier unknown interruption tails remain unknown, not new hand credit.

## Fixed allocation and hardware-only preflight

Stage1: add at least262144 actual physical environment hands to EACH arm/seed,
allow only the final complete-update overshoot. Order S1-full,S1-heads,S3-heads,
S3-full. Stage2, if stage1 has no broad collapse and all evidence is valid: each
arm reaches1048576 additional physical hands relative to its original8M parent.
Stage2 order S3-full,S3-heads,S1-heads,S1-full. Do not auto-extend beyond this dose.
Stop naturally at7200s per attempt if necessary; preserve partial evidence and
review an exact-state continuation, never restart an attempt or reset counters.

Before new poker hands, run disposable full-network CUDA forward/backward memory
probes, no optimizer steps or saved updated policy, in descending minibatches
16384,8192,4096. Select the largest passing size with a512MiB auxiliary allocation
and finite gradients. Only CUDA OOM permits trying the next size; other errors
require diagnosis. Use the selected identical size for BOTH arms and seeds, fixed
through both stages. This hardware choice uses no rewards. If smaller than16384,
explicitly report the departure from the preceding training recipe and altered
update frequency; the paired scope contrast still holds batch size fixed. This
probe is not a guarantee of production memory sufficiency. No silent batch retry
after production begins. If4096 cannot fit, stop before training for review.

## Training contract

Unchanged production trainer SHA1b4d23abfa3e0a9c675126fd7183d37b134a2a13253563e990e144cc01a90f8b,
with previously qualified durable45s checkpoint publication wrapper. Physical
200bb v6legacyv4obs, GN/critic_v2/separate preflop, PPO2,targetKL.01, actual restored
Adam LR approximately1e-4, current-to-Standard10 referenceKL1, reference refresh0,
replaydepth2/ratio.5,4096 hands-per-iteration setting,12workers x8envs,
loss-kbest5,25%selfplay,8adaptive opponent groups, original3initial opponents.
Training/worker seeds and lineage IDs remain the original S1/S3 settings.
Fresh managed attempt namespace for EVERY new arm/stage; retain parent namespace
and immutable assignment-replay origin evidence. Statistical worker continuation,
not bitwise worker RNG continuation or matched training decks across arms.
Exact initial model/optimizer/replay/counter/main-RNG/pool audit and trace-prefix
checks are required. Do not modify production or old experiment evidence.
Loss-kbest may legitimately evict any original anchor; reconstruct the actual
score and selection rather than require anchors to remain forever. Report anchor
retention separately from pool correctness. No mandatory heads-only drift audit
for a full-network arm; verify actual parameter scope and use the Standard10
evaluation anchor for capability-preservation evidence.

## Untouched evaluation and decisions

After each stage, four endpoints each face their SAME original8M parent on2048
new common decks per frozen anchor, both seats. Four anchors: standard10,cfr4,
legacy_iter16,legacy_mixed65k with the identical SHA-bound panel in the preceding
S3 reference study. Greedy execution, unchanged physical200bb legacy observation
bridge. Eval seeds: S1stage1/2=20263811/20263812; S3stage1/2=20263831/20263832.
Identical seeds/decks for full and heads within a seed/stage, independently
verified parent rewards.131072 actual internal evaluation hands per stage,
including intentional repeated parent executions. No new Slumbot hands here.
Check deck uniqueness and disjointness against the inventoried prior common-deck
corpus, plus prior stages/seeds. Do not claim every historical corpus is covered.

Report full-minus-heads and each endpoint-minus-parent, per anchor and both seats,
paired deck-mean95% intervals. Both fixed training seeds reported separately;
any two-seed average is exploratory, not a seed-population CI. A stage1 broad
collapse means full-minus-heads upper95%<-25bb100 on at least3/4anchors AND
upper95%<0 on both seats in either seed. Finish both seeds stage1 before this
decision, unless mechanical failure prevents valid completion. If present, review
and stop automatic stage2, not declare all representation learning impossible.
Otherwise complete the fixed stage2 dose despite inconclusive small-sample gains.
At stage2 assess geometric slopes, cross-seed breadth, Standard10 preservation,
actual throughput and proxy limitations before any larger resource commitment.
Previously observed internal/external misalignment and older full-network/low-
temperature negatives are retained. A positive internal pilot alone is not proof
of stronger general poker or authorization for final100k Slumbot qualification.

## Ownership and accounting

Register before memory probes or poker queries. Log exact commands and hashes;
one stage controller owns updates while live. Count actual new physical hands,
transition-bearing hands, no-decision/tails and replay separately. No skipped
indices or inherited parent hands are new training. Keep failures and all raw
evidence. Source-bound reusable process/drain/termination logic is used unchanged;
new scope-aware audits are additive. Finish this same record only after training,
evaluation and evidence analysis, or a genuinely terminal failure decision.
