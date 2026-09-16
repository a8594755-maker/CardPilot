# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:19:05.751793+00:00`
- Candidate: `physical_1m_source`
- Candidate path: `C:\Users\a8594\CardPilot\models\baseline\standard10\latest.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +0.00 | +16.50 | -16.50 | +/-0.00 | 0.0000 | VALID | 0/0/2048 | 118.4 |
| slumbot_free | 4,096 | +14.14 | +36.70 | -8.42 | +/-4.41 | 0.0000 | VALID | 481/447/1120 | 158.0 |
| corrected_cfr96 | 4,096 | -2.24 | +15.50 | -19.97 | +/-16.95 | 0.0000 | VALID | 856/821/371 | 84.4 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
