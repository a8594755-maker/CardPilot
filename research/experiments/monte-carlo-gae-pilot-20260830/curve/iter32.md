# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T17:05:39.174329+00:00`
- Candidate: `monte_carlo_gae_iter32`
- Candidate path: `research\experiments\monte-carlo-gae-pilot-20260830\production\checkpoints\checkpoint_iter000032_hands000000131801.pt`
- Candidate checkpoint iter/hands: `32` / `131801`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.78 | +25.20 | -26.76 | +/-0.72 | 0.0000 | VALID | 3/11/1010 | 55.5 |
| slumbot_free | 2,048 | +9.85 | +36.62 | -16.92 | +/-5.51 | 0.0000 | VALID | 232/222/570 | 71.6 |
| corrected_cfr96 | 2,048 | +10.74 | +37.54 | -16.06 | +/-27.51 | 0.0000 | VALID | 418/403/203 | 37.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
