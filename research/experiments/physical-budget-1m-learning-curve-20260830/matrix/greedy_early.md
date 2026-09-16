# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:21:04.154782+00:00`
- Candidate: `physical_1m_early`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\early.pt`
- Candidate checkpoint iter/hands: `64` / `263623`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +0.35 | +16.46 | -15.75 | +/-0.47 | 0.0000 | VALID | 12/9/2027 | 109.6 |
| slumbot_free | 4,096 | +14.92 | +37.78 | -7.94 | +/-5.77 | 0.0000 | VALID | 491/459/1098 | 145.8 |
| corrected_cfr96 | 4,096 | +11.76 | +42.94 | -19.41 | +/-23.37 | 0.0000 | VALID | 856/810/382 | 83.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
