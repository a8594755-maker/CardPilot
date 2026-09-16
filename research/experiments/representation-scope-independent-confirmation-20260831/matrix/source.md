# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T05:38:27.564537+00:00`
- Candidate: `representation_confirmation_source`
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
| standard10 | 16,384 | +0.00 | +16.51 | -16.51 | +/-0.00 | 0.0000 | VALID | 0/0/8192 | 57.8 |
| slumbot_free | 16,384 | +18.97 | +48.69 | -10.74 | +/-8.95 | 0.0000 | VALID | 1835/1765/4592 | 73.7 |
| corrected_cfr96 | 16,384 | +62.29 | +74.14 | +50.44 | +/-28.67 | 0.0000 | VALID | 3184/3310/1698 | 40.8 |
| heldout_weak | 16,384 | +1.79 | +17.51 | -13.92 | +/-17.89 | 0.0000 | VALID | 1075/1150/5967 | 51.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
