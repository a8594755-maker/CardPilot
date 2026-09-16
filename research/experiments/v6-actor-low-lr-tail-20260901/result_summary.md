# Actor-head low-LR convergence-tail result

Decision: `ADMIT_INDEPENDENT_GREEDY_FRESH5K`.

The exact raw actor checkpoint was continued from 132,553 to 263,022 completed
physical lineage hands.  The tail added 130,469 hands over 26 PPO updates while
preserving the ten Adam states, inherited 1e-5 learning rate, legacy hand
counter, actor EMA, adaptive-league state, assignment RNG chain, and a disjoint
fixed-deal start index.  The fixed-pool/session audit and independent review
both passed.

An initial zero-hand command was rejected by argparse because it omitted the
explicit `--no-reset-optimizer` acknowledgement.  No checkpoint was loaded and
no hands were produced.  The same record preserves the stderr and exact command;
recovery added only that acknowledgement.  During later evaluation, a stale
`execution.json` snapshot overwrote the original status snapshot.  The complete
`recovery_execution.json`, original stderr/failure text, command history, parent
SHA, and prefix hashes remain authoritative.  This evidence limitation did not
change model or hand artifacts.

Under generic greedy execution, the 61,440-hand common-deck matrix gave:

- tail minus parent: +46.3739 bb/100, paired 95% CI [+7.4970, +85.2508]
- tail minus source: +218.5390 bb/100, paired 95% CI [+152.9241, +284.1538]
- positive tail-minus-parent anchors: 4/5

All five matrix opponents participated in training, so these numbers are a
convergence/mechanism gate, not held-out generalization evidence.  They satisfy
the preregistered admission rule for one independent fresh 5,000-hand greedy
Slumbot pilot.  No Slumbot hands were used here and the 100k Goal is unmet.

Frozen tail SHA256:
`6f3bf54433d72fdc4ebb9de33c52947c6da4fd0af2259d8b9561f7956821db5b`.
