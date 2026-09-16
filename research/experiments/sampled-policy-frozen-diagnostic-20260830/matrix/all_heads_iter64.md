# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T19:16:59.062132+00:00`
- Candidate: `all_heads_iter64_sampled`
- Candidate path: `research\experiments\adaptive-league-all-heads-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263602.pt`
- Candidate checkpoint iter/hands: `64` / `263602`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | -0.64 | +10.73 | -12.02 | +/-8.38 | 0.0000 | VALID | 58/40/3998 | 113.9 |
| slumbot_free | 8,192 | +11.56 | +39.51 | -16.39 | +/-9.82 | 0.0000 | VALID | 923/886/2287 | 153.3 |
| corrected_cfr96 | 8,192 | +24.68 | +39.79 | +9.56 | +/-41.82 | 0.0000 | VALID | 1596/1659/841 | 84.0 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
