# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T18:14:04.137226+00:00`
- Candidate: `counterfactual_soft_iter64`
- Candidate path: `research\experiments\counterfactual-soft-policy-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263417.pt`
- Candidate checkpoint iter/hands: `64` / `263417`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.12 | +25.29 | -25.54 | +/-0.79 | 0.0000 | VALID | 5/6/1013 | 55.6 |
| slumbot_free | 2,048 | +11.14 | +36.62 | -14.34 | +/-5.93 | 0.0000 | VALID | 239/229/556 | 71.5 |
| corrected_cfr96 | 2,048 | +19.94 | +56.99 | -17.12 | +/-33.08 | 0.0000 | VALID | 420/401/203 | 37.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
