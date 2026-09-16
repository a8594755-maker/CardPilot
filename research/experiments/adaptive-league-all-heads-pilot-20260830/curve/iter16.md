# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T05:24:34.804456+00:00`
- Candidate: `all_heads_iter16`
- Candidate path: `research\experiments\adaptive-league-all-heads-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065930.pt`
- Candidate checkpoint iter/hands: `16` / `65930`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.15 | +25.39 | -25.68 | +/-0.79 | 0.0000 | VALID | 6/13/1005 | 56.0 |
| slumbot_free | 2,048 | +11.77 | +36.62 | -13.08 | +/-5.82 | 0.0000 | VALID | 241/229/554 | 71.5 |
| corrected_cfr96 | 2,048 | +9.77 | +37.67 | -18.13 | +/-27.43 | 0.0000 | VALID | 420/399/205 | 38.0 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
