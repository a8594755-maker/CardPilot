# Counterfactual soft-policy replay pilot

## Outcome

Decision: `REJECT_COUNTERFACTUAL_SOFT_POLICY_NO_ROBUST_GENERAL_GAIN`.

A conservative policy-only replay target derived from paired common-random-number all-legal action advantages completed a valid 263,417-hand treatment run, but did not produce a robust improvement over the untouched adaptive-league all-heads control. No confirmation or Slumbot evaluation is justified.

## Dataset and treatment contract

- The immutable replay dataset contains 10,752 paired-CRN rows: 6,454 train, 2,149 validation, and 2,149 test; SHA256 `605a7ab8cb1c8cb044ac56d48a3e3cde05b769e61281efac9ee27d9d736efb8e`.
- Every split covers all 20 seat/street/trajectory-opponent cells. Targets use paired action-minus-anchor `advantage_lcb` with z=1.96 and row-only reliability.
- The treatment changes only learned-policy supervision: policy loss coefficient 0.01, target clip 1.5, temperature 1, one stratified 512-row replay batch per update, and linear decay by actual hands to 262,144.
- The Action-Q head was disabled, the counterfactual Q coefficient and Q loss remained identically zero, and no benchmark-specific action rule was added.

## Training and integrity

- Smoke: 4,103 actual environment hands; both fixed-pool and policy-replay audits passed.
- Production: 263,417 actual environment hands over 64 updates; fixed-pool/session-independence and replay-cursor audits passed.
- Replay applied exactly 64 batches and 32,768 draws, equal to 5.077161 dataset epochs. Every policy loss was finite and positive; the effective coefficient followed the preregistered actual-hand decay monotonically.
- The immutable three-anchor pool, all 64 assignment records and their RNG/hash chain, optimizer state, global advantage normalization, and archive boundaries/hashes were verified.
- Maximum source-policy KL was 0.00151743, maximum PPO clip fraction was zero, and there were zero KL early stops.
- Frozen archives were saved at 65,873, 131,656, 197,580, and 263,417 actual hands.

## Frozen matched evaluation

Each archive was evaluated on the untouched seed-20260853 stream for 1,024 mirrored pairs against Standard10, slumbot_free, and corrected CFR96. Values are treatment minus the untouched `adaptive-league-all-heads-pilot-20260830` control in bb/100 with paired 95% half-widths.

| Iteration | Standard10 | slumbot_free | corrected CFR96 |
|---:|---:|---:|---:|
| 16 | +0.391 +/- 0.645 | -0.334 +/- 0.610 | -1.037 +/- 1.802 |
| 32 | +0.098 +/- 0.906 | -0.384 +/- 0.968 | -11.373 +/- 18.502 |
| 48 | -0.537 +/- 0.756 | -0.495 +/- 0.692 | -0.125 +/- 0.973 |
| 64 | +0.171 +/- 0.556 | +0.049 +/- 0.646 | +8.614 +/- 18.473 |

Only 5 of 12 point estimates were positive and 7 were negative. Mean delta was -0.414 bb/100 and median delta was -0.229 bb/100. Every paired 95% interval crossed zero. Although iter64 was point-positive against all three anchors, the two low-variance effects were near zero and the CFR96 estimate was too noisy; earlier checkpoints were mixed or negative, so there is no consistent learning curve.

## Interpretation

The all-legal uncertainty-conservative target is mechanically valid and numerically stable, and policy-only replay can be applied without an Action-Q head. At this dataset size and coefficient, however, it does not improve general learned-policy strength robustly. The likely bottleneck is not simply the absence of alternative-action supervision from this small offline CRN set; future work should prioritize substantially broader learned-policy data or a stronger policy-optimization objective rather than scaling this treatment unchanged.

No Slumbot hands were used. The formal benchmark remains unmet.
