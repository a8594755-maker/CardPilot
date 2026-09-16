# Exact-v6 synchronized versus sequential update control

Decision: `REJECT_SYNCHRONIZATION_AS_SUFFICIENT_FIX`.

The arms began from byte-identical weights and used common training/evaluation
decks plus paired sampling and optimizer seeds. Both terminal checkpoints
reloaded exactly. Synchronized collection improved terminal greedy results on
all three generic anchors: its mean was +158.10 versus -108.48 bb/100 for the
matched sequential arm, a +266.58 delta. The 128-pair intervals are extremely
wide, so this is directional development evidence only.

Synchronization did not pass the primary structural gate. Mean absolute
seat-node log imbalance increased from 3.236 to 3.960. In both arms, player 0
received zero traverser nodes on iteration 2 because the sampled opponent folded
preflop on both roots; synchronized player 0 again received zero on iteration 3.
Thus freezing the iteration profile removes one sequential-update confound but
does not prevent zero-support trajectory collapse.

Two missing algorithm contracts now dominate:

1. The new adapter samples the exact regret-matched opponent strategy without
   exploration, while the repository's batched HUNL Deep CFR traversal defaults
   to 0.1 exploration. A deterministic fold can eliminate all downstream
   traverser samples at tiny budgets.
2. SD-CFR deploys an iteration-weighted sample/mixture of stored advantage
   networks. These controls evaluated the terminal current network, whose
   oscillation is not the average strategy convergence target.

Next step: implement explicit opponent exploration with recorded behavior
probabilities and per-iteration strategy snapshots, then compare epsilon 0 versus
0.1 under synchronized common-deck collection. Evaluate the frozen weighted
snapshot policy per hand as primary and terminal current network only as a
diagnostic. Require nonzero per-seat coverage and improved balance before any
budget increase.
