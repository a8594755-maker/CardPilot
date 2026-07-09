# RL-1 5M history analysis

Source: `models\ppo\rl1_5M_run1\history.json` (100 iterations, 50k hands/iter)

## Value-head cold-start trajectory

| iter | hands | value_loss | policy_loss | anchor_kl | approx_kl | early_stop |
|---:|---:|---:|---:|---:|---:|:--:|
| 1 | 50,000 | 703.40 | 2.482 | 1.746 | 1.278 | * |
| 2 | 100,000 | 34.68 | 0.053 | 4.436 | 1.438 | * |
| 3 | 150,000 | 5.46 | 0.006 | 4.635 | 0.005 |  |
| 5 | 250,000 | 4.50 | 0.015 | 4.478 | 0.022 |  |
| 10 | 500,000 | 4.89 | 0.006 | 3.960 | 0.009 |  |
| 20 | 1,000,000 | 5.20 | 0.015 | 3.049 | 0.022 |  |
| 30 | 1,500,000 | 1.62 | 0.005 | 1.637 | 0.011 |  |
| 40 | 2,000,000 | 321.85 | 0.048 | 1.518 | 0.310 | * |
| 50 | 2,500,000 | 9.09 | 0.009 | 1.222 | 0.037 | * |
| 60 | 3,000,000 | 75.70 | 0.004 | 0.918 | 0.035 | * |
| 70 | 3,500,000 | 493.08 | 0.021 | 1.830 | 0.330 | * |
| 80 | 4,000,000 | 356.45 | 0.039 | 1.519 | 0.191 | * |
| 90 | 4,500,000 | 210.45 | 0.043 | 1.020 | 0.150 | * |
| 100 | 5,000,000 | 1372.40 | 0.019 | 1.440 | 0.141 | * |

- value_loss[1]  = 703.40  (cold start)
- value_loss[5]  = 4.50
- value_loss[10] = 4.89
- value_loss[50] = 9.09
- value_loss[100]= 1372.40  (FINAL)
- value_loss min = 1.20 @ iter 42
- value_loss max = 1372.40 @ iter 100

## Anchor-KL drift

- anchor_kl[1]   = 1.746
- anchor_kl[5]   = 4.478
- anchor_kl[10]  = 3.960
- anchor_kl[50]  = 1.222
- anchor_kl[100] = 1.440  (FINAL)
- anchor_kl max  = 4.689 @ iter 4

## Action-mix evolution

Anchor (BC) reference mix is ~fold 60% / cc 22% / raise 18%. Watch for cc collapse to 0.

| iter | hands | mix |
|---:|---:|:--|
| 1 | 50,000 | fold=61.0% cc=16.4% r-s=17.0% r-m=5.5% r-big=0.2% |
| 2 | 100,000 | fold=69.9% r-s=29.7% r-m=0.2% |
| 3 | 150,000 | fold=67.5% r-s=32.5% |
| 5 | 250,000 | fold=67.4% r-s=31.4% r-m=1.3% |
| 10 | 500,000 | fold=67.6% r-s=28.3% r-m=4.2% |
| 20 | 1,000,000 | fold=68.3% cc=0.9% r-s=23.1% r-m=7.7% |
| 30 | 1,500,000 | fold=72.2% cc=19.4% r-s=3.6% r-m=4.8% |
| 40 | 2,000,000 | fold=63.6% cc=31.1% r-s=1.6% r-m=3.8% |
| 50 | 2,500,000 | fold=63.1% cc=27.8% r-s=3.4% r-m=5.1% r-big=0.6% |
| 60 | 3,000,000 | fold=61.8% cc=26.1% r-s=3.4% r-m=6.1% r-big=2.7% |
| 70 | 3,500,000 | fold=64.3% cc=29.6% r-s=1.7% r-m=3.5% r-big=0.8% |
| 80 | 4,000,000 | fold=55.4% cc=26.0% r-s=0.8% r-m=16.7% r-big=1.0% |
| 90 | 4,500,000 | fold=52.5% cc=36.7% r-s=3.3% r-m=5.4% r-big=2.0% |
| 100 | 5,000,000 | fold=55.4% cc=29.3% r-s=2.2% r-m=10.2% r-big=2.9% |

### CC (check/call) collapse / recovery
- CC < 1% first seen at iter 2 (hands 100,000)
- CC > 5% recovered at iter 22 (hands 1,100,000)
- CC final = 29.3%

### Fold dominance
- fold range: 50.6% .. 72.7%
- never crossed fold > 92% hard-stop threshold

## Policy entropy
- entropy[1]   = 0.0744
- entropy[10]  = 0.0238
- entropy[50]  = 0.1159
- entropy[100] = 0.1441
- entropy min  = 0.0043 @ iter 4

## Advantage normalization sanity
A healthy training run has |adv.mean| ~ 0 and adv.std ~ 1 after normalize. Cold value head means raw adv.std is huge.

| iter | adv.mean | adv.std | p5 | p95 |
|---:|---:|---:|---:|---:|
| 1 | 1.04 | 27.84 | -14.44 | 55.93 |
| 2 | -2.34 | 8.50 | -16.81 | 4.68 |
| 3 | 0.74 | 2.71 | -3.37 | 6.60 |
| 5 | -0.03 | 2.15 | -3.94 | 4.31 |
| 10 | 0.38 | 2.23 | -3.51 | 4.57 |
| 20 | -0.10 | 2.30 | -4.15 | 3.87 |
| 30 | 0.04 | 1.30 | -0.71 | 1.59 |
| 40 | 1.84 | 19.80 | -1.69 | 3.14 |
| 50 | -0.04 | 3.05 | -0.99 | 1.25 |
| 60 | 0.06 | 8.71 | -1.73 | 1.77 |
| 70 | -2.49 | 23.21 | -7.89 | 1.44 |
| 80 | -1.44 | 20.61 | -6.44 | 3.15 |
| 90 | -0.95 | 14.98 | -7.13 | 3.30 |
| 100 | -1.86 | 37.58 | -12.27 | 13.94 |

## PPO epoch early-stopping
- early-stopped iterations: 64 / 100
- ppo_epochs configured: 2 → expect ~50% early-stop is normal; >70% suggests target_kl=0.03 too tight

## Diagnosis

1. **Cold-start value head**: iter-1 value_loss = 703.4, ~1x the final value. 
   Initial adv.std = 27.8 (vs healthy ~10-20) → garbage critic produced garbage advantages.
2. **Anchor-KL spike**: jumped from 1.75 to 4.69 in iters 2-5 → policy moved far from anchor before critic could stabilize.
3. **CC collapse**: check/call dropped to ~0% by iter 2, recovered → policy degraded due to bad advantage signal.
4. **Recovery via anchor KL**: final anchor_kl = 1.44, still high vs target 0.03 — the anchor pull kept the policy from total divergence but did not restore CC mass.

## Recommended next step

**Value-head warmup** before policy updates:
- Freeze policy head & shared trunk.
- Collect K=200k-500k hands of pure rollout from anchor.
- Train value head only with MSE on bootstrapped returns until value_loss < 50.
- Then unfreeze policy and resume PPO with reset optimizer state.
- Expected outcome: iter-1 value_loss < 100 (vs 703), iter-1 anchor_kl < 0.5 (vs 1.75).