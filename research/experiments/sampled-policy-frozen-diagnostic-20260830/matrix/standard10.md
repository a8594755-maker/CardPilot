# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T19:13:12.892533+00:00`
- Candidate: `standard10_sampled`
- Candidate path: `models\baseline\standard10\latest.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.00 | +14.06 | -14.06 | +/-0.00 | 0.0000 | VALID | 0/0/4096 | 119.7 |
| slumbot_free | 8,192 | +11.27 | +40.56 | -18.02 | +/-9.68 | 0.0000 | VALID | 906/883/2307 | 150.0 |
| corrected_cfr96 | 8,192 | +22.99 | +49.41 | -3.43 | +/-40.26 | 0.0000 | VALID | 1593/1676/827 | 82.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
