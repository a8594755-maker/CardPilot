# Fixed 1M boundary decision

All sixteen training/evaluation jobs exited cleanly. Independent terminal review
recomputed the raw contrasts and verified checkpoint/runtime hashes, original
optimizer and replay continuation, raw prefixes, distinct attempt namespaces and
the 32,768 evaluation decks against 845,826 retained rows in 111 files (zero
overlap). This is statistical continuation, not bitwise worker equivalence;
unique training-deck coverage is not proved by physical execution accounting.

Cost: 4,206,408 new physical executions, 3,700,849 transition hands, 503,508
no-decision hands, 2,051 residual worker-tail hands and 6,511,472 replay rows.
Training jobs consumed 7,758.48 seconds; controller elapsed 12,249.25 seconds.
262,144 internal evaluation executions are not independent unique deals and
are not Slumbot hands. Final qualification remains zero.

Mixture minus control pooled bb/100 (conditional paired-deck 95% intervals):

| Seed | Additional 262k | Additional 1M |
|---|---|---|
| 1 | -3.76 [-16.25, 8.73] | -2.11 [-12.97, 8.75] |
| 3 | +1.59 [-13.45, 16.63] | +10.15 [-3.51, 23.80] |

At 1M, own-original-parent changes are control -4.50 and mixture -6.61 for
Seed1, control -5.94 and mixture +4.20 for Seed3; all pooled intervals include
zero. Seed3 treatment/control point improvements cover three anchors and both
seats, but Seed1 only one anchor and one seat. Seed1 legacy_iter16 regression
is an exploratory bucket, not a multiplicity-adjusted causal finding. Positive
absolute anchor scores do not establish improvement over parents or Slumbot.

Classification: valid implemented mechanism, insufficient replicated strength
evidence; not an algorithm-level failure and not proof that more scale cannot
help. No preregistered broad collapse occurred. The apparent treatment/control
slope is encouraging in Seed3 but does not reproduce as own-parent improvement
in Seed1. Do not select only Seed3 or call this a stable stronger model.

Allocation: retain all four endpoints and both doses; do not automatically launch
4M training, another external80k cohort or final100k. Before another substantial
allocation, perform a bounded zero-new-hand audit of retained training metrics
and opponent assignments: realized exposure by opponent/seat, objective/critic
health, and whether endpoint changes reflect actual learning progress or a
stationary/noisy regime. Compare with already completed diagnostics to avoid
rerunning old work. Missing measurements must be reported as missing, not inferred
from losses or KL. Use this evidence to choose bounded unchanged-regimen scale
versus one substantive training intervention, not an unbounded diagnostic chain.

No frozen weights, runtime, raw hands or prior records were altered by review.
