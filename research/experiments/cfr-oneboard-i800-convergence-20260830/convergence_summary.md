# One-board i800 convergence control

Claim scope: checkpoint strategy drift, not exploitability.

Both solves recomputed the exact `As7d2c` board from zero with the same b8
abstraction and seed 20260829 as the i200 checkpoints. The comparison includes
all flop histories at depths 0 and 1 plus a deterministic 0.002 sample of deeper
histories.

| Tree | Group | i50->i200 mean TV | i200->i800 mean TV | Ratio | i50->i200 fraction TV > 0.1 | i200->i800 fraction TV > 0.1 |
|---|---:|---:|---:|---:|---:|---:|
| SRP | all matched rows | 0.072823 | 0.135767 | 1.864 | 0.207884 | 0.390931 |
| SRP | flop depth 0 | 0.239457 | 0.152880 | 0.638 | 0.875000 | 0.875000 |
| SRP | flop depth 1 | 0.189443 | 0.116533 | 0.615 | 0.656250 | 0.609375 |
| 3BP | all matched rows | 0.084326 | 0.135349 | 1.605 | 0.234022 | 0.396976 |
| 3BP | flop depth 0 | 0.347553 | 0.212738 | 0.612 | 1.000000 | 0.875000 |
| 3BP | flop depth 1 | 0.203710 | 0.123996 | 0.609 | 0.812500 | 0.500000 |

The shallow mean-TV reductions are consistent across both trees (36-39%), so
additional iterations move the policy in a more stable direction. They do not
meet an absolute convergence standard: 87.5% of root buckets in each tree still
move by more than TV 0.1 between i200 and i800, and depth-1 mean TV remains
0.117-0.124. The all-row aggregate also worsens because the deeper solve expands
the reachable support substantially; it must not be interpreted as a like-for-like
exploitability estimate.

Decision: reject i200 CFR checkpoint drift as a confidence weight for learned
targets. Retain the i800 artifacts as higher-fidelity teacher data, but require a
different confidence signal or materially deeper/action-finer solving before
claiming convergence.
