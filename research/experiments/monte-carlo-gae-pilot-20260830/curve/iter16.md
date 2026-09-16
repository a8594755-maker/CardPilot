# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T17:03:27.132171+00:00`
- Candidate: `monte_carlo_gae_iter16`
- Candidate path: `research\experiments\monte-carlo-gae-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065824.pt`
- Candidate checkpoint iter/hands: `16` / `65824`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.27 | +25.49 | -26.03 | +/-0.66 | 0.0000 | VALID | 6/12/1006 | 55.8 |
| slumbot_free | 2,048 | +11.38 | +36.23 | -13.47 | +/-5.80 | 0.0000 | VALID | 239/229/556 | 71.0 |
| corrected_cfr96 | 2,048 | +10.07 | +37.05 | -16.90 | +/-27.51 | 0.0000 | VALID | 417/405/202 | 37.2 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
