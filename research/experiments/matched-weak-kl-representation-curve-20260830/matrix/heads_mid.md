# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T04:33:16.448071+00:00`
- Candidate: `representation_curve_heads_mid`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\heads_mid.pt`
- Candidate checkpoint iter/hands: `56` / `230628`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | -2.25 | +19.27 | -23.76 | +/-25.30 | 0.0000 | VALID | 515/516/3065 | 51.6 |
| slumbot_free | 8,192 | +16.39 | +38.05 | -5.28 | +/-27.71 | 0.0000 | VALID | 1178/1070/1848 | 63.8 |
| corrected_cfr96 | 8,192 | +101.32 | +102.99 | +99.66 | +/-58.71 | 0.0000 | VALID | 1595/1559/942 | 36.9 |
| heldout_weak | 8,192 | -2.82 | -17.58 | +11.94 | +/-12.19 | 0.0000 | VALID | 292/257/3547 | 47.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
