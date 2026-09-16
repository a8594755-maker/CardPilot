# Static current-KL 2M-to-4M scale preregistration

## Rationale

The exact-state 1M-to-2M experiment passed its preregistered geometric gate:
Seed2 and Seed3 had positive pooled slopes (+1.663 and +0.134 bb/100), the
median slope was positive, only Seed1 showed a broad reversal, and all training,
deck, session-independence, and Standard10 drift checks passed. The combined
slope remained uncertain and slightly negative (-1.137 bb/100, 95% CI
[-4.604, +2.329]); no seed met the stricter breadth-positive criterion, and the
combined seat-1 slope was significantly negative. Thus 4M is one further
geometric observation of a mechanically sound learned-policy method, not a
claim of established poker strength and not an automatic commitment to 8M.

This experiment consumes no Slumbot hands. Existing external results are used
only as context: Standard10's historical greedy execution is the strongest
mature external reference, while sampled execution is materially weaker, so
execution contracts must remain explicit. No Slumbot actions or outcomes are
used as training labels and no benchmark-specific rules are added.

## Exact continuation contract

The frozen 2M parent checkpoint SHA256 values are:

- seed1: `fba34e5690efc7faa6747adb84d29ff576382711dfcfee885c4728a67248868f`
- seed2: `82f21bf84eb8c7acf90ff64321e17d79f467f6fa5aa8adbbe6ddcf09bb4514fe`
- seed3: `3e24831fc240e26bafe5389dd84b0f65d00f283de74f1580a2b86ae67ce6a7b0`

Each continuation preserves model weights, optimizer and current learning rate,
serialized two-iteration complete-hand replay and replay RNG, loss-K-best pool
state and candidate history, adaptive-league state, run ID, all transition and
physical counters, and the hash-chained opponent-assignment evidence. The
static reference remains Standard10 SHA256
`91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`
with coefficient 1, direction `current_to_reference`, and no refresh.

The training configuration remains unchanged: physical-v6/legacy-v4
observation bridge, 12 workers, 4096 hands/update, sampled hero execution, all
policy heads plus critic-v2, PPO epochs 2, target-KL 0.01, preserved LR 1e-4,
entropy coefficient 0.005/floor 0.05, 25% self-play, adaptive loss-K-best
league, replay ratio 0.5, and fixed training deal streams. New continuation
deal starts are 37.3M, 38.3M, and 39.3M; the staging tool must prove each is
beyond the parent session's first-unused upper bound. Only physical hands after
the frozen 2M parent counter count as new environment training hands.

The target is at least 4,194,304 cumulative physical environment hands per
seed. Planned minimum new hands are 2,096,948, 2,094,518, and 2,094,644,
respectively (6,286,110 total); normal final-update overshoot is counted rather
than discarded.

## Evaluation and decision gate

After all three endpoints finish, compare each frozen 2M parent to its 4M
endpoint on 32,768 new common-deck physical hands against Standard10, CFR4,
legacy iter16, and legacy mixed65k, in both seats. Use independent evaluation
seeds 20263281-20263283 and require raw deck evidence to be unique and disjoint
from all earlier static-current-KL evaluation corpora. Audit 20,000 new offline
Standard10 states per endpoint with seeds 20263291-20263293. No checkpoint may
be selected from training reward or from these evaluation results.

Promote to 8M only if all evidence and mechanics checks pass, mean TV remains
below 0.08, greedy disagreement remains below 0.12, at least two seeds have
positive 2M-to-4M pooled slopes, the median slope is positive, fewer than two
seeds show broad reversal (both seats negative or at least three of four anchor
slopes negative), the combined slope is positive, and breadth improves through
at least one breadth-positive seed or absence of a significantly negative
combined seat slope. If the original directional gate passes but this stronger
breadth gate does not, stop at a safe diagnostic point rather than scaling
automatically. Replicated broad reversal, catastrophic drift, or causal
mechanics/evidence failure rejects this continuation. Other mixed results are
insufficient-scale-or-mechanism evidence, not proof that long-horizon learning
cannot work.
