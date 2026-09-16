# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T22:00:12.027380+00:00`
- Candidate: `physical1m_confirmation_final`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\physical-budget-1m-learning-curve-20260830\frozen\final.pt`
- Candidate checkpoint iter/hands: `211` / `868858`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +1.91 | +28.19 | -24.36 | +/-2.42 | 0.0000 | VALID | 81/63/8048 | 126.2 |
| slumbot_free | 16,384 | +14.95 | +25.65 | +4.26 | +/-10.29 | 0.0000 | VALID | 1828/1730/4634 | 151.6 |
| corrected_cfr96 | 16,384 | +61.67 | +92.11 | +31.22 | +/-27.83 | 0.0000 | VALID | 3183/3295/1714 | 86.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
