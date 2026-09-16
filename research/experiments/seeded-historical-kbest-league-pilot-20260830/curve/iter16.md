# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T12:48:35.278953+00:00`
- Candidate: `kbest_iter16`
- Candidate path: `research\experiments\seeded-historical-kbest-league-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065896.pt`
- Candidate checkpoint iter/hands: `16` / `65896`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.02 | +25.68 | -25.73 | +/-0.63 | 0.0000 | VALID | 7/2/1015 | 120.4 |
| slumbot_free | 2,048 | +10.83 | +36.62 | -14.96 | +/-5.83 | 0.0000 | VALID | 235/225/564 | 153.2 |
| corrected_cfr96 | 2,048 | +9.57 | +37.01 | -17.87 | +/-27.53 | 0.0000 | VALID | 419/406/199 | 81.3 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
