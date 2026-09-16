# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T04:56:56.252826+00:00`
- Candidate: `representation_curve_full_mid`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\full_mid.pt`
- Candidate checkpoint iter/hands: `52` / `214114`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +122.34 | +47.78 | +196.91 | +/-65.16 | 0.0000 | VALID | 1015/936/2145 | 47.7 |
| slumbot_free | 8,192 | +253.68 | +134.09 | +373.26 | +/-75.01 | 0.0000 | VALID | 1412/1228/1456 | 57.5 |
| corrected_cfr96 | 8,192 | +474.92 | +579.64 | +370.20 | +/-102.63 | 0.0000 | VALID | 1486/1494/1116 | 35.2 |
| heldout_weak | 8,192 | +227.88 | -7.22 | +462.98 | +/-76.70 | 0.0000 | VALID | 991/1037/2068 | 43.9 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
