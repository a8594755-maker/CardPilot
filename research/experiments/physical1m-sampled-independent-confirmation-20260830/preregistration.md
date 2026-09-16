# Independent sampled final confirmation

Registered before any new confirmation games. Parent: `physical-budget-1m-learning-curve-20260830`, COMPLETED after1,049,891 physical training hands and147,456 discovery evaluation hands. Its primary-final sampled endpoint met exploratory admission; that does not establish general strength or Slumbot success.

## Fixed identities and budget

- Treatment: parent `frozen/final.pt`, SHA256 `ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3`.
- Matched source control and first anchor: original Standard10 SHA256 `91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428`.
- Other anchors, in order: slumbot_free SHA256 `457d3babb82cb8014a2b7c378b2b5f916962565e63a44d192d5d7acd8393d6e7`; corrected_cfr96 SHA256 `902a7049ca66c0552246d11fe482eed4df47ac5c675ddf051c34ed86dcf213a6`.
- Policy mode `sampled_both_sides`, unchanged categorical probabilities (temperature1), stack200bb.
- Seed20260894; per-anchor offsets index*1000003; common sampled action streams use schema `sha256_seed_pair_physical_seat_decision_v1`.
-8192 mirrored pairs per anchor per candidate. Control first, then final.98304 total new internal hands, no new training or Slumbot hands. No optional stopping, checkpoint/mode replacement, extra seeds or pooling parent discovery hands into this sample.

## Analysis and decision

Recompute treatment-minus-control per-pair EV and nominal normal95% CI independently from raw arrays. Validate completed execution, exact seeds/mode/stack, all input hashes, full raw pair/seat arrays, arithmetic and OOD validity. Nominal replication gate: positive delta on each of3 anchors and at least one nominal95% CI lower bound above0. This gate alone is not familywise significance. Also report Bonferroni98.333% per-anchor intervals, using z=NormalDist.inv_cdf(1-0.05/6), as the predeclared stronger secondary check. Do not conceal weak/negative other-anchor results behind the favorable anchor.

If the fixed replication gate fails, return to a separately logged fixed-weight hand-group gradient-noise diagnostic; do not scale unchanged training or retest another discovery checkpoint. If it passes, assess external sampled-policy validation in a separate experiment before further training-scale decisions. Neither outcome establishes exploitability or the user's goal. Formal success still requires one frozen policy on at least100000 fresh Slumbot hands with bb/100>0 and95% lower>0.

## Execution integrity

`python research/experiments/physical1m-sampled-independent-confirmation-20260830/run_confirmation.py` snapshots complete AlphaHoldem Python sources and required deep_cfr modules, verifies frozen code/checkpoints before and after execution, records exact cell commands, and updates accounting after each persisted complete cell. It leaves the record RUNNING for result interpretation/finish. `--resume-evaluation` is only for a confirmed terminal interruption: it verifies frozen launcher/source, reuses completed cells and refuses to overwrite partial evidence. No process is automatically restarted.
