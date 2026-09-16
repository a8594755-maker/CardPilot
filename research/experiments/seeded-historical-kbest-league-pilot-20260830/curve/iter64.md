# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T12:53:10.523542+00:00`
- Candidate: `kbest_iter64`
- Candidate path: `research\experiments\seeded-historical-kbest-league-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263581.pt`
- Candidate checkpoint iter/hands: `64` / `263581`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.15 | +25.68 | -25.39 | +/-0.88 | 0.0000 | VALID | 7/7/1010 | 118.0 |
| slumbot_free | 2,048 | +11.25 | +36.62 | -14.12 | +/-5.83 | 0.0000 | VALID | 240/231/553 | 137.5 |
| corrected_cfr96 | 2,048 | +10.42 | +37.65 | -16.81 | +/-27.46 | 0.0000 | VALID | 417/397/210 | 79.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
