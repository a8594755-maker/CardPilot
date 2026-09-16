# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:32:14.143966+00:00`
- Candidate: `physical_1m_early`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\early.pt`
- Candidate checkpoint iter/hands: `64` / `263623`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +3.02 | +18.54 | -12.49 | +/-4.83 | 0.0000 | VALID | 38/38/4020 | 123.0 |
| slumbot_free | 8,192 | +19.22 | +42.96 | -4.53 | +/-14.12 | 0.0000 | VALID | 951/845/2300 | 164.8 |
| corrected_cfr96 | 8,192 | +79.12 | +110.88 | +47.36 | +/-40.93 | 0.0000 | VALID | 1678/1598/820 | 80.7 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
