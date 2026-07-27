# V5 Loss Inference Audit

- Status: `PASS_DESCRIPTIVE_INFERENCE_AUDIT`
- Evidence class: `DESCRIPTIVE_LOCALIZATION_WITH_CLUSTER_UNCERTAINTY`
- Candidate hands / sessions: `5,000` / `4`
- Candidate bb/100: `-146.173`
- Decision: `LOCALIZE_ONLY_COUNTERFACTUAL_OR_CONTROL_REQUIRED_FOR_INTERVENTION`

Realized losses localize where outcomes occurred. They do **not** identify the EV of an unchosen action or action regret. This artifact cannot authorize tuning by itself.

## position

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `BB` | 2,500 | 0.500 | 0.500 | -139.71 | [-262.24, -17.18] | 86.71 | 0.394 |
| `SB` | 2,500 | 0.500 | 0.500 | -152.64 | [-211.48, -93.80] | 35.30 | 0.394 |

## terminal

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `opp_fold` | 3,327 | 0.665 | 0.665 | 657.72 | [633.49, 688.94] | 41.11 | 0.008 |
| `hero_fold` | 1,114 | 0.223 | 0.223 | -1197.50 | [-1335.04, -1088.56] | -8.00 | 0.965 |
| `showdown` | 506 | 0.101 | 0.101 | -2381.60 | [-2676.87, -2130.46] | -1775.50 | 0.000 |

## terminal_street

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `opp_fold@flop` | 1,469 | 0.294 | 0.442 | 480.53 | [451.53, 511.03] | -33.00 | 0.135 |
| `opp_fold@preflop` | 1,094 | 0.219 | 0.329 | 278.70 | [240.62, 314.88] | 5.87 | 0.789 |
| `showdown@river` | 506 | 0.101 | 1.000 | -2381.60 | [-2676.87, -2130.46] | -1775.50 | 0.000 |
| `opp_fold@turn` | 496 | 0.099 | 0.149 | 1208.11 | [1148.49, 1269.69] | -375.70 | 0.000 |
| `hero_fold@flop` | 436 | 0.087 | 0.391 | -789.02 | [-931.91, -708.50] | 183.48 | 0.064 |
| `hero_fold@preflop` | 331 | 0.066 | 0.297 | -800.30 | [-916.51, -690.87] | 115.00 | 0.567 |
| `opp_fold@river` | 268 | 0.054 | 0.081 | 2157.53 | [1865.40, 2557.85] | -241.87 | 0.341 |
| `hero_fold@turn` | 178 | 0.036 | 0.160 | -1787.18 | [-1954.79, -1647.22] | -630.66 | 0.000 |
| `hero_fold@river` | 169 | 0.034 | 0.152 | -2408.18 | [-2659.07, -2154.55] | -124.04 | 0.666 |

## first_preflop_decision

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `sb_open_raise_lt2.5bb` | 2,479 | 0.496 | 0.992 | -152.36 | [-212.39, -92.17] | 35.59 | 0.813 |
| `bb_vs_open_lt2.5bb_raise_4-8bb` | 2,093 | 0.419 | 0.929 | -166.84 | [-310.00, -21.06] | 94.36 | 0.813 |
| `no_hero_preflop` | 246 | 0.049 | 1.000 | 50.00 | [50.00, 50.00] | 0.00 | 1.000 |
| `bb_vs_open_lt2.5bb_f` | 141 | 0.028 | 0.063 | -100.00 | [-100.00, -100.00] | 0.00 | 1.000 |

## hole_family

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `other_offsuit` | 2,666 | 0.533 | 0.533 | -142.63 | [-246.70, -39.73] | 125.73 | 0.196 |
| `other_suited` | 667 | 0.133 | 0.133 | -38.90 | [-113.10, 39.65] | 196.18 | 0.196 |
| `broadway_offsuit` | 454 | 0.091 | 0.091 | -68.60 | [-278.92, 134.45] | 234.84 | 0.196 |
| `pair` | 305 | 0.061 | 0.061 | -39.64 | [-461.29, 413.57] | -166.79 | 0.597 |
| `suited_connector` | 249 | 0.050 | 0.050 | -357.91 | [-697.55, 19.14] | -367.97 | 0.196 |
| `ace_offsuit` | 195 | 0.039 | 0.039 | -395.56 | [-628.73, -237.18] | 343.16 | 0.196 |
| `broadway_suited` | 164 | 0.033 | 0.033 | -166.42 | [-377.30, -23.86] | -303.17 | 0.254 |
| `wheel_ace_offsuit` | 163 | 0.033 | 0.033 | -447.97 | [-884.32, -39.33] | -446.68 | 0.196 |

## hole_combo

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|

## preflop_line

| slice | n | total share | context rate | bb/100 | cluster CI | baseline delta | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|
| `H:b200 O:c` | 1,743 | 0.349 | 0.349 | -23.81 | [-154.07, 71.92] | 1.31 | 1.000 |
| `O:b200 H:b400 O:c` | 1,376 | 0.275 | 0.275 | -292.98 | [-405.61, -191.30] | 87.11 | 1.000 |
| `O:b200 H:b400 O:f` | 530 | 0.106 | 0.106 | 200.00 | [200.00, 200.00] | 0.00 | 1.000 |
| `H:b200 O:b600 H:b1200 O:c` | 284 | 0.057 | 0.057 | -673.19 | [-1406.10, 257.64] | 324.47 | 1.000 |
| `O:f` | 246 | 0.049 | 0.049 | 50.00 | [50.00, 50.00] | 0.00 | 1.000 |
| `O:b200 H:f` | 141 | 0.028 | 0.028 | -100.00 | [-100.00, -100.00] | 0.00 | 1.000 |
| `H:b200 O:f` | 138 | 0.028 | 0.028 | 100.00 | [100.00, 100.00] | 0.00 | 1.000 |
| `H:b200 O:b600 H:b1200 O:f` | 129 | 0.026 | 0.026 | 600.00 | [600.00, 600.00] | 0.00 | 1.000 |

## Interpretation contract

- Allowed: localization, uncertainty-aware association, and hypothesis design.
- Forbidden: treating hero-fold loss, a losing line, or a hole-family loss as counterfactual action regret.
- Required before action-specific tuning: a validated counterfactual estimator or a registered same-state/same-start controlled experiment.
