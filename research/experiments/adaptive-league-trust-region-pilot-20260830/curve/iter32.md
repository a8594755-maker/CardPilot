# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T02:59:07.056596+00:00`
- Candidate: `adaptive_iter32`
- Candidate path: `research\experiments\adaptive-league-trust-region-pilot-20260830\production\checkpoints\checkpoint_iter000032_hands000000131843.pt`
- Candidate checkpoint iter/hands: `32` / `131843`
- Pairs per anchor: `2048`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 4,096 | +0.29 | +18.58 | -17.99 | +/-1.22 | 0.0000 | VALID | 6/8/2034 | 49.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
