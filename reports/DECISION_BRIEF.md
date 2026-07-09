# Beat-Slumbot Campaign — Decision Brief (2026-06-07)

One-page synthesis for the funding decision. Detail lives in `campaign_state.md` + the per-cycle reports.

## Where we are
- **Best agent: BC anchor `models/bc/v3_anchor_5M_d1_light/best.pt` = -44.74 bb/100 vs Slumbot (unbeaten).**
- Goal: bb/100 > 0 with 95% CI lower bound > 0 over 100k+ hands. Gap to close: ~45 bb/100.
- **All cheap/in-budget paths are exhausted.** Breaking -45 now requires ONE gated investment.

## The evidence chain (cycles 5-12, all zero-compute)
1. **PPO-from-BC is dead.** RL-1 -57, warm-critic -57, Phase-B full-dist -74, per-class-KL -60 — none beat
   BC -45. Mechanism: per-decision discipline lost; critic diverges on mixed-pool returns. (cycles 4-5)
2. **BC is teacher-saturated.** BC reproduces its teacher (heuristic_v3) at 98.6% acc / L1-TV 0.009.
   So the -45 ceiling is the *teacher's* ceiling — "re-BC on the same teacher" cannot help. (cycle 7)
3. **The leak is OOP postflop at 200bb depth.** Loss localizes to BB/out-of-position (-68 bb/100, 66% of
   loss) and early streets; turn/river play is already +EV. (cycle 9)
4. **The cheap preflop fix is falsified.** heuristic_v2 *did* widen BB defense (flat-call) → -59, WORSE
   than v3's polarized -51.5. BB's 72% fold is largely correct given weak OOP postflop realization. The
   binding constraint is OOP postflop equity realization, not the preflop range. (cycle 10)
5. **It's a structural ASSET-REGIME gap.** Teacher/Slumbot are 200bb-deep; every CFR/VN asset we own is
   ≤100bb (vnet-v10 = 50bb). CFR can validly relabel only ~2% of (deep) decisions. The gap hits BOTH the
   offline-distill path AND the real-time resolver (which caps at 100bb scenarios + ≤100bb value nets).
   (cycles 8, 11, 12)

**Conclusion: the only way to move -45 is to build 200bb-native CFR/VN assets, then use them (re-BC teacher
and/or real-time resolver). There is no cheaper route.**

## The decision — pick ONE funded path (all gated)
| # | path | what it buys | cost / gate |
|---|---|---|---|
| **1 (rec)** | **Build 200bb SRP CFR/VN assets** (offline solve) | correct OOP-postflop strategy at the right depth; unlocks BOTH the re-BC teacher AND the realtime resolver | ~1TB raw (only 814GB free → needs `--samples-per-bucket 1` streaming or cleanup); 32GB fork solver, low parallelism; **multi-day to ~2 weeks**; +EV export if also used as an E1 critic |
| 2 | **New RL idea at depth** | could learn OOP realization directly | needs a genuinely new algorithm (PPO-from-BC dead); likely >5M-hand run; design risk |
| 3 | **Accept -45 / stop** | keep BC anchor as the deliverable | no further spend; goal unmet |

## Recommendation
Fund **path-1 (200bb asset build)** — it is the common prerequisite for every solver-based fix and is the
highest-leverage, lowest-design-risk option. Smallest viable scope: **SRP-only, 200bb, policy export** (SRP
covers 97.5% of decisions; policy format is ready, no EV needed for the teacher route). First step on
approval: add `PIPELINE_SRP_V3_200BB` config + ~10-line solve-script handling, free ~1TB disk (or enable
streaming), launch a small N-board smoke to validate memory/throughput BEFORE the full 1,911-board run.

## What I need from you
A go/no-go on path-1 (and confirmation on disk: free ~1TB, or approve streaming-only). Until then the
analysis phase is **closed** (nothing left to learn cheaply) and I'm on a steady hold — no compute, BC
anchor preserved, all records current. If you'd rather not get idle pings, I can pause the recurring cron.
