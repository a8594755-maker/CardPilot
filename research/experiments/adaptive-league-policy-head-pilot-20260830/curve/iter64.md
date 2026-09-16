# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T04:34:07.443201+00:00`
- Candidate: `policy_head_iter64`
- Candidate path: `research\experiments\adaptive-league-policy-head-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263464.pt`
- Candidate checkpoint iter/hands: `64` / `263464`
- Pairs per anchor: `1024`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 2,048 | +0.10 | +13.82 | -13.62 | +/-0.43 | 0.0000 | VALID | 3/3/1018 | 57.9 |
| slumbot_free | 2,048 | +21.04 | +50.29 | -8.22 | +/-19.27 | 0.0000 | VALID | 235/210/579 | 72.6 |
| corrected_cfr96 | 2,048 | +2.66 | +20.85 | -15.54 | +/-20.54 | 0.0000 | VALID | 415/418/191 | 40.1 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
