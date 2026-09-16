# Standard10-prior residual-regret smoke analysis

The registered eight-root mechanism run completed without changing the frozen
Standard10 checkpoint.  Across 23,476 exact-v6 decision nodes it populated both
seat/iteration buffers, produced finite positive losses, reloaded the frozen
residual bundle exactly, and generated 4,096 untouched evaluation hands.

The preservation identity is exact at the mechanism boundary: 368 audited
Standard10 states had zero greedy mismatches and maximum probability error
`2.98e-08` when the residual was zero.  This distinguishes the mechanism from
from-zero Deep CFR and from an imitation replacement.

All four paired point directions favored the learned residual ensemble.  The
direct learned-anchor contrast against Standard10 was `+27.7344 bb/100`, while
call-station, uniform, and min-bet deltas were `+964.0625`, `+38.8770`, and
`+772.3574`.  Every interval remained wide and crossed zero, so these are smoke
directions rather than strength evidence.

The critical risk is excessive policy release.  Candidate greedy disagreement
from Standard10 was 83.5% to 88.9% across cells.  The scale-1 residual therefore
does not preserve the mature execution contract in practice even though the
zero-residual identity is exact.  Scaling training volume at this setting would
confound whether the positive directions came from useful state-conditioned
credit or from an unstable near-total rewrite.

Decision: `ADMIT_STANDARD10_RESIDUAL_REGRET_CONTROL`.  Run a frozen-bundle
residual-scale dose control on disjoint development and confirmation decks.
Select the smallest scale that materially reduces greedy disagreement while
retaining a positive direct Standard10 direction; do not allocate Slumbot or
additional training hands until that confirmation passes.
