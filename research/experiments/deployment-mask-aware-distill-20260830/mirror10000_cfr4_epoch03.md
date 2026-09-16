# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T00:21:51.912905+00:00`
- Candidate: `CFR4-DUALMASK-H64-SKL1-E3`
- Candidate path: `research\experiments\deployment-mask-aware-distill-20260830\adapter_cfr4_dualmask_h64_skl1_l2p01_epoch03.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `10000`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| Standard10 | 20,000 | +2.01 | +20.48 | -16.46 | +/-0.63 | 0.0000 | VALID | 570/437/8993 | 97.4 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `True`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
