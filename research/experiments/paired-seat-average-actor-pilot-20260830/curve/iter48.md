# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T18:59:44.203559+00:00`
- Candidate: `paired_seat_iter48`
- Candidate path: `research\experiments\paired-seat-average-actor-pilot-20260830\production\checkpoints\checkpoint_iter000048_hands000000197655.pt`
- Candidate checkpoint iter/hands: `48` / `197655`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.24 | +25.78 | -25.29 | +/-0.68 | 0.0000 | VALID | 9/10/1005 | 118.2 |
| slumbot_free | 2,048 | +11.42 | +36.62 | -13.78 | +/-5.86 | 0.0000 | VALID | 242/232/550 | 155.0 |
| corrected_cfr96 | 2,048 | +10.18 | +37.33 | -16.96 | +/-27.45 | 0.0000 | VALID | 417/397/210 | 83.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
