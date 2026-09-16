# Preregistration: terminal ELO-survivor selection diagnostic

## Question

The parent run retained five frozen policies, but its endpoint evaluation deployed the
terminal actor (snapshot id 5) rather than the tournament top-rated survivor.  Does
deploying the outcome-blind ELO winner materially change the exact physical-v6 greedy
policy and its breadth?

## Frozen selection rule

- Source run: `v6-legacy-fresh-zero-standard10-elo-curriculum-smoke-20260901`.
- Rank only the terminal `pool_snapshots` by their already-recorded
  `selection_score`; do not inspect any new endpoint result when selecting.
- The selected policy is snapshot id 2, iteration 2, 8,256 transition-bearing
  hands, terminal ELO 1568.1509667100256.
- The selected state must be bit-identical to the `model` state in
  `checkpoint_iter000002_hands000000008256.pt` and to terminal pool snapshot id 2.
- Copy that archived checkpoint once to `frozen/top_survivor.pt`; no training,
  optimizer step, averaging, or checkpoint mutation is allowed.

The parent terminal endpoint evidence is known, but it cannot affect the candidate or
anchor selection.  Reuse the parent's exact four deal streams so that the newly
evaluated survivor can be compared pairwise against the already-frozen terminal
control with lower variance.

## Evaluation contract

- Exact physical v6 rules with the exact legacy-v4 observation bridge.
- Frozen greedy execution for candidate and anchor.
- 4,096 mirrored deal pairs per anchor (8,192 physical hands per cell).
- Anchors and seeds:
  - Standard10, seed 20261210;
  - fresh-zero no-KL-stop terminal policy, seed 21261213;
  - fresh-zero KL-stop terminal policy, seed 22261216;
  - fresh-zero LR1e-4 terminal policy, seed 23261219.
- Preserve raw `pairs.jsonl`, summaries, candidate/anchor hashes, and paired
  treatment-minus-parent-terminal deltas.

## Gates and decisions

Validity requires the source-state equality checks, four complete/hash-valid cells,
and exact deal-key alignment with the parent control cells.

The survivor-selection hypothesis is supported only if:

1. its reachable greedy behavior differs from the terminal actor on at least one
   cell;
2. all four survivor point estimates are positive;
3. at least two survivor 95% CI lower bounds are positive, including at least one
   untouched fresh-zero learned anchor; and
4. the paired pooled survivor-minus-terminal delta has a positive 95% CI lower
   bound.

If any support condition fails, reject historical-survivor deployment and do not
scale this run.  If all pass, the next step is an untouched fresh Slumbot gate of the
same frozen survivor; this diagnostic itself cannot claim benchmark progress.

Accounting: zero new training hands, 8 candidate evaluation hands per pair index
across four cells (32,768 new physical evaluation hands).  Reused parent control
hands are lineage evidence and are not counted again.
