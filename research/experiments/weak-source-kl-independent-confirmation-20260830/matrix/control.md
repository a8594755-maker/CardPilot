# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T01:22:09.856810+00:00`
- Candidate: `weak_kl_confirmation_control`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\weak-source-kl-pilot-20260830\frozen\control.pt`
- Candidate checkpoint iter/hands: `54` / `222200`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +2.67 | +24.28 | -18.93 | +/-6.71 | 0.0000 | VALID | 72/74/8046 | 117.6 |
| slumbot_free | 16,384 | +16.56 | +36.94 | -3.82 | +/-11.07 | 0.0000 | VALID | 1771/1752/4669 | 151.6 |
| corrected_cfr96 | 16,384 | +59.59 | +113.40 | +5.78 | +/-31.12 | 0.0000 | VALID | 3171/3333/1688 | 79.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
