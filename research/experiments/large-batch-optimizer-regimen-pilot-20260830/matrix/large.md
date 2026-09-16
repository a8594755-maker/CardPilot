# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T22:59:56.188117+00:00`
- Candidate: `large_batch_pilot_large`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\large-batch-optimizer-regimen-pilot-20260830\frozen\large.pt`
- Candidate checkpoint iter/hands: `14` / `114997`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | +0.72 | +23.67 | -22.23 | +/-0.77 | 0.0000 | VALID | 54/37/4005 | 120.9 |
| slumbot_free | 8,192 | +15.09 | +30.53 | -0.35 | +/-14.61 | 0.0000 | VALID | 918/891/2287 | 151.8 |
| corrected_cfr96 | 8,192 | +29.32 | +78.98 | -20.34 | +/-41.72 | 0.0000 | VALID | 1618/1599/879 | 81.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
