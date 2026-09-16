# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T00:55:10.979412+00:00`
- Candidate: `weak_batch_pilot_control`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\weak-source-kl-pilot-20260830\frozen\control.pt`
- Candidate checkpoint iter/hands: `54` / `222200`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.04 | +28.02 | -27.93 | +/-0.54 | 0.0000 | VALID | 32/39/4025 | 118.2 |
| slumbot_free | 8,192 | +21.23 | +40.08 | +2.38 | +/-16.14 | 0.0000 | VALID | 915/886/2295 | 148.4 |
| corrected_cfr96 | 8,192 | +81.63 | +94.70 | +68.55 | +/-40.82 | 0.0000 | VALID | 1643/1666/787 | 81.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
