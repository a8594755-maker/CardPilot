# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:53:01.073440+00:00`
- Candidate: `physical1m_confirmation_control`
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
| standard10 | 16,384 | +0.00 | +27.79 | -27.79 | +/-0.00 | 0.0000 | VALID | 0/0/8192 | 121.0 |
| slumbot_free | 16,384 | +16.23 | +29.71 | +2.75 | +/-9.17 | 0.0000 | VALID | 1802/1713/4677 | 155.0 |
| corrected_cfr96 | 16,384 | +49.48 | +78.40 | +20.55 | +/-26.34 | 0.0000 | VALID | 3165/3324/1703 | 80.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
