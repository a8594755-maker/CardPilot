# Real-GPU multi-environment throughput result

Decision: MULTIENV_FRESH_START_THROUGHPUT_QUALIFIED. Selected fresh-start configuration: multi8.

| Arm | Actual physical hands | Trainer wall hands/s | Excluding update1 logged hands/s | Median batch |
|---|---:|---:|---:|---:|
| single1 | 37332 | 98.676 | 106.917 | 3.30 |
| multi4 | 35845 | 246.504 | 282.937 | 11.90 |
| multi8 | 33650 | 341.185 | 404.908 | 23.20 |

All three trainer/session/numerical/counter/provenance audits passed. This ordered single-run comparison measures implementation throughput, not causal or multi-seed performance. Logged times are rounded and omit non-collection/PPO overhead; trainer wall rate includes it. Completed unconsumed worker tails are included in physical counts, not optimizer consumption. Worker normal shutdown and per-slot interrupted resume are not qualified. Zero evaluation or Slumbot hands; no short-arm checkpoint may be promoted.
