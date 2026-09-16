# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T05:29:12.855330+00:00`
- Candidate: `all_heads_iter48`
- Candidate path: `research\experiments\adaptive-league-all-heads-pilot-20260830\production\checkpoints\checkpoint_iter000048_hands000000197748.pt`
- Candidate checkpoint iter/hands: `48` / `197748`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.39 | +26.27 | -25.49 | +/-0.67 | 0.0000 | VALID | 7/7/1010 | 56.6 |
| slumbot_free | 2,048 | +11.61 | +36.62 | -13.40 | +/-5.80 | 0.0000 | VALID | 240/230/554 | 71.7 |
| corrected_cfr96 | 2,048 | +10.19 | +37.00 | -16.62 | +/-27.46 | 0.0000 | VALID | 418/398/208 | 37.9 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
