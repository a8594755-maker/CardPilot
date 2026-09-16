# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:35:54.632759+00:00`
- Candidate: `physical_1m_mid`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\mid.pt`
- Candidate checkpoint iter/hands: `128` / `527075`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.41 | +18.43 | -17.62 | +/-0.87 | 0.0000 | VALID | 46/47/4003 | 122.2 |
| slumbot_free | 8,192 | +21.64 | +42.86 | +0.41 | +/-14.90 | 0.0000 | VALID | 949/844/2303 | 150.0 |
| corrected_cfr96 | 8,192 | +73.74 | +119.45 | +28.04 | +/-39.82 | 0.0000 | VALID | 1685/1596/815 | 86.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
