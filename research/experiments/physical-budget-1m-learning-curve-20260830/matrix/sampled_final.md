# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:39:28.639187+00:00`
- Candidate: `physical_1m_final`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\final.pt`
- Candidate checkpoint iter/hands: `211` / `868858`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.55 | +18.76 | -17.66 | +/-0.89 | 0.0000 | VALID | 49/46/4001 | 125.1 |
| slumbot_free | 8,192 | +21.78 | +42.95 | +0.62 | +/-14.90 | 0.0000 | VALID | 949/848/2299 | 158.7 |
| corrected_cfr96 | 8,192 | +70.44 | +116.67 | +24.21 | +/-39.31 | 0.0000 | VALID | 1682/1597/817 | 88.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
