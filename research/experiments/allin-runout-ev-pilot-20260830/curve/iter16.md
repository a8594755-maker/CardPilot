# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T15:28:08.694906+00:00`
- Candidate: `allin_ev_iter16`
- Candidate path: `research\experiments\allin-runout-ev-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065851.pt`
- Candidate checkpoint iter/hands: `16` / `65851`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.10 | +25.59 | -25.78 | +/-0.63 | 0.0000 | VALID | 6/3/1015 | 119.4 |
| slumbot_free | 2,048 | +10.88 | +37.01 | -15.26 | +/-5.86 | 0.0000 | VALID | 236/225/563 | 119.9 |
| corrected_cfr96 | 2,048 | +9.31 | +36.52 | -17.90 | +/-27.59 | 0.0000 | VALID | 420/405/199 | 74.8 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
