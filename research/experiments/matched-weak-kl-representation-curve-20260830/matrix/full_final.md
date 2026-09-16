# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T05:11:01.605127+00:00`
- Candidate: `representation_curve_full_final`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\full.pt`
- Candidate checkpoint iter/hands: `105` / `432347`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +156.09 | +79.06 | +233.12 | +/-82.63 | 0.0000 | VALID | 1372/1277/1447 | 41.1 |
| slumbot_free | 8,192 | +381.05 | +156.62 | +605.49 | +/-93.90 | 0.0000 | VALID | 1733/1654/709 | 48.5 |
| corrected_cfr96 | 8,192 | +703.23 | +688.25 | +718.22 | +/-110.28 | 0.0000 | VALID | 1422/1346/1328 | 31.9 |
| heldout_weak | 8,192 | +277.39 | +25.24 | +529.54 | +/-91.29 | 0.0000 | VALID | 1214/1278/1604 | 38.2 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
