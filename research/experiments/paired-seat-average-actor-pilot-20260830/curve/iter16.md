# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T18:56:58.214380+00:00`
- Candidate: `paired_seat_iter16`
- Candidate path: `research\experiments\paired-seat-average-actor-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065912.pt`
- Candidate checkpoint iter/hands: `16` / `65912`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.27 | +26.56 | -26.03 | +/-0.49 | 0.0000 | VALID | 7/5/1012 | 116.0 |
| slumbot_free | 2,048 | +10.88 | +36.62 | -14.87 | +/-5.83 | 0.0000 | VALID | 236/226/562 | 147.7 |
| corrected_cfr96 | 2,048 | +10.32 | +38.04 | -17.41 | +/-27.54 | 0.0000 | VALID | 421/405/198 | 63.7 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
