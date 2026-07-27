# RL-1 5M vs BC anchor: per-position / per-street edge-loss analysis

Both checkpoints evaluated under identical conditions (seed=42, 20400 hands per opponent).

Source: `reports/phase2/rl1_5M_final_eval/`. RL-1 ckpt: `models/ppo/rl1_5M_run1/ckpt_5M.pt`. BC ckpt: `models/bc/v3_anchor_5M_d1_light/best.pt`.

## Per-opponent overall + position split

| opp | BC bb/100 | RL bb/100 | Δ | BC SB | RL SB | Δ SB | BC BB | RL BB | Δ BB |
|:--|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fold | +8.99 | +4.71 | -4.28 | -32.32 | -40.91 | -8.59 | +50.00 | +50.00 | +0.00 |
| call | +2.50 | +4.17 | +1.67 | -17.69 | -30.54 | -12.85 | +22.63 | +38.78 | +16.15 |
| random | +185.30 | +224.69 | +39.39 | +137.11 | +193.34 | +56.23 | +233.28 | +255.91 | +22.63 |
| heuristic_v3 | +5.24 | +1.93 | -3.31 | -27.22 | -32.43 | -5.21 | +37.49 | +36.08 | -1.41 |
| scripted_aggro | +26.86 | +17.97 | -8.89 | +25.38 | +34.08 | +8.70 | +28.35 | +1.93 | -26.42 |
| scripted_station | +2.50 | +3.97 | +1.47 | -17.69 | -30.70 | -13.01 | +22.63 | +38.53 | +15.90 |
| scripted_jammer | +19.31 | +39.32 | +20.01 | -29.94 | -7.45 | +22.49 | +68.17 | +85.76 | +17.59 |
| pathb10m | +4.94 | +4.44 | -0.50 | -33.59 | -37.46 | -3.87 | +43.23 | +46.09 | +2.86 |
| **slumbot** | -42.84 | -57.13 | -14.29 | — | — | — | — | — | — |

### Summary
- Mean Δ total: +5.69 bb/100
- Mean Δ SB:    +5.49 bb/100  (RL-1 lost ~9 bb/100 from SB across opponents)
- Mean Δ BB:    +5.91 bb/100  (RL-1 gained on BB)
- Slumbot Δ:    -14.29 bb/100  (significant regression)

## Per-street action-mix shift (RL-1 − BC, percentage points)

Reading guide: positive = RL-1 used MORE; negative = RL-1 used LESS than BC anchor.
Threshold: only |shift| ≥ 2% shown.

### vs fold
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=90.5% cc=8.0% | fold=+2.8 |
| FLOP | cc=86.2% rS=10.7% rBIG=2.1% | cc=+60.1 rS=-49.0 rM=-13.3 rBIG=+2.1 |
| TURN | cc=94.5% rS=3.6% | cc=+40.9 rS=-18.5 rM=-22.8 |
| RIV | cc=96.1% | cc=+36.7 rS=-27.0 rM=-10.3 |

### vs call
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=90.3% cc=8.1% | fold=+2.3 |
| FLOP | cc=81.7% rS=12.3% rM=5.4% | cc=+53.0 rS=-47.1 rM=-6.5 |
| TURN | cc=83.3% rS=9.8% rM=6.4% | cc=+58.0 rS=-45.6 rM=-13.0 |
| RIV | cc=84.5% rS=7.8% rM=7.2% | cc=+59.8 rS=-50.1 rM=-10.3 |

### vs random
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=89.6% cc=8.6% | fold=+3.0 |
| FLOP | fold=35.1% cc=55.9% rS=6.0% rM=2.7% | fold=+5.7 cc=+30.5 rS=-32.0 rM=-4.5 |
| TURN | fold=18.9% cc=71.1% rS=5.7% rM=3.9% | cc=+47.6 rS=-41.3 rM=-8.1 |
| RIV | fold=9.6% cc=82.9% rS=3.7% rM=3.5% | fold=-6.0 cc=+58.4 rS=-44.2 rM=-8.6 |

### vs heuristic_v3
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=89.8% cc=8.1% rBIG=2.1% | fold=+3.1 |
| FLOP | fold=17.0% cc=70.7% rS=8.5% rM=3.1% | fold=+3.6 cc=+43.8 rS=-40.6 rM=-7.5 |
| TURN | fold=11.3% cc=76.4% rS=7.9% rM=3.6% | cc=+51.6 rS=-40.2 rM=-11.5 |
| RIV | fold=11.1% cc=77.9% rS=6.6% rM=3.7% | fold=-5.0 cc=+52.0 rS=-37.9 rM=-9.7 |

