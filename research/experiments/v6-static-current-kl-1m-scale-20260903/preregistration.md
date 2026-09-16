# Static current-KL 262k-to-1M scale preregistration

The independent high-precision confirmation admitted the static
`KL(current || initial Standard10)` method to a one-million-hand scale test.
Across 294,912 prior-plus-fresh evaluation hands, all three 65k-to-262k slopes
were positive (+1.054, +0.613, +0.780 bb/100), seeds 2 and 3 passed simultaneous
both-seat and three-anchor breadth, and only one fresh cohort showed broad
collapse.  The all-seed pooled slope (+0.816 bb/100) remained uncertain, so this
is evidence for more training rather than a benchmark claim.

## Exact continuation contract

The three frozen 262k parents have SHA256s
`1e9cda7fb9793554d767f36957df9c730baab32e1d2cd5f972497ab25d044e43`,
`2ac666344ad73b6d4a3a36cdfffed0e5f5cc9b4c8c40b7dc6227a5fc6803d8d6`,
and `ce9a7ad4769cb1fca56231239866f7a478eef9958416ca53cf8c3e03c6f1c236`.
Continuation preserves model, optimizer and its current learning rate,
two-iteration complete-hand replay, loss-K-best active weights and history,
adaptive league, counters, run IDs, and hash-chained assignment RNG evidence.
The repaired pool loader advances future candidate IDs beyond every serialized
history ID; existing duplicated rejected IDs remain documented and full
`(id, iteration, hands)` refs remain unique.

Static Standard10 reference SHA256
`91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`
and `current_to_reference` direction remain fixed with refresh disabled.  New
fixed deal streams begin at 30.3M, 31.3M, and 32.3M, beyond prior conservative
first-unused bounds.  Each seed targets at least 1,048,576 cumulative physical
environment hands.  Only the new suffix counts as new training work.  Archives
are written at global iterations 64, 128, and 192.

## Evaluation and scale decision

All three frozen 262k parents and 1M endpoints will be compared on new
common-deck deals against Standard10, CFR4, legacy iter16, and legacy mixed65k
in both seats, plus 20,000-state Standard10 drift per endpoint.  No endpoint is
selected from training rewards.

Promotion beyond 1M requires positive 262k-to-1M slopes in at least two seeds,
positive median slope, at least two seeds with both seats nonnegative and at
least three nonnegative anchor slopes, complete causal/evidence integrity, and
mean TV at most 0.08 plus greedy disagreement at most 0.12 in every seed.
Clear rejection requires replicated broad proxy reversal in at least two seeds,
causal mechanics failure, or catastrophic drift.  Other mixed results mean
insufficient evidence.  Prior integrated lineages improved through 1M but
reversed from 1M to 2M, so no continuation beyond 1M occurs before this gate.
No Slumbot calls are authorized by this training run alone.
