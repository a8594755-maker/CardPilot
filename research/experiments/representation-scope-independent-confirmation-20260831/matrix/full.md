# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-31T06:29:16.982729+00:00`
- Candidate: `representation_confirmation_full`
- Candidate path: `C:\Users\a8594\CardPilot\research\experiments\matched-weak-kl-representation-curve-20260830\frozen\full.pt`
- Candidate checkpoint iter/hands: `105` / `432347`
- Pairs per anchor: `8192`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 16,384 | +202.10 | +93.63 | +310.58 | +/-59.78 | 0.0000 | VALID | 2773/2504/2915 | 41.0 |
| slumbot_free | 16,384 | +339.32 | +80.41 | +598.24 | +/-64.86 | 0.0000 | VALID | 3445/3308/1439 | 49.3 |
| corrected_cfr96 | 16,384 | +712.75 | +752.49 | +673.02 | +/-78.81 | 0.0000 | VALID | 2879/2685/2628 | 32.0 |
| heldout_weak | 16,384 | +184.69 | +41.32 | +328.06 | +/-64.74 | 0.0000 | VALID | 2412/2528/3252 | 38.2 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
