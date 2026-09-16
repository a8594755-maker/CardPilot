# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:24:57.394016+00:00`
- Candidate: `physical_1m_final`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\final.pt`
- Candidate checkpoint iter/hands: `211` / `868858`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +0.20 | +16.41 | -16.02 | +/-0.49 | 0.0000 | VALID | 16/13/2019 | 119.1 |
| slumbot_free | 4,096 | +15.61 | +37.84 | -6.61 | +/-5.78 | 0.0000 | VALID | 491/457/1100 | 155.4 |
| corrected_cfr96 | 4,096 | +12.61 | +43.93 | -18.71 | +/-23.58 | 0.0000 | VALID | 861/806/381 | 83.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
