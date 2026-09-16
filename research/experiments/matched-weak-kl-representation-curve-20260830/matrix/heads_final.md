# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T04:44:37.059041+00:00`
- Candidate: `representation_curve_heads_final`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\heads.pt`
- Candidate checkpoint iter/hands: `107` / `440811`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +21.89 | +20.96 | +22.83 | +/-37.71 | 0.0000 | VALID | 581/511/3004 | 51.9 |
| slumbot_free | 8,192 | +31.11 | +49.88 | +12.34 | +/-31.68 | 0.0000 | VALID | 1208/1086/1802 | 64.3 |
| corrected_cfr96 | 8,192 | +141.99 | +94.41 | +189.56 | +/-67.12 | 0.0000 | VALID | 1635/1515/946 | 37.5 |
| heldout_weak | 8,192 | +14.50 | -11.94 | +40.94 | +/-31.26 | 0.0000 | VALID | 292/250/3554 | 47.8 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
