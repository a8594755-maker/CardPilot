# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T04:21:48.886679+00:00`
- Candidate: `representation_curve_source`
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
| standard10 | 8,192 | +0.00 | +11.91 | -11.91 | +/-0.00 | 0.0000 | VALID | 0/0/4096 | 58.7 |
| slumbot_free | 8,192 | +8.46 | +36.21 | -19.29 | +/-8.20 | 0.0000 | VALID | 907/900/2289 | 74.2 |
| corrected_cfr96 | 8,192 | +37.54 | +75.62 | -0.54 | +/-40.30 | 0.0000 | VALID | 1563/1695/838 | 40.4 |
| heldout_weak | 8,192 | -11.42 | -9.28 | -13.56 | +/-21.68 | 0.0000 | VALID | 518/519/3059 | 52.7 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
