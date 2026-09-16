# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T04:27:24.795788+00:00`
- Candidate: `policy_head_iter16`
- Candidate path: `research\experiments\adaptive-league-policy-head-pilot-20260830\production\checkpoints\checkpoint_iter000016_hands000000065829.pt`
- Candidate checkpoint iter/hands: `16` / `65829`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.73 | +15.38 | -13.92 | +/-0.60 | 0.0000 | VALID | 7/0/1017 | 56.3 |
| slumbot_free | 2,048 | +21.07 | +50.55 | -8.41 | +/-19.25 | 0.0000 | VALID | 235/211/578 | 72.8 |
| corrected_cfr96 | 2,048 | -6.90 | +2.62 | -16.42 | +/-7.57 | 0.0000 | VALID | 414/417/193 | 39.2 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
