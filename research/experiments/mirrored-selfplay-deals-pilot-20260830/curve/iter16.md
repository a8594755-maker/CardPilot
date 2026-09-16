# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T16:04:45.522592+00:00`
- Candidate: `mirrored_selfplay_iter16`
- Candidate path: `research\experiments\mirrored-selfplay-deals-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065784.pt`
- Candidate checkpoint iter/hands: `16` / `65784`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.34 | +24.80 | -25.49 | +/-0.97 | 0.0000 | VALID | 6/12/1006 | 54.5 |
| slumbot_free | 2,048 | +11.35 | +36.62 | -13.92 | +/-5.82 | 0.0000 | VALID | 240/231/553 | 67.5 |
| corrected_cfr96 | 2,048 | +11.37 | +38.48 | -15.74 | +/-27.52 | 0.0000 | VALID | 417/397/210 | 32.8 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
