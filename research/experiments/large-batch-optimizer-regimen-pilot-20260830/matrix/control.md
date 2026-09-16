# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T22:56:09.741819+00:00`
- Candidate: `large_batch_pilot_control`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\large-batch-optimizer-regimen-pilot-20260830\frozen\control.pt`
- Candidate checkpoint iter/hands: `14` / `115056`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +1.06 | +24.25 | -22.14 | +/-0.71 | 0.0000 | VALID | 46/25/4025 | 126.0 |
| slumbot_free | 8,192 | +14.25 | +33.87 | -5.37 | +/-14.47 | 0.0000 | VALID | 915/890/2291 | 161.9 |
| corrected_cfr96 | 8,192 | +25.97 | +71.89 | -19.96 | +/-40.93 | 0.0000 | VALID | 1614/1603/879 | 87.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
