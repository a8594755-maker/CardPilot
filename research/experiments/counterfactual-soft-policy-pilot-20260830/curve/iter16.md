# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T18:07:25.338601+00:00`
- Candidate: `counterfactual_soft_iter16`
- Candidate path: `research\experiments\counterfactual-soft-policy-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065873.pt`
- Candidate checkpoint iter/hands: `16` / `65873`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.24 | +26.17 | -25.68 | +/-0.49 | 0.0000 | VALID | 6/6/1012 | 55.7 |
| slumbot_free | 2,048 | +11.44 | +36.62 | -13.74 | +/-5.81 | 0.0000 | VALID | 240/229/555 | 72.3 |
| corrected_cfr96 | 2,048 | +8.73 | +36.81 | -19.35 | +/-27.43 | 0.0000 | VALID | 416/404/204 | 38.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
