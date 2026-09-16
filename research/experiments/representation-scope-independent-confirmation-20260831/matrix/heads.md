# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T06:01:16.452358+00:00`
- Candidate: `representation_confirmation_heads`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\heads.pt`
- Candidate checkpoint iter/hands: `107` / `440811`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +91.37 | +18.52 | +164.23 | +/-28.18 | 0.0000 | VALID | 1176/990/6026 | 51.7 |
| slumbot_free | 16,384 | +24.85 | +28.25 | +21.45 | +/-22.30 | 0.0000 | VALID | 2381/2187/3624 | 63.6 |
| corrected_cfr96 | 16,384 | +119.38 | +58.13 | +180.64 | +/-48.04 | 0.0000 | VALID | 3292/2937/1963 | 37.6 |
| heldout_weak | 16,384 | +28.40 | -6.78 | +63.57 | +/-24.50 | 0.0000 | VALID | 583/480/7129 | 46.6 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
