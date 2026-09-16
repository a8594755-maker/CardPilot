# Exact-v6 Deep CFR traversal-K scale control

Decision: `REJECT_K8_TRAVERSAL_SCALE`.

K8 passed every structural scale gate. Minimum seat×iteration traverser coverage
rose from 2 to 342 nodes, mean log imbalance fell from 3.695 to 2.712, and all
cells retained coverage. It generated 276,338 decision nodes and 193,795 terminal
branches without hitting a per-root limit. Call-station and uniform snapshot
returns were directionally better than K2.

The transfer gate failed because min-bet deteriorated from +178.65 to -832.58
bb/100; K8's three-anchor mean was -188.43 versus +79.27 for K2. The min-bet
512-hand CI was [-1693.87, 28.70], while all cells remain high variance. Per the
preregistered rule, K8 is not admitted despite better coverage.

Scaling K also expanded the player-1 reservoir to 59,282 samples versus 4,850
for player 0, while update steps stayed fixed. More importantly, the helper still
uses SmoothL1 plus a bounded DCFR-like sample weight. Brown et al. use MSE and
linear-CFR iteration weights when retraining the value network from scratch.
Thus the failed transfer gate does not cleanly isolate traversal count from an
increasingly consequential loss/weighting mismatch.

Next step: at an intermediate fixed K, compare the current Huber/DCFR surrogate
against paper MSE/LCFR weighting with identical fresh initialization, decks,
sampling seeds, steps, and snapshot evaluation. Only then revisit traversal
scale. Simple-anchor outcomes remain development diagnostics and are not
substitutes for Slumbot evidence.
