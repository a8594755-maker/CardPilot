# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T15:31:41.618963+00:00`
- Candidate: `allin_ev_iter64`
- Candidate path: `research\experiments\allin-runout-ev-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263472.pt`
- Candidate checkpoint iter/hands: `64` / `263472`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.15 | +25.68 | -25.39 | +/-0.74 | 0.0000 | VALID | 6/8/1010 | 98.9 |
| slumbot_free | 2,048 | +10.73 | +35.84 | -14.38 | +/-6.06 | 0.0000 | VALID | 240/231/553 | 138.8 |
| corrected_cfr96 | 2,048 | +20.68 | +56.37 | -15.01 | +/-33.08 | 0.0000 | VALID | 418/397/209 | 74.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
