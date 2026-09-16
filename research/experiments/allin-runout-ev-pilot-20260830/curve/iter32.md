# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T15:29:17.547042+00:00`
- Candidate: `allin_ev_iter32`
- Candidate path: `research\experiments\allin-runout-ev-pilot-20260830\production\checkpoints\checkpoint_iter000032_hands000000131619.pt`
- Candidate checkpoint iter/hands: `32` / `131619`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.20 | +26.17 | -25.78 | +/-0.55 | 0.0000 | VALID | 6/7/1011 | 116.3 |
| slumbot_free | 2,048 | +11.63 | +36.62 | -13.35 | +/-5.80 | 0.0000 | VALID | 240/229/555 | 147.5 |
| corrected_cfr96 | 2,048 | +10.60 | +37.22 | -16.03 | +/-27.52 | 0.0000 | VALID | 419/400/205 | 78.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
