# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T12:57:00.761693+00:00`
- Candidate: `kbest_iter64_seed20260854`
- Candidate path: `research\experiments\seeded-historical-kbest-league-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263581.pt`
- Candidate checkpoint iter/hands: `64` / `263581`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.34 | +25.34 | -24.66 | +/-0.79 | 0.0000 | VALID | 9/8/1007 | 85.0 |
| slumbot_free | 2,048 | +15.63 | +36.12 | -4.87 | +/-6.33 | 0.0000 | VALID | 261/213/550 | 121.1 |
| corrected_cfr96 | 2,048 | -1.54 | +16.83 | -19.91 | +/-8.44 | 0.0000 | VALID | 436/416/172 | 64.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
