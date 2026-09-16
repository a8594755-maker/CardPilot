# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T13:27:13.961160+00:00`
- Candidate: `i200_control_epoch2`
- Candidate path: `research\experiments\sharded-cfr4-teacher-recovery-20260830\adapter_cfr4_full_h64_skl1_l2p01_epoch02.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +1.07 | +21.13 | -18.99 | +/-1.39 | 0.0000 | VALID | 104/70/1874 | 100.7 |
| slumbot_free | 4,096 | +12.20 | +33.26 | -8.85 | +/-4.35 | 0.0000 | VALID | 490/468/1090 | 125.9 |
| corrected_cfr96 | 4,096 | -7.08 | -1.38 | -12.77 | +/-14.40 | 0.0000 | VALID | 880/841/327 | 72.0 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