### vs scripted_aggro
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=88.1% cc=8.6% rBIG=3.3% | fold=+4.2 rBIG=-2.4 |
| FLOP | fold=29.1% cc=63.9% rS=6.0% | fold=-11.5 cc=+37.2 rS=-20.0 rM=-6.2 |
| TURN | fold=6.0% cc=84.2% rS=7.8% | fold=-8.0 cc=+55.3 rS=-33.3 rM=-15.0 |
| RIV | cc=74.5% rS=19.0% rM=4.5% rBIG=2.0% | cc=+59.3 rS=-40.2 rM=-21.0 rBIG=+2.0 |

### vs scripted_station
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=90.3% cc=8.1% | fold=+2.3 |
| FLOP | cc=81.7% rS=12.3% rM=5.4% | cc=+53.0 rS=-47.1 rM=-6.5 |
| TURN | cc=83.3% rS=9.8% rM=6.4% | cc=+58.0 rS=-45.6 rM=-13.0 |
| RIV | cc=84.5% rS=7.8% rM=7.2% | cc=+59.8 rS=-50.1 rM=-10.3 |

### vs scripted_jammer
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=90.5% cc=8.0% | fold=+2.6 |
| FLOP | fold=10.2% cc=79.9% rS=7.4% rBIG=2.1% | fold=-4.9 cc=+54.7 rS=-41.0 rM=-10.9 rBIG=+2.1 |
| TURN | fold=7.2% cc=86.0% rS=5.4% | fold=-5.3 cc=+56.1 rS=-43.6 rM=-8.2 |
| RIV | fold=10.8% cc=85.6% rS=2.9% | fold=-17.5 cc=+40.9 rS=-16.7 rM=-7.2 |

### vs pathb10m
| street | RL-1 mix | shift vs BC |
|:--|:--|:--|
| PRE | fold=90.5% cc=7.8% | fold=+3.5 |
| FLOP | fold=42.7% cc=55.5% | fold=-23.3 cc=+29.7 rS=-4.9 |
| TURN | fold=10.7% cc=89.3% | fold=-20.1 cc=+25.1 rS=-3.5 |
| RIV | fold=6.5% cc=93.0% | fold=-29.2 cc=+33.5 rS=-3.6 |

## Aggregated per-street shift (averaged across 8 opponents)

| street | mean RL-1 − BC shift |
|:--|:--|
| PRE | fold=+3.0 |
| FLOP | fold=-3.8 cc=+45.3 rS=-35.2 rM=-7.1 |
| TURN | fold=-4.1 cc=+49.1 rS=-33.9 rM=-11.6 |
| RIV | fold=-7.2 cc=+50.1 rS=-33.7 rM=-9.8 |

## Diagnosis

1. **Postflop collapse to passive**: averaged across opponents, RL-1 on FLOP cc shifted **+45.3**pp, small-raise **-35.2**pp, medium-raise **-7.1**pp. Same pattern on TURN/RIV.
2. **Asymmetric SB profile**: SB gain vs random/jammer/aggro masks regressions of −3 to −13 bb/100 vs realistic opponents (fold, call, heuristic_v3, station, pathb10m, slumbot). Mean Δ SB = +5.5 bb/100 but this is an artifact of large gains vs exploitable opponents.
3. **Gain vs aggressive opponents BB**: jammer +18, station +16, call +16, random +23 bb/100 — cc-bot survives well against jam/bluff opponents because they fold less and inflate pots we win.
4. **Slumbot regression confirmed**: RL-1 5M vs Slumbot -57.13 bb/100 vs BC -42.84 bb/100 (Δ -14.29 bb/100, |Δ| > CI ±21.9 so significant).

### Root cause hypothesis
- Per `reports/rl1_5M_history_analysis.md`: value_loss U-shape (cold-start 703 → recovered 1.2 → re-exploded 1372).
- Cold critic at iter 1-2 + KL collapse to call-only on iter 2 (cc=0.08%) → policy explored a passive basin.
- Anchor KL pull recovered CC mass starting iter 22 but never restored raise mass; raises remained ~10% vs BC ~50%.
- Net result: policy retained anchor proximity in fold/cc dimensions but lost the **value-betting** + **bluffing** structure.

### Implication for RL-2
Value-head warmup alone may not be sufficient. Consider:
- (a) Warm critic + cold policy (current plan).
- (b) Higher anchor_kl_coef at the start (e.g. 0.2 → decay) to prevent passive basin entry.
- (c) Add per-action anchor regularization on raise slots specifically (action-level KL).
- (d) Lower lr (3e-5 → 1e-5) for first 1M hands to slow drift while critic stabilizes.

Recommended minimal change: (a) + (d). Validate with 500k smoke before committing to RL-2 5M.