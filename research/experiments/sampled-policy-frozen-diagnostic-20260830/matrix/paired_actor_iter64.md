# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T19:20:54.392405+00:00`
- Candidate: `paired_actor_iter64_sampled`
- Candidate path: `research\experiments\paired-seat-average-actor-pilot-20260830\production\checkpoints\checkpoint_iter000064_hands000000263479.pt`
- Candidate checkpoint iter/hands: `64` / `263479`
- Pairs per anchor: `4096`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `sampled_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| standard10 | 8,192 | -4.04 | +9.80 | -17.87 | +/-6.61 | 0.0000 | VALID | 57/52/3987 | 118.1 |
| slumbot_free | 8,192 | +12.27 | +39.91 | -15.38 | +/-9.82 | 0.0000 | VALID | 932/887/2277 | 151.7 |
| corrected_cfr96 | 8,192 | +23.02 | +41.33 | +4.70 | +/-41.54 | 0.0000 | VALID | 1589/1661/846 | 75.3 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `False`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength requires a frozen policy versus Slumbot with the 100k+ CI rule.
