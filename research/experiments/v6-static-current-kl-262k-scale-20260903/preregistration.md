# Static current-KL 65k-to-262k scale preregistration

This experiment continues only the three static-reference arms admitted by
`v6-nashpg-moving-reference-geometric-20260903`.  It is a scale test of
`KL(current || initial Standard10)`, not a retry of refresh-after-every-update.

## Frozen continuation contract

Each parent checkpoint, staged metric prefix, and staged opponent-assignment
prefix is SHA256-pinned.  Continuation retains the parent run ID, optimizer and
its current learning rate, serialized two-iteration complete-hand replay,
loss-K-best pool, adaptive-league state, inherited physical/transition hand
counters, and assignment RNG reconstructed from the hash-chained evidence.
The source-policy reference is explicitly pinned to Standard10 SHA256
`91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`;
reference refresh remains disabled.

The fixed training streams move from 30M/31M/32M to disjoint 30.1M/31.1M/32.1M
ranges.  Gaps are intentional.  No earlier deal indices are reused.  Each
lineage targets at least 262,144 cumulative actual environment hands.  Only the
new suffix counts as new training work.

## Evaluation and decision

The frozen 65k parent and frozen 262k endpoint for each seed will use untouched
common decks against Standard10, CFR4, legacy iter16, and legacy mixed65k in
both seats.  Outcome-blind 20,000-state Standard10 drift audits are required.

Promotion beyond this scale requires positive 65k-to-262k pooled slopes in at
least two of three seeds, positive median slope, at least two seeds with both
pooled seats nonnegative and at least three of four anchor slopes nonnegative,
complete mechanical/evidence integrity, and final mean TV at most 0.08 plus
greedy disagreement at most 0.12 for every seed.  Significance and positive
absolute Slumbot score are not required at 262k.

Clear rejection requires a replicated broad proxy reversal in at least two
seeds (both seats negative and at least three of four anchors negative), a
mechanism/accounting failure, or catastrophic Standard10 drift.  Other noisy or
mixed results are insufficient scale.  No Slumbot calls are authorized here.

