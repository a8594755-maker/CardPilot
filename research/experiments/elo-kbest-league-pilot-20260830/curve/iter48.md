# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T14:20:39.373060+00:00`
- Candidate: `elo_kbest_iter48`
- Candidate path: `research\experiments\elo-kbest-league-pilot-20260830\production\checkpoints\checkpoint_iter000048_hands000000197455.pt`
- Candidate checkpoint iter/hands: `48` / `197455`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.05 | +25.00 | -25.10 | +/-1.08 | 0.0000 | VALID | 11/13/1000 | 98.7 |
| slumbot_free | 2,048 | +11.07 | +35.84 | -13.69 | +/-6.10 | 0.0000 | VALID | 242/233/549 | 126.5 |
| corrected_cfr96 | 2,048 | +20.42 | +56.24 | -15.40 | +/-33.08 | 0.0000 | VALID | 417/397/210 | 70.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
