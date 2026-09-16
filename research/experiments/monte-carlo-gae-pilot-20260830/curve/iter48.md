# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T17:07:53.863737+00:00`
- Candidate: `monte_carlo_gae_iter48`
- Candidate path: `research\experiments\monte-carlo-gae-pilot-20260830\production\checkpoints\checkpoint_iter000048_hands000000197620.pt`
- Candidate checkpoint iter/hands: `48` / `197620`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.22 | +25.98 | -25.54 | +/-0.47 | 0.0000 | VALID | 8/5/1011 | 56.2 |
| slumbot_free | 2,048 | +10.90 | +36.62 | -14.82 | +/-5.76 | 0.0000 | VALID | 236/227/561 | 71.3 |
| corrected_cfr96 | 2,048 | +9.43 | +36.91 | -18.04 | +/-27.53 | 0.0000 | VALID | 419/404/201 | 37.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
