# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T21:28:32.676125+00:00`
- Candidate: `physical_1m_source`
- Candidate path: `C:\Users\a8594\CardPilot\models\baseline\standard10\latest.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.00 | +17.56 | -17.56 | +/-0.00 | 0.0000 | VALID | 0/0/4096 | 123.0 |
| slumbot_free | 8,192 | +21.27 | +48.46 | -5.92 | +/-13.19 | 0.0000 | VALID | 929/845/2322 | 160.3 |
| corrected_cfr96 | 8,192 | +53.30 | +91.18 | +15.42 | +/-37.14 | 0.0000 | VALID | 1664/1627/805 | 87.8 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
