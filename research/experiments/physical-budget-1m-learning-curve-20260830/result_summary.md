# One-million physical-hand learning curve

Decision: `FINAL_ENDPOINT_ADMITS_INDEPENDENT_CONFIRMATION`.

Measured training: **1,049,891 physical hands**, 211 updates. Legacy transition-bearing markers: 868,858. Frozen internal evaluation:147456hands; no new Slumbot hands.

| Checkpoint/mode | Physical training hands | Standard10 delta | Slumbot-free delta | CFR96 delta | Confirmation admission |
|---|---:|---:|---:|---:|---|
| greedy_early | 314,614 | +0.354 +/- 0.471 | +0.781 +/- 3.602 | +14.001 +/- 15.380 | False |
| greedy_mid | 634,937 | +0.281 +/- 0.439 | +1.125 +/- 3.584 | +14.803 +/- 15.689 | False |
| greedy_final | 1,049,891 | +0.195 +/- 0.494 | +1.477 +/- 3.608 | +14.848 +/- 15.690 | False |
| sampled_early | 314,614 | +3.023 +/- 4.834 | -2.051 +/- 4.038 | +25.819 +/- 17.675 | False |
| sampled_mid | 634,937 | +0.406 +/- 0.868 | +0.369 +/- 6.206 | +20.443 +/- 14.776 | True |
| sampled_final | 1,049,891 | +0.548 +/- 0.894 | +0.514 +/- 6.208 | +17.136 +/- 13.384 | True |

Deltas are matched treatment-minus-Standard10-control bb/100 with nominal95% pair CI half-width. 
Controls share deck and (when sampled) action random streams. The final endpoint is primary; early/mid checkpoints are exploratory.

Integrity: independent standard-library CI recomputation agrees with stored paired results; selected model and raw matrix hashes match;76 frozen tensors unchanged; all policy/value heads changed by finite updates. See completed_analysis.json and production_audit.json.

No internal admission establishes Slumbot strength, Nash convergence, or low exploitability. Any admitted cell requires a separately preregistered independent confirmation. If no cell is admitted, do not scale this unchanged configuration or promote its checkpoints to a100k Slumbot test. The result does not falsify the AlphaHoldem paper: batch size, update scope, regularization and league differ.

Goal remains unachieved: one frozen policy must still pass at least100000 fresh Slumbot hands above0bb/100 with positive95% CI lower bound.

## Interpretation and next experiment

The prespecified final sampled endpoint meets exploratory admission, as does sampled mid. Greedy fails at every checkpoint. The sampled improvement is primarily against CFR96; the two other final-anchor CIs cross zero. More physical training did not produce a monotonic improvement across this discovery curve. This supports an independent test of the fixed final endpoint, not further scale-up or a general-strength claim.

Next: separately preregister a single fixed-policy sampled replication, final checkpoint SHA256 `ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3`, original Standard10 matched control, the same three anchor identities, new seed20260894 and8192 mirrored pairs per anchor for each candidate (98304 total internal hands). Keep temperature1, unchanged evaluator sampling semantics and all budgets fixed before seeing outcomes. Require valid raw evidence, positive matched deltas on all three anchors and at least one positive nominal95% lower bound; additionally report multiplicity-adjusted intervals without treating exploratory discovery as part of the independent sample. No checkpoint reselection, combined discovery/confirmation CI, new training, or Slumbot game is authorized by this replication plan alone. If it fails, return to mechanism diagnostics; if it passes, separately assess external sampled-policy validation before any further training-scale decision.
