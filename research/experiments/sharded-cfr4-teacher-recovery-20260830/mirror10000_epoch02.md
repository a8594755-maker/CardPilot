# V5 Mirrored-Deal Internal Eval

- Checked at: `2026-08-30T01:48:50.232576+00:00`
- Candidate: `CFR4-FULL-H64-SKL1-E2`
- Candidate path: `research\experiments\sharded-cfr4-teacher-recovery-20260830\adapter_cfr4_full_h64_skl1_l2p01_epoch02.pt`
- Candidate checkpoint iter/hands: `313` / `10283876`
- Pairs per anchor: `10000`
- Starting stack: `200.0` bb
- Device: `cuda`
- Policy mode: `greedy_argmax_both_sides`

This is an internal mirrored-deal measuring stick. It is not a Slumbot benchmark and cannot support L5/L6 claims.

## Results

| anchor | hands | overall bb/100 | BB bb/100 | SB bb/100 | 95% CI (overall) | anchor OOD rate | OOD gate | pair W/L/D | h/s |
|---|---:|---:|---:|---:|---:|---:|---|---|---:|
| Standard10 | 20,000 | +1.45 | +20.18 | -17.29 | +/-0.56 | 0.0000 | VALID | 476/304/9220 | 116.5 |

## Validity Gate

- Anchor OOD validity threshold: `0.15`
- All anchors pass OOD gate: `True`
- Internal signal gate pass: `True`

## Gate Notes

- EXP-001 target gate is CI <= +/-20 bb/100 at 10k mirrored pairs.
- Anchor OOD must be at or below the validity threshold before the mirror row can be used as an internal progress signal.
- Later method experiments should use this as a progress signal, not as a strength claim.
- Official strength remains greedy policy versus Slumbot with the 100k+ CI rule.
