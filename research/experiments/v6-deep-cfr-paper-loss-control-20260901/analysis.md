# Exact-v6 Deep CFR paper loss and LCFR weighting control

Decision: `REJECT_PAPER_LOSS_AT_BOUNDED_BUDGET`.

Both K4 arms completed 48 total root traversals and all seat×iteration coverage.
The paper loss remained finite under gradient clipping, but its squared-error
scale (1,755--16,533) is not directly comparable with the surrogate SmoothL1
scale (24.6--41.7).

On the common weighted-snapshot panel, paper MSE/LCFR improved only min-bet. Its
three-anchor mean was +63.21 versus +217.15 bb/100 for the surrogate, a -153.94
delta, and mean log imbalance was slightly worse (2.610 versus 2.330). The
preregistered transfer gates therefore reject the paper-loss bundle at this
bounded 512-step budget.

This does not refute the paper's 4,000-step/large-batch regimen; it shows that a
literal loss/weight substitution without paper-scale optimizer compute is not a
useful next scale step here. The active learned candidate is the frozen K4
fresh-reinit surrogate snapshot bundle from this experiment.

Next step: evaluate that bundle directly against frozen Standard10 under exact
physical-v6 rules and each policy's own observation/execution contract. A
substantial paired loss would reject Slumbot spending; a positive result would
justify building a journaled snapshot-policy Slumbot adapter and a fresh small
external gate.
