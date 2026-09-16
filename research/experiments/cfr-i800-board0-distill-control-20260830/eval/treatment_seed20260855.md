# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T13:24:44.101152+00:00`
- Candidate: `i800board0_epoch2`
- Candidate path: `research\experiments\cfr-i800-board0-distill-control-20260830\adapter_cfr4_i800board0_h64_skl1_l2p01_epoch02.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +1.91 | +23.40 | -19.57 | +/-1.46 | 0.0000 | VALID | 157/86/1805 | 112.1 |
| slumbot_free | 4,096 | +10.49 | +32.83 | -11.85 | +/-4.11 | 0.0000 | VALID | 488/472/1088 | 140.7 |
| corrected_cfr96 | 4,096 | -11.51 | +1.42 | -24.43 | +/-4.87 | 0.0000 | VALID | 866/860/322 | 79.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
