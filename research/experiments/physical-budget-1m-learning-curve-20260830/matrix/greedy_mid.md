# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:23:03.379933+00:00`
- Candidate: `physical_1m_mid`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\mid.pt`
- Candidate checkpoint iter/hands: `128` / `527075`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +0.28 | +16.55 | -15.99 | +/-0.44 | 0.0000 | VALID | 13/8/2027 | 117.9 |
| slumbot_free | 4,096 | +15.26 | +37.81 | -7.28 | +/-5.77 | 0.0000 | VALID | 489/456/1103 | 132.6 |
| corrected_cfr96 | 4,096 | +12.56 | +43.85 | -18.72 | +/-23.58 | 0.0000 | VALID | 860/807/381 | 83.0 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
