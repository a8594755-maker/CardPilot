# Fixed regularized-return pilot

Question: does eta=0.1 bb full-chronology regularization produce useful learned
changes relative to eta=0 under otherwise identical new on-policy training?
This is NOT full RNaD, not unchanged continuation of the legacy PPO recipe, and
not a final Slumbot test. Standard10 is the sole sampled training opponent and
the fixed reference. A favorable result requires later opponent breadth training;
this fixed-opponent pilot cannot establish a general equilibrium policy.

Retain original seed1/3 fixed2M parent weights and all Adam state. Old replay,
pool and counters remain in immutable hash-bound parents, explicitly inactive in
the separate new-regimen checkpoint schema. Local counters denote NEW physical
executions, never overwrite inherited counts. No epsilon or replay. Gamma and
lambda1, one epoch,2048 complete hands per update, minibatch16384, original Adam
LR1e-4, entropy coefficient.005/floor.05, value coefficient1, no local KL term.
Actual terminal commitment bounds shift by exact future shaping per decision.

Two arms per seed: eta0 control and eta.1. Same seed-specific deal and action
namespace for both arms; independent namespaces between seeds. Frozen weights
through each entire collection batch. Both physical seats alternate. CPU1 thread.
Fixed cumulative doses16384 and65536 NEW physical hands per arm.262144 total
live training executions,131072 distinct planned seed/deal keys across arms.
No train-on-eval or outcome-based early success stopping. Fail closed on nonfinite
updates, contract mismatch, unfinished transaction or disk free space below8GiB.
Keep all checkpoints/raw evidence. Each100MB checkpoint,128 update snapshots plus
initial snapshots is approximately13GB; initial disk free31.8GB supports this dose.

Train stage1 all arms, then pause at clean boundaries for stage1 frozen evaluation.
Before collecting any evaluation reward, freeze all three policies per seed
(parent/control/treatment) and evaluator sources. At each stage use8 existing
anchor identities in the retained input contract,512 disjoint fresh planned decks
per seed/anchor, both seats, sampledT1:49152 executions per stage. Use identical
decks/action keys across the three policies. Stage namespaces distinct; independent
from training. Verify no planned deck overlap with available earlier raw evidence
before evaluating. Existing anchors share ancestry: NOT lifetime-unseen families.

Report paired seat-averaged treatment-minus-control and own-parent bb/100 with
deck-level95% CIs, pooled and per-anchor, preservation versus transfer, per seed
and seat. These are developmental conditional intervals, not final acceptance.
Do not change eta after viewing pilot outcomes. Finish both fixed training doses
unless a documented integrity or replicated catastrophic deterioration warrants
a stop. A positive small smoke is not sufficient for promotion; inconclusive
65k is insufficient scale, not an algorithm rejection. Choose next dose/opponent
breadth only after full learning curves, hardware costs and mechanism magnitude.
