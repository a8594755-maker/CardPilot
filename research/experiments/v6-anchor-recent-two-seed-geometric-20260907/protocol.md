# Anchor-preserving recency versus historical loss selection

One main family (anchor-latest), one control (loss-kbest), training seeds 1 and 3.
Hypothesis: updating learned opponents, while retaining three external anchors,
improves continued learning breadth relative to the nearly static historical-loss
pool. Recency is not assumed to equal opponent strength or diversity.

Both arms branch from the exact original connected2M endpoints of
v6-preflop-actor-route-2m-continuation-20260906. Smoke endpoints are excluded.
Retain full learned model, Adam and actual LR, replay, counters, static Standard10
reference, actor/critic routes, initial pool order and adaptive statistics.
The only algorithmic contrast is explicit pool strategy. Both use the qualified
isolated wrapper; default loss-kbest selection remains unchanged.

Additional physical execution targets per branch: 262144 then 1048576, measured
from that seed's parent counter, not reset to zero. Complete-update overshoot is
reported. Replay and no-decision/tail executions are separate. Do not claim one
policy trained on the sum of four branches. New managed attempt namespaces on
every job; statistical continuation, not bitwise worker RNG equivalence.

Stage order: S1 control, S1 recent, S3 recent, S3 control; then reverse order.
12 workers x8 environments, 4096 transition-bearing target hands per iteration,
batch16384, PPOepochs2, targetKL .01, actual retained LR~1e-4, referenceKL1,
replaydepth2/ratio.5, K5, snapshot every2, self-play .25, adaptive8 groups.
Per-job natural runtime limit7200s; no automatic restart or overwrite. Resume
failures are reviewed with preserved evidence, never rerun from an older parent.

After each stage: all four frozen endpoints versus their own unchanged parent,
four frozen heterogeneous anchors, both seats, 2048 common-deck pairs per anchor.
Internal seeds20265011/20265031 for stage1,20265012/20265032 for stage2.
Before execution, verify deck freshness against the retained historical corpus.
Shared decks within a seed allow paired arm contrasts; separate seeds do not.
131072 internal executions per stage,16384 unique evaluation decks per stage.
Report per-anchor, per-seat, matched control and own-parent changes with uncertainty.

262k is a mechanism/early-curve gate, not a demand to beat Slumbot. Continue to1M
unless integrity fails, numerical instability occurs, or the existing broad-collapse
criterion is met. Admission/assignment turnover must actually occur; otherwise
diagnose implementation rather than enlarging a misconfigured run. Do not stop
solely for nonsignificance or negative absolute score. Do not promote solely for
lower loss, less policy drift, recency, or positive training rewards.

At a clean1M milestone, fixed external development calibration: all four policies,
20000 fresh Slumbot hands each, eight2500 sessions each; no lucky-arm selection,
replacement or extension. Freeze execution/runtime and audit session identifiers
before launch in its own evidence record. This is development, not final acceptance.
No Slumbot labels or action rules enter training. Reassess larger scale using
cross-seed own curves, breadth, capability preservation and external alignment.
The final >=100k single-policy blind criterion remains entirely unmet by this trial.

Automate initial restoration, parent/source hashes, live current-job physical
accounting, raw-prefix preservation, admission/assignment identities, namespace
receipts, optimizer health and terminal descendant checks. No competing logger.
Candidate controller must pass preflight/tests before training allocation.
