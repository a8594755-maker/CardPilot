# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T16:07:20.938661+00:00`
- Candidate: `mirrored_selfplay_iter48`
- Candidate path: `research\experiments\mirrored-selfplay-deals-pilot-20260830\production\checkpoints\checkpoint_iter000048_hands000000197599.pt`
- Candidate checkpoint iter/hands: `48` / `197599`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.37 | +24.80 | -25.54 | +/-0.84 | 0.0000 | VALID | 5/9/1010 | 93.5 |
| slumbot_free | 2,048 | +11.32 | +36.62 | -13.99 | +/-5.79 | 0.0000 | VALID | 239/229/556 | 120.2 |
| corrected_cfr96 | 2,048 | +10.94 | +38.00 | -16.12 | +/-27.52 | 0.0000 | VALID | 418/401/205 | 70.3 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
