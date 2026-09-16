# Static current-KL 262k independent fresh confirmation preregistration

This is a zero-training, zero-Slumbot confirmation of the already frozen
65k-to-262k endpoints from `v6-static-current-kl-262k-scale-20260903`.  It is
motivated by mixed rather than negative mechanism evidence: the first cohort
had positive slopes in two of three seeds and positive median/combined slopes,
but only one seed passed the simultaneous both-seat and three-anchor breadth
gate.

## Frozen inputs and untouched design

The three parent SHA256s are `8b92b254396156d3e65833725e03b2f5ba30ae6aa9906c688b15aa5b856c8238`,
`690c2e9e614b8f7f86408c0d8142dd7d3b3a42dcda31df79107068197be658a7`,
and `ba6effa3ca20cccf371eef6d0ee80f93f7334e2622bc04920c932493d4ec3af9`.
The corresponding 262k endpoint SHA256s are
`1e9cda7fb9793554d767f36957df9c730baab32e1d2cd5f972497ab25d044e43`,
`2ac666344ad73b6d4a3a36cdfffed0e5f5cc9b4c8c40b7dc6227a5fc6803d8d6`,
and `ce9a7ad4769cb1fca56231239866f7a478eef9958416ca53cf8c3e03c6f1c236`.

Each seed uses 4,096 wholly new common-deck pairs per each of Standard10,
CFR4, legacy iter16, and legacy mixed65k, in both seats, under frozen greedy
legacy-v4 observation execution.  Evaluation seeds are 20263061, 20263062,
and 20263063.  This produces 65,536 hands per training seed and 196,608 total.
No sample-size adaptation, endpoint selection, or partial-result stopping is
allowed.

## Decision gates

The fresh cohort supports promotion to a 1M-scale continuation only if all of
the following hold: fresh slopes are positive in at least two of three seeds;
the fresh median slope is positive; after pooling the prior and fresh raw rows,
at least two seeds have nonnegative slopes in both seats and on at least three
of four anchors; the all-seed pooled slope is positive; all raw hashes, row
counts, frozen checkpoint relations, deck uniqueness, and evaluation seeds
pass.  Statistical significance is informative but not required at this
scale.

A clear method rejection requires fresh broad collapse in at least two seeds
(both seats negative and at least three anchors negative) or a causal integrity
failure.  Other outcomes remain insufficient evidence and do not imply that
training at 262k hands disproves a long-horizon method.  The candidate-ID reuse
found in the parent training is a documented noncausal provenance limitation;
the trainer is repaired for future continuations.  No Slumbot calls are
authorized.
