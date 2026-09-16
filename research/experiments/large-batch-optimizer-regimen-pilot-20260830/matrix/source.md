# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T22:52:36.347604+00:00`
- Candidate: `large_batch_pilot_source`
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
| standard10 | 8,192 | +0.00 | +23.44 | -23.44 | +/-0.00 | 0.0000 | VALID | 0/0/4096 | 122.9 |
| slumbot_free | 8,192 | +11.43 | +27.68 | -4.82 | +/-13.13 | 0.0000 | VALID | 905/880/2311 | 162.2 |
| corrected_cfr96 | 8,192 | +28.60 | +80.19 | -23.00 | +/-39.83 | 0.0000 | VALID | 1604/1618/874 | 85.2 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
