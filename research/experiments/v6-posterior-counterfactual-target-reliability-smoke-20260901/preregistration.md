# Preregistration: posterior-marginalized counterfactual target reliability

## Question

Does replacing fixed opponent holes with history-consistent posterior samples remove
the action instability and new-all-in pathology observed in the prior target smoke?
No policy weights change in this experiment.

## Frozen inputs and sampling

- Posterior rows: SHA256
  `1ccf2568114055640e2115322f174fb5ab3d6bf0476baaaa3a91cf0e40f1708b`,
  admitted by `v6-history-consistent-hole-posterior-smoke-20260901`.
- Candidate/continuation: frozen Standard10 under the exact legacy-v4 bridge.
- Opponents retain the exact per-row frozen model and legacy/native contract.
- For each of the 64 balanced seat x street rows, draw without replacement eight
  development and eight disjoint confirmation opponent-hole pairs from the frozen
  accepted support using seed 2026134001.
- Independently resample unseen future cards for every hole sample. Candidate holes,
  observed board, and public/financial history remain fixed.
- Branch every legal physical action with common posterior-hole/future samples across
  actions, then continue both policies greedily.
- Select the development mean-best action, retaining source on exact ties. Confirmation
  samples never select actions.

## Gate

Training a state-conditioned residual is admitted only if all hold:

1. overall development/confirmation selected-action agreement >= 0.80;
2. every seat x street agreement >= 0.70;
3. aggregate confirmation selected-minus-source 95% CI lower bound > 0;
4. no seat x street mean confirmation delta is negative; and
5. newly selected all-ins are <= 5% of rows.

Failure ends this counterfactual target route without coefficient, threshold, subset,
or seed tuning. Passing admits a separate learned residual smoke with row/opponent
heldouts and source-preservation gates; it is not strength evidence.

The 112 posterior-source trajectory hands are lineage only and are not counted again.
All branch continuations are offline counterfactual samples, not new environment hands.
