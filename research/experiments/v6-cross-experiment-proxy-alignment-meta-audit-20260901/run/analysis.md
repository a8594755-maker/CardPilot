# Proxy alignment meta-audit

## Same-policy 5k to 20k

| Policy | 5k bb/100 | 20k bb/100 | 5k optimism |
|---|---:|---:|---:|
| standard10 | -15.7900 | -24.5683 | +8.7783 |
| legacy_iter16 | +19.4600 | -37.1617 | +56.6217 |
| procedural_soup | +9.0452 | -41.8162 | +50.8614 |
| actor_raw | -9.4188 | -46.5992 | +37.1804 |
| mgda_seed1_12k | -11.1100 | -47.5250 | +36.4150 |

## Internal-pass routes

| Route | Internal decision | External bb/100 |
|---|---|---:|
| physical_1m | `ADMIT_SEPARATE_SLUMBOT_PILOT` | -137.7392 |
| representation_full | `REPRESENTATION_SCOPE_REPLICATION_PASSED` | -81.2510 |
| weak_source_kl | `WEAK_KL_REPLICATION_PASSED` | -55.8690 |
| procedural_soup | `ADMIT_SEPARATE_GENERIC_GREEDY_SLUMBOT_FRESH5K` | -41.8162 |
| legacy_iter16 | `ADMIT_EXACT_ITER16_GREEDY_FRESH5K_SLUMBOT` | -37.1617 |
| mgda_seed1_12k | `HOLD_BEYOND_12K_ON_SEED1_SEAT_VARIANCE` | -47.5250 |

## Decision

`REQUIRE_MULTI_SEED_BROAD_HOLDOUT_CURVES_AND_20K_FIRST_EXTERNAL_GATE`

The promoted 5k pilots are selection-biased, so optimism estimates describe this research process rather than an unbiased 5k estimator.
