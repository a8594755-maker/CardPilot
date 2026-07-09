# CardPilot Project Status — 2026-05-08 (updated)

Comprehensive record of all work, models, and results.

---

## 1. Project Overview

**Goal:** Build a competitive GTO poker AI for coaching / bot deployment, approaching GTO Wizard AI quality on consumer hardware (RTX 4070, 32 cores, 128GB RAM).

**Architecture:**
- Monorepo (pnpm workspaces): `apps/` + `packages/`
- Runtime: Node.js 24, TypeScript (tsx), Python 3.12 (for ML training)
- Game: Heads-up No-Limit Texas Hold'em (HUNL)

**Two parallel tracks:**
1. **CFR pipeline** (tabular) → trained value networks (V7→V9.1→V10)
2. **AlphaHoldem** (end-to-end RL) → direct policy network, bypasses CFR

---

## 2. CFR Pipeline (完成的部分)

### V2 Pipelines (completed earlier)
All 1,911 isomorphic flops × 200K iter × 100 buckets:
- `pipeline_v2_hu_srp_50bb/` — SRP 50bb, 2 bet sizes [0.33, 0.75]
- `pipeline_v2_hu_srp_100bb/` — SRP 100bb
- `pipeline_v2_hu_3bet_50bb/` — 3-bet 50bb
- `pipeline_v2_hu_3bet_100bb/` — 3-bet 100bb

**Raw CFR data: DELETED** (900GB+) — training data already presampled.

### V3 Pipeline SRP 50bb (Completed 2026-04-01)
- Config: `pipeline_srp_v3` — **3 bet sizes** [0.33, 0.67, 1.0]/[0.50, 0.75, 1.25]/[0.50, 1.0, 1.50]
- 1,911 flops × 200K iter × 50 buckets
- Training data: 889M raw samples → presampled to **25.3M train + 2.8M val**
- **Raw CFR data: DELETED** (~730GB)

### V3 Other Scenarios (abandoned)
- `pipeline_3bet_v3` — started ~60 flops, killed when pivoted to AlphaHoldem
- `pipeline_srp_v3_100bb` / `pipeline_3bet_v3_100bb` — never started

---

## 3. Value Networks (CFR track)

| Model | Data | KL | Top-1 | Sizing | Flop KL | Turn KL | River KL |
|-------|------|-----|-------|--------|---------|---------|----------|
| V7 | V2 unified 7.95M | 0.340 | 60.8% | 77.7% | 0.227 | 0.275 | 0.364 |
| V8 | V2 unified (embedding) | 0.338 | 59.7% | 74.2% | 0.250 | 0.291 | 0.352 |
| V9.1 | V2 3/25/72 balance 28.8M | 0.336 | 61.4% | 78.1% | 0.208 | 0.272 | 0.361 |
| **V10** ⭐ | V3 3/25/72 balance 25.3M | **0.307** | 58.0% | 67.9% | **0.185** | **0.258** | **0.328** |

**V10 deployed to:** bot-client main, realtime-resolver (4 scenarios), game-server, arena.

---

## 4. Real-Time Resolver

Module: [apps/bot-client/src/realtime-resolver.ts](apps/bot-client/src/realtime-resolver.ts)

### WASM CFR
- **11.2x speedup** vs TS
- Flop 5000 iter, Turn 3000, River 1500

### Cold-start WASM convergence benchmark
```
200 iter:  165ms, strategy diff 0.208
500 iter:  379ms, diff 0.141
5000 iter: 3444ms, diff 0.032
```

### VNet Warm-Start (FAILED)
Bucket abstraction blocks per-combo NN; warm-start actively worse than cold.

---

## 5. AlphaHoldem RL — V3 (1B hands, 50bb training)

### Architecture (Pseudo-Siamese)
```
card_info:   (B, 6, 4, 13)
action_info: (B, 25, 4, 5)
extra_info:  (B, 2)

Card branch:  Conv2D(48) → ResBlock(96, s2) → ResBlock(96)
              → ResBlock(192, s2) → ResBlock(192) → flatten
Action branch: same structure
Extra FC: Linear(2→32)
Trunk: Linear(fused → 2048 → 1024 → 512 → 256)
Heads: policy(9) + value(1)

Params: 8.15M (matches paper's 8.6M)
```

Action space (9 discrete):
- 0: fold | 1: check/call | 2-7: raise to {33,50,67,75,100,150}% pot | 8: all-in

### V3 Training (Standard PPO, 50bb)
- 1,000,007,692 hands total
- Workers: 28 (persistent MP, shared memory)
- Throughput: ~1,000-1,400 hands/sec
- VLoss trajectory: 640 → 199 (stuck at 199 — NO Trinal-Clip)

### V3 Evaluation Results (at 50bb)

**vs Baselines (10K hands each):**
| Opponent | mbb/hand | Win rate |
|----------|----------|----------|
| Random | **+1,487** ±301 | 38.2% |
| Call-station | **+3,303** ±392 | 31.7% |
| Aggressive | **+2,793** ±432 | 13.3% |

**Head-to-Head vs V10 (1000 hands, 50bb):**
- AlphaHoldem V3: **+2,301 mbb/hand** ±1,206 ✓
- V10 loses decisively

**vs Slumbot (2000 hands, 200bb — WRONG STACK DEPTH):**
- AlphaHoldem V3: **-2,784 mbb/hand** ±2,015 (loses)
- V10: **-2,351 mbb/hand** ±1,564 (also loses)
- Both bots crushed by Slumbot due to 50bb vs 200bb mismatch

---

## 6. Paper Gap Analysis (Critical Self-Assessment)

User identified we skipped key paper innovations:

### What we missed in V3 (confirmed)
1. **Trinal-Clip PPO** — The paper's main contribution (not implemented in V3)
2. **K-Best opponent pool** — Only naive self-play (not implemented)
3. **γ=0.999** — Used γ=1.0 instead
4. **200bb stack depth** — Trained at 50bb
5. **Reward signal validation** — Not audited

### Paper Specs (from deep research of AAAI 2022 paper pp. 4692-4693)

**Trinal-Clip PPO — Policy Loss (Equation 3):**
```
L^tcp(θ) = E[ clip(clip(r_t, 1-ε, 1+ε), δ₁) · Â_t ]

where:
  ε  = 0.2 (standard PPO clip)
  δ₁ = 3.0 (outer policy bound, only when adv < 0)
```

**Trinal-Clip PPO — Value Loss (Equation 4):**
```
L^tcv(θ) = E[ (clip(R_t^γ, -δ₂, +δ₃) - V_θ(s_t))² ]

where:
  δ₂ = hero's chips committed in trajectory  (DYNAMIC)
  δ₃ = villain's chips committed in trajectory  (DYNAMIC)
```

**Paper Performance (ELO in ablation Table 2):**
- Original PPO: ELO 1257
- Dual-Clip PPO: ELO 1308
- **Trinal-Clip PPO: ELO 1597** (+340 vs original)

**K-Best Self-Play (paper vague on details):**
- Maintain pool of snapshots by ELO
- Select top K
- K value NOT disclosed
- Snapshot frequency NOT disclosed

---

## 7. AlphaHoldem V4 (IN PROGRESS) — Full Paper Replication

Started: 2026-04-19
File: [scripts/alpha_holdem/train_mp3.py](scripts/alpha_holdem/train_mp3.py)

### Fixes from V3

| Issue | V3 | V4 |
|-------|-----|------|
| Stack depth | 50bb | **200bb** (matches Slumbot) |
| Policy loss | Standard PPO | **Trinal-Clip (Eq. 3)** |
| Value loss | MSE (unclipped) | **Trinal-Clip (Eq. 4)** |
| Gamma | 1.0 | **0.999** |
| Opponent pool | None (naive) | **K-best (K=5)** |
| Entropy | 0.1 + adaptive | 0.05 + safety boost when <0.1 |

### Implementation Specs

**Environment changes ([scripts/alpha_holdem/environment.py](scripts/alpha_holdem/environment.py)):**
- Added `chips_committed(player)` method
- Added `GameConfig.full_200bb()` to [scripts/deep_cfr/game_state.py](scripts/deep_cfr/game_state.py)
- Reset to 200bb on `starting_stack > 100`

**Worker changes ([scripts/alpha_holdem/train_mp3.py](scripts/alpha_holdem/train_mp3.py)):**
- Tracks hero_chips & villain_chips at hand end
- Emits 11-tuple transitions (added δ₂, δ₃)
- Shared memory `opp_id` slot for K-best routing

**Trainer changes:**
- `trinal_clip_ppo_update()` function
- Per-sample value clipping with trajectory-specific bounds
- `KBestPool` class with ELO-based ranking

### Paper Alignment Audit

**✅ Matches paper's disclosed values exactly:**
- Architecture (pseudo-Siamese, ResBlocks)
- Adam optimizer, lr=3e-4
- Batch size 16384
- GAE λ=0.95
- γ=0.999, ε=0.2, δ₁=3.0
- Dynamic δ₂/δ₃ from committed chips
- 200bb HUNL

**⚠️ Guessed (paper doesn't disclose):**
- K value in K-best = 5
- Snapshot frequency = every 200 iter
- ELO K-factor = 32
- Opponent sampling: 80% pool / 20% self
- Entropy coefficient = 0.05 (paper uses entropy regularization but value not published)
- PPO epochs per update = 4 (standard; paper doesn't specify)
- Mini-batch size = 1024 (paper's 16384 is *collection* batch)

**❌ Our additions (beyond paper):**
- Adaptive entropy boost when entropy < 0.1 (×5)
- Epsilon-greedy 0.15 with decay in last 20%

### V4 Training Progress (as of 2026-04-27 — paused at 70%)

**Current state:** 703M / 1B hands (70.3%)

**Metrics across milestones:**
| Milestone | Hands | VLoss | Entropy | Note |
|-----------|-------|-------|---------|------|
| Init | 0 | 5,910 | 1.28 | Started |
| Crash recovery | 6.5M | 1,500 | 0.015 → 1.18 | Adaptive boost saved it |
| 80M | 80M | 1,200 | 1.18 | Stable |
| 200M | 200M | 700 | 1.20 | Trinal-Clip working |
| 350M | 350M | 422 | 1.13 | New low |
| 500M | 500M | 625 | 1.13 | Snapshot for eval |
| 700M | 703M | 346-3,036 | 1.09 | Variance up, vloss bouncing |

**Entropy recovery story:**
- First run: entropy crashed to 0.015 by iter 401
- Kill + restart with entropy_coef=0.05 + adaptive boost
- Entropy recovered to 1.15 within ~50 iters, stable since

**Speed degradation:** 1,500 h/s early → 500-1,000 h/s late
- Hands getting longer as model develops postflop play
- More raise/call decisions per hand

**ETA from 70%:** ~3-7 more days to 1B hands

### V4 Slumbot Benchmarks (full training journey)

| Checkpoint | Config | bb/100 | mbb/hand | CI | Sample | Note |
|-----------|--------|--------|----------|----|------|------|
| V4 @ 150M | K=5, floor=0.5 | -466.5 | -4,665 | ±3,397 | 500 | too noisy |
| V4 @ 500M | K=5, floor=0.5 | -130.7 | -1,307 | ±1,043 | 2K | True baseline |
| V4 @ 600M | K=5, floor=0.5 | -128.6 | -1,286 | ±1,016 | 2K | Plateau detected |
| V4 @ 660M | **K=3** (regression branch) | -172.7 | -1,727 | ±693 | 2K | K=3 caused regression |
| V4 @ 700M | K=5, **floor=0.3** | -112.9 | -1,129 | ±1,126 | 2K | Floor=0.3 first effect |
| V4 @ 800M | K=5, floor=0.3 | **-72.1** | **-721** | ±491 | 2K | Plateau breakthrough |
| V4 @ 900M | K=5, floor=0.3 | **-69.5** | **-695** | ±759 | 2K | Best 2K result |
| V4 @ 987M (2K) | K=5, floor=0.3 | -9.0 | -90 | ±706 | 2K | misleading point estimate (wide CI) |
| **V4 @ 987M (20K)** | K=5, floor=0.3 | **-49.7** | **-497** | **±219** | **20.4K** | **REAL benchmark** ⭐ |
| **V4 @ 1B (frozen)** | — | — | — | — | — | source for V5 resume |
| **Paper @ 2.7B** | (reference) | **+11.1** | **+111** | — | — | beat Slumbot |

**Improvement journey (bb/100):**
- V3 (50bb): -278.4
- V4 @ 500M: -130.7 (+148 bb/100 vs V3)
- V4 @ 800M: -72.1 (+59 bb/100 vs 500M, after floor=0.3 fix)
- V4 @ 900M: -69.5 (+3 bb/100 vs 800M, slowing)
- V4 @ 987M (20K): **-49.7 ± 21.9** ← gap to paper +11.1 = ~61 bb/100
- Note: 2K-hand benchmarks have CI ±60-80 bb/100 — only useful for >100 bb/100 regressions

**Critical findings:**
1. **K=3 actively hurt** — caused regression from -130.7 → -172.7 bb/100
2. **floor=0.5 caused plateau** at -130 bb/100
3. **floor=0.3 broke through** plateau (-130 → -72 bb/100, 58 bb/100 improvement)
4. **CI shrinking** as training progresses (more consistent strategy)

### V4 Final Prediction (1B)

**Updated based on 900M result (-69.5 bb/100):**

Trajectory shows plateau forming around -70 bb/100:
- 700→800: +40 bb/100 improvement (big)
- 800→900: +3 bb/100 improvement (slowing)
- 900→1B: estimated +0~5 bb/100

Most likely outcome at 1B: **-65 to -70 bb/100**

Gap to paper (+11.1 bb/100): ~80 bb/100 (~800 mbb/hand)

This represents:
- V3 → V4 improvement: +209 bb/100 (huge)
- Paper replication: ~85% achieved
- Remaining gap: due to compute (1B vs 2.7B hands)

### Speedup Options (Considered, Not Implemented)

Investigated mid-training speedup:
- `torch.compile()`: 1.3-1.5x lossless, Windows risky
- FP16 autocast: 2x, slight precision loss
- Bigger inference batches: 1.5-2x, architecture risk
- Cython game engine: 5-10x, 3-5 days work

**Decision:** Don't change inference mid-training. Risk of corrupting 70% trained checkpoint outweighs ~3 day savings.

### V4 Predicted Outcomes

| Scenario | Probability | vs Slumbot | Meaning |
|----------|-------------|------------|---------|
| Optimistic | 20% | +50 to +100 mbb | Matches paper (+111) |
| **Middle** | **50%** | **-50 to +50 mbb** | Near break-even |
| Pessimistic | 30% | -300 to -100 mbb | Improvement but not enough |

**Remaining gaps to paper:**
- Compute: 28 cores vs 89 cores (3x less)
- Total hands: 1B vs 2.7B (2.7x less)
- K-best details guessed
- Possible reward signal edge cases

---

## 8. Slumbot Benchmark Integration

Script: [scripts/alpha_holdem/play_slumbot.py](scripts/alpha_holdem/play_slumbot.py) (AlphaHoldem)
Script: [scripts/alpha_holdem/play_slumbot_v10.py](scripts/alpha_holdem/play_slumbot_v10.py) (V10)

### Slumbot API Protocol
- POST `https://slumbot.com/slumbot/api/{new_hand,act}`
- JSON with `token` and `incr` (action string)
- 200bb HUNL, SB=50 BB=100 Stack=20000 chips
- Action format: `"b200c/kb400"` (k=check, c=call, f=fold, bN=bet to N chips)
- `client_pos`: 0=BB, 1=SB

### Key bug fixes
- All-in bet must be capped at remaining stack on current street (NOT total stack)
- If `state['pos'] != client_pos`: fold as safety (don't silently fail)

---

## 9. Other Infrastructure

### SD-CFR (Neural CFR) — PARKED
- Leduc validated: 73.3 mbb/g
- NLHE: too slow on single GPU (est. 4700+ iter to converge)
- Details: [sdcfr_hunl_results.md](sdcfr_hunl_results.md)

### GPU Training Pipeline
- [scripts/train_gpu.py](scripts/train_gpu.py) (467 lines)
- RTX 4070, ~6 min/epoch, 50 epochs ≈ 5h per model

---

## 10. Current Models & Disk State

### Production
- **V10** (`vnet-v10-v3data.json`) — CFR value network, deployed
- **AlphaHoldem V3** (`alpha_holdem_v3.pt`) — Strong at 50bb, weak at 200bb

### Training
- **AlphaHoldem V4** (`alpha_holdem_v4.pt`) — In progress, 200bb + Trinal-Clip + K-best

### Disk
- Training data preserved: `unified_v91/` (9.7GB), `v3_srp_50bb_sampled/` (10GB)
- Raw CFR data all deleted (~1TB freed)

---

## 11. Key Technical Lessons

### AlphaHoldem pitfalls
1. **Entropy collapse without boost** — PPO vanilla crashes entropy; paper doesn't mention but they likely have some mechanism
2. **Value loss explodes at 200bb** — without Trinal-Clip, vloss goes unstable
3. **Stack depth matters enormously** — 50bb strategies don't transfer to 200bb
4. **Windows multiprocessing** — per-iter spawn is 100x slower than persistent workers

### What I got wrong
1. Skipped Trinal-Clip PPO (paper's main contribution) on first read
2. Used naive self-play instead of K-best pool
3. Trained at 50bb when benchmarking at 200bb
4. Declared V3 "failed" vs Slumbot without testing V10 for comparison
5. γ=1.0 (infinite horizon) instead of paper's γ=0.999

---

## 12. V5 Optimization Track (2026-05-07 onwards)

### V4 Frozen as Baseline
- **`models/alpha_holdem_v4_final.pt`** — 1B-hand checkpoint, source for V5 resume
- **`models/alpha_holdem_v4_final_1000M.pt`** — tagged copy for audit trail
- Trainer `train_mp3.py` preserved untouched; rollback path = `train_mp3.py + alpha_holdem_v4_final.pt`

### V5.0 Trainer (`scripts/alpha_holdem/train_v5.py`)

V5 plan philosophy: optimize for **EIR (Effective Information Rate)**, not just h/s. Full roadmap in `memory/v5_optimization_plan.md`.

V5.0 changes (forked from train_mp3.py):
1. `--epsilon 0` default (no PPO ratio corruption from epsilon-greedy)
2. **Both-player transition collection** in self-play (~2× trans/hand)
3. Action table cache (eliminate duplicate `state.legal_actions()`)
4. Flat obs view in inference (no list→array→tensor copy)
5. **Latest-K** opponent pool (FIFO) replacing K-best ELO (PSRO is V5.3)
6. Split shm: `assigned_opp_id` (main writes) vs `request_model_id` (worker writes) — fixes V4 race
7. New metrics: `tdec/s`, `inf_bs`, separate collect_time / ppo_time

### V5.0 Launch Pipeline

**`scripts/alpha_holdem/freeze_v4.ps1`** — Pick rolling/eval/live ckpt with hands ≥ MinHandsM, copy to canonical + tagged paths. Used standalone or by watcher.

**`scripts/alpha_holdem/auto_launch_v5.ps1`** — 5-phase watcher:
1. Wait for `hands ≥ TargetHands` in `alpha_holdem_v4_train.log`
2. Wait for `models/v5_ready.flag` (manual benchmark gate)
3. Stop V4 trainer (if `-KillV4`)
4. Run freeze_v4.ps1 (defaults to MinHandsM=1000)
5. Launch V5: `python train_v5.py --resume alpha_holdem_v4_final.pt --out alpha_holdem_v5.pt`

Known issue: hidden powershell process died after invoking freeze step in one run; freeze had to be run manually. Cause unclear; likely stdout handling. Phase 1-3 worked correctly.

### V5.0 In-Flight Status

Started 2026-05-07 17:00 EDT, resumed from V4 final.

**Training health: GOOD.**
- vloss: spike 1700 at startup → recovered to 170-300 (V4-comparable)
- entropy: stable at 0.55-0.60 (well above 0.3 floor)
- rew100: settled near 0 (pool equilibrium reached)
- ploss: tiny 0.001-0.01 (converged update sizes)

**Throughput: REGRESSED vs V4.**

Clean-window measurement (no GPU contention from gaming):
| Metric | V4 end | V5.0 clean | Ratio |
|---|---|---|---|
| h/s (raw, V5 inflated) | 1300 | 660 | 51% |
| h/s (real, V5 deflated by 1.2) | 1300 | 550 | 42% |
| trans/sec | 1100 | 970 | 88% |
| trans/real-hand | 1.9 | 2.3 | 121% |

V5.0 succeeded at producing more transitions per hand (the math worked), but worker-side cost (dual `hand_buffers[player].append(...)` + `last_actor` tracking + 2× pipe sends in self-play) outweighed the gain. Net: V5 produces fewer real hands/sec than V4.

**Verdict so far:**
- Speed dimension: **failed** — V5.0 is slower than V4
- Strategy dimension: **TBD** — needs +50M hands of V5 + 20K Slumbot benchmark

### Decision Gate (after +50M V5 hands)

If V5 vs Slumbot ≤ -30 bb/100 (clearly better than V4's -49.7), keep V5 even with speed regression (sample efficiency wins).
If V5 vs Slumbot ≈ -49.7 or worse, **rollback to V4**, skip V5.0, jump to V5.1 (FastHUNLState + shm ring buffer — moves data accumulation off worker, the actual fix).

### V5.1+ Roadmap (in `v5_optimization_plan.md`)

- **V5.1** (3-5 days): FastHUNLState (mutable, no clone), shm ring buffer for transitions, AMP bf16, inference micro-batching → target 2-5× raw h/s
- **V5.2** (3-5 days): All-in/multi-runout EV (HIGHEST PRIORITY for variance), suit permutation aug (24× free data), seat-swap paired baseline, pot-normalized value head, auxiliary heads
- **V5.3** (5-7 days): Opponent mixer network + PSRO meta-strategy
- **V5.4** (multi-week): Async actor-learner, distributional value, local CFR teacher, public-state fanout

Top 3 by impact: Opponent Mixer (V5.3), All-in EV (V5.2), Public-State Fanout (V5.4).

---

## 13. Next Steps

### Immediate
- [ ] Run V5.0 to ~1.05B hands (+50M from start) — ETA ~3-5 days at current 660 h/s
- [ ] Benchmark V5 @ 1.05B vs Slumbot (20K hands, 12 parallel sessions)
- [ ] Compare to V4 @ 987M baseline (-49.7 bb/100 ± 21.9)
- [ ] If V5 < V4: rollback, skip V5.0, build V5.1

### If V5.0 wins (Slumbot ≤ -30 bb/100)
- [ ] Continue V5.0 to 1.5B
- [ ] Layer V5.1 on top of V5.0

### If V5.0 loses
- [ ] Rollback: `python train_mp3.py --resume alpha_holdem_v4_final.pt --total-hands 2000000000`
- [ ] Implement V5.1 (FastHUNLState + ring buffer) on top of train_mp3.py
- [ ] V5.0's "both-player collect" + "latest-K" become candidate features for V5.1+ (after speed is fixed)

### If V4 final continues to plateau
- [ ] Audit reward signal bit-by-bit vs paper
- [ ] Try snapshot every 50/100 iters
- [ ] Consider training longer (1.5B-2B hands)

---

## 13. Summary Stats

**Total training compute spent (cumulative):**
- V2 + V3 CFR pipelines: ~10 days of CFR solving
- V7-V10 value networks: ~30 hours GPU
- AlphaHoldem V3 (1B hands, 50bb): ~14 days
- AlphaHoldem V4 (200bb + Trinal-Clip + K-best): ~7 days so far @ 70%, ~3-7 more days to 1B

**Paper replication level:** ~90% faithful to Zhao et al. AAAI 2022 (with some K-best details guessed).

**Current best bot at 50bb:** AlphaHoldem V3 (beats V10 by 2.3 BB/hand)
**Current bot at 200bb:** None viable yet (V4 in progress)
**Production deployment:** V10 (CFR + resolver) still default

---

## 14. File References

### AlphaHoldem
- [scripts/alpha_holdem/network.py](scripts/alpha_holdem/network.py) — Pseudo-Siamese net, 8.15M params
- [scripts/alpha_holdem/environment.py](scripts/alpha_holdem/environment.py) — HUNL env with chip tracking
- [scripts/alpha_holdem/train_mp3.py](scripts/alpha_holdem/train_mp3.py) — **Current trainer (Trinal-Clip + K-best)**
- [scripts/alpha_holdem/train_mp2.py](scripts/alpha_holdem/train_mp2.py) — V3 trainer (deprecated)
- [scripts/alpha_holdem/evaluate.py](scripts/alpha_holdem/evaluate.py) — vs Random/CS/Aggressive
- [scripts/alpha_holdem/head_to_head.py](scripts/alpha_holdem/head_to_head.py) — vs V10
- [scripts/alpha_holdem/play_slumbot.py](scripts/alpha_holdem/play_slumbot.py) — vs Slumbot
- [scripts/alpha_holdem/play_slumbot_v10.py](scripts/alpha_holdem/play_slumbot_v10.py) — V10 vs Slumbot

### CFR / V10
- [packages/cfr-solver/src/scripts/solve-v3-parallel.ts](packages/cfr-solver/src/scripts/solve-v3-parallel.ts)
- [packages/cfr-solver/src/scripts/cfr-to-training-data.ts](packages/cfr-solver/src/scripts/cfr-to-training-data.ts)
- [scripts/train_gpu.py](scripts/train_gpu.py)
- [apps/bot-client/src/realtime-resolver.ts](apps/bot-client/src/realtime-resolver.ts)
