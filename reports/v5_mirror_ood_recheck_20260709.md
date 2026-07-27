# V5 Mirror OOD Recheck

- Checked at: `2026-07-09T11:41:56.7340893Z`
- Anchor OOD validity threshold: `0.15`
- Scope: existing mirrored-deal JSON artifacts with `anchor_ood_node_rate` under `models/` and `reports/`.

## Summary

- Rows scanned: `11`
- Rows valid at threshold: `3`
- Rows invalid/retro-suspect at threshold: `8`
- High-OOD V4-anchor rows must not be used for progress, plateau, V4-strength, Slumbot, L5, or L6 judgments.

## Rows

| checked_at | candidate | iter | hands | anchor | pairs | bb/100 | CI95 | anchor OOD | OOD gate | artifact |
|---|---|---:|---:|---|---:|---:|---:|---:|---|---|
| 2026-07-07T06:25:13.895043+00:00 | current_latest_smoke | 10800 | 177210246 | v4 | 20 | -28.4 | 145.11 | 0.117021 | VALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1/v5_mirror_eval_exp001_followup_smoke_20p_20260707.json` |
| 2026-07-07T06:45:09.183864+00:00 | active_10900_followup | 10900 | 178851139 | v4 | 10000 | -69.318 | 16.22 | 0.198347 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1/v5_mirror_eval_exp001_followup_gate10900_v4_10kp_20260707.json` |
| 2026-07-08T04:03:46.706696+00:00 | candidate | 12700 | 208385405 | alpha_holdem_v4_final | 5000 | -55.722 | 17.548 | 0.243367 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707/v5_mirror_exp004_gate12700_vs_v4.json` |
| 2026-07-08T04:04:11.688979+00:00 | candidate | 12700 | 208385405 | alpha_holdem_v4_final | 2000 | -48.824 | 29.502 | 0.23888 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707/v5_mirror_exp004_vs_v4_2k.json` |
| 2026-07-08T04:06:19.679571+00:00 | candidate | 12700 | 208385405 | alpha_holdem_v4_final | 3000 | -54.212 | 23.783 | 0.242828 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707/v5_mirror_exp004_vs_v4_12700.json` |
| 2026-07-08T04:09:11.312948+00:00 | candidate | 12700 | 208385405 | alpha_holdem_v4_final | 2000 | -48.824 | 29.502 | 0.23888 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707/v5_mirror_exp004_judgment_2k.json` |
| 2026-07-08T13:43:00.457797+00:00 | exp004_step2_gate13800 | 13800 | 226434446 | alpha_holdem_v4_final | 5000 | -73.406 | 23.671 | 0.213935 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre0005_r1_20260708/v5_mirror_exp004_step2_gate13800_vs_v4_5kp.json` |
| 2026-07-08T17:09:13.151857+00:00 | exp002_exp004_followup_gate14300 | 14300 | 234651694 | alpha_holdem_v4_final | 10000 | -182.268 | 18.456 | 0.022845 | VALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre0005_exp002_multienv_r1_20260708/v5_mirror_exp002_exp004_followup_gate14300_vs_v4_10kp.json` |
| 2026-07-08T17:29:48.529133+00:00 | exp004_gate14000_preEXP002_coef0005_singleenv | 14000 | 229715962 | alpha_holdem_v4_final | 10000 | -156.304 | 18.481 | 0.060876 | VALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre0005_r1_20260708/v5_mirror_ISOLATE_gate14000_preEXP002_vs_v4_10kp.json` |
| 2026-07-09T06:50:23.899665+00:00 | stable001_recovery_gate19000_312M | 19000 | 311997917 | v4_final | 10000 | 4.11 | 9.513 | 0.547343 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_rollback_r1_20260708/v5_mirror_plateau_recovery_gate19000_vs_v4_10kp_20260709.json` |
| 2026-07-09T11:32:25.349734+00:00 | stable001_second_gate20700_340M | 20700 | 339965679 | v4_final | 10000 | -30.646 | 14.243 | 0.443618 | INVALID | `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_exp002_multienv_rollback_r1_20260708/v5_mirror_plateau_second_gate20700_340M_vs_v4_10kp_20260709.json` |

## Interpretation

- The 2026-07-09 recovery and second plateau mirrors are invalid under the OOD gate (`0.547343` and `0.443618`).
- The EXP-004 step-1 mirror row at gate12700 (`-55.722 +/-17.548`) is retro-suspect under this stricter gate because anchor OOD was `0.243367`.
- The lower-OOD V4-anchor rows at gate14000 and gate14300 remain usable only as internal diagnostics; they still cannot support Slumbot/L5/L6 claims.
- Future mirror gates should use the patched OOD validity fields and a selected v55-native frozen anchor before being trusted as progress signals.
