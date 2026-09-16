# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T12:03:00.877664+00:00`
- Candidate: `replay_iter16`
- Candidate path: `research\experiments\alpha-replay-buffer-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065794.pt`
- Candidate checkpoint iter/hands: `16` / `65794`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | -0.56 | +24.80 | -25.93 | +/-0.87 | 0.0000 | VALID | 5/12/1007 | 118.9 |
| slumbot_free | 2,048 | +11.95 | +36.62 | -12.72 | +/-5.81 | 0.0000 | VALID | 241/229/554 | 154.4 |
| corrected_cfr96 | 2,048 | +10.25 | +38.68 | -18.17 | +/-27.43 | 0.0000 | VALID | 419/399/206 | 72.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
