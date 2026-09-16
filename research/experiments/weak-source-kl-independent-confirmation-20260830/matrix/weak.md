# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T01:30:24.417901+00:00`
- Candidate: `weak_kl_confirmation_weak`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\weak-source-kl-pilot-20260830\frozen\weak.pt`
- Candidate checkpoint iter/hands: `54` / `222328`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +6.35 | +12.97 | -0.26 | +/-16.13 | 0.0000 | VALID | 1098/1048/6046 | 108.1 |
| slumbot_free | 16,384 | +23.13 | +24.37 | +21.89 | +/-19.83 | 0.0000 | VALID | 2293/2023/3876 | 128.8 |
| corrected_cfr96 | 16,384 | +124.44 | +169.98 | +78.90 | +/-42.95 | 0.0000 | VALID | 3301/3033/1858 | 77.9 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
