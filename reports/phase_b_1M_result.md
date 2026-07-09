# Phase B 1M Smoke — Result (2026-06-06)

Autonomous supervisor cycle 4. Option A executed: PPO from BC anchor + gentlest warmup.

## Config
- anchor: `models/bc/v3_anchor_5M_d1_light/best.pt` (BC d1-light, Slumbot -44.74)
- warmup: `models/ppo/warm_critic_kl30_60ep_smoke/warmup.pt` (vloss 158->27, trunk drift 0.12)
- opponent mix: self .40 / heuristic_v3 .30 / scripted_aggro .15 / fold .15 (NO proxy)
- 1M hands, 50k/iter (20 iters), anchor_kl_coef 0.05 (data-driven decay, never triggered <2M), GN norm
- runtime 451s (7.5 min, ~2200 h/s) — trainer is FAST (earlier "8h" estimate was wrong)

## Training trajectory (HEALTHY-looking)
- mix locked near BC the whole run: F~62-72 / CC~21-32 / R~6-10 / jam~0. CC NEVER collapsed (vs RL-1 ->0).
- akl steady 0.9-1.8 (gentler than warm-1.5M's 1.2-1.4 peak). No explosion, no aggressive-basin.
- vloss noisy (34-1100) but ended low (34). Final mix F66/CC27/R6.5/jam0.4.

## Slumbot bench (8 sessions x 1000 hands, ~800/sess at write time)
| session | bb/100 @800 |
|---|---|
| 1 | -11.3 (high-variance outlier) |
| 2 | -75.6 |
| 3 | -84.3 |
| 4 | -72.6 |
| 5 | -98.6 |
| 6 | -84.8 |
| 7 | -95.6 |
| 8 | -59.8 |
| **mean** | **~ -73** (rough, CI wide; 7/8 sessions -60 to -99) |

## Verdict: REGRESSION — Option A axis is EXHAUSTED
- BC anchor: -45. Phase B 1M: ~-73. Warm-1.5M: -57. V4-extension family: -65 to -73.
- **PPO continuation from BC degrades to the V4-extension band regardless of warmup gentleness.**
- Mechanism: aggregate mix stays BC-shaped, but per-decision policy drifts (CC 22%->27% = more
  flat-calls -> showdown losses, the exact -36BB trap from path_b terminal analysis). Full-dist
  anchor-KL at 0.05 preserves SHAPE but not per-hand DISCIPLINE. Same finding as warm-1.5M report.

## Implication for campaign
The entire "gentle-PPO-finetune-from-BC anchor" family (RL-1, warm-critic 500k/1.5M, Phase B 1M)
converges to -57 to -90 vs Slumbot. None beats the BC anchor's -45. **More tweaks on this axis
will not break the ceiling.** Two genuinely-untried levers remain:
  (B) per-action / per-class KL that pins the fold/call/raise CLASS distribution to BC while
      allowing within-class card-dependent freedom — directly targets the CC-drift mechanism.
  (E) abandon PPO-from-BC; the structural ceiling may need a different algorithm (e.g. CFR-guided
      value target, or distillation of a stronger teacher), not RL continuation.

Recommend B as the last RL-axis experiment before declaring PPO-from-BC dead and pivoting to E.
</content>
