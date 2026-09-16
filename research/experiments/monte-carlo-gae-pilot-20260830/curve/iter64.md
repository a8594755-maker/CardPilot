# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T17:10:05.514996+00:00`
- Candidate: `monte_carlo_gae_iter64`
- Candidate path: `research\experiments\monte-carlo-gae-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263581.pt`
- Candidate checkpoint iter/hands: `64` / `263581`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.05 | +25.88 | -25.78 | +/-0.53 | 0.0000 | VALID | 5/8/1011 | 55.7 |
| slumbot_free | 2,048 | +11.44 | +36.62 | -13.74 | +/-5.81 | 0.0000 | VALID | 240/229/555 | 71.8 |
| corrected_cfr96 | 2,048 | +10.73 | +37.63 | -16.17 | +/-27.53 | 0.0000 | VALID | 416/398/210 | 37.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
