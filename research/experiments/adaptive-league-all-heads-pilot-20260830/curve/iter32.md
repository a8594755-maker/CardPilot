# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T05:26:52.576680+00:00`
- Candidate: `all_heads_iter32`
- Candidate path: `research\experiments\adaptive-league-all-heads-pilot-20260830\production\checkpoints\checkpoint_iter000032_hands000000131842.pt`
- Candidate checkpoint iter/hands: `32` / `131842`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.15 | +25.98 | -25.68 | +/-0.84 | 0.0000 | VALID | 6/6/1012 | 57.3 |
| slumbot_free | 2,048 | +11.80 | +36.62 | -13.03 | +/-5.89 | 0.0000 | VALID | 240/229/555 | 72.6 |
| corrected_cfr96 | 2,048 | +20.98 | +57.45 | -15.49 | +/-33.08 | 0.0000 | VALID | 418/398/208 | 38.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
