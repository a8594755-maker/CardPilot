# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T01:14:31.391128+00:00`
- Candidate: `weak_kl_confirmation_source`
- Candidate path: `C:\Users\a8594\CardPilot\models\baseline\standard10\latest.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +0.00 | +24.20 | -24.20 | +/-0.00 | 0.0000 | VALID | 0/0/8192 | 120.7 |
| slumbot_free | 16,384 | +15.68 | +40.10 | -8.75 | +/-9.16 | 0.0000 | VALID | 1734/1734/4724 | 150.1 |
| corrected_cfr96 | 16,384 | +55.97 | +102.61 | +9.33 | +/-29.30 | 0.0000 | VALID | 3157/3356/1679 | 81.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
