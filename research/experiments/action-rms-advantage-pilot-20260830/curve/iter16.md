# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T14:52:07.234049+00:00`
- Candidate: `action_rms_iter16`
- Candidate path: `research\experiments\action-rms-advantage-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065910.pt`
- Candidate checkpoint iter/hands: `16` / `65910`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.15 | +24.80 | -25.10 | +/-1.19 | 0.0000 | VALID | 14/16/994 | 103.2 |
| slumbot_free | 2,048 | +11.31 | +35.45 | -12.83 | +/-6.20 | 0.0000 | VALID | 244/235/545 | 138.5 |
| corrected_cfr96 | 2,048 | +5.35 | +26.10 | -15.40 | +/-21.70 | 0.0000 | VALID | 421/396/207 | 75.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
