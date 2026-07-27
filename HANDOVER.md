# AlphaHoldem Replication — Training Journey Handover

**Date:** 2026-05-08 (updated)
**Project:** Reimplementing Zhao et al. AAAI 2022 "AlphaHoldem" on consumer hardware
**Hardware:** RTX 4070 (12GB) + 28-core CPU + 128GB RAM (Windows 11)
**Status:** V4 frozen at 1B hands, **20K-hand benchmark = -49.7 bb/100 ± 21.9**. V5.0 trainer launched; speed regression observed.

This handover packages the production training code, full memory/lessons, the chronological journey, and the in-flight V5.0 optimization attempt.

---

## TL;DR

We reimplemented AlphaHoldem from scratch in PyTorch and trained a 200bb HUNL poker bot on a single RTX 4070. After two failed attempts and one major plateau, V4 reached **-49.7 bb/100 ± 21.9 vs Slumbot at 987M hands** (20.4K-hand benchmark, 12 parallel sessions). Paper achieves +11.1 bb/100 at 2.7B hands — gap of ~61 bb/100.

> **Earlier 2K-hand quick-look quoted -9.0 bb/100 ± 70.6** — this was within the wide CI but ~40 bb/100 more optimistic than the 20K benchmark. Don't trust 2K-hand Slumbot numbers; CI is too wide.

V4 is now frozen at `models/alpha_holdem_v4_final.pt` (1B-hand checkpoint). V5.0 trainer (`train_v5.py`) was forked and launched as an EIR-focused optimization attempt; **early evidence is that V5.0 didn't deliver speedup**. See "V5.0 Attempt" section below.

Critical hyperparameters that took multiple iterations to find:
- **Trinal-Clip PPO** (Eq. 3 + 4 in paper) — required from the start; without it value loss explodes
- **K-best opponent pool K=5** — K=3 caused regression (initially thought K=3 better, was wrong)
- **entropy_floor=0.3** — 0.5 too conservative (plateau), 0.1 too late (collapse), 0.3 was sweet spot
- **gamma=0.999** — paper value, NOT 1.0
- **200bb stack depth** — match Slumbot benchmark; 50bb training transferred poorly

---

## Files in This Package

```
alphaholdem_handover/
├── HANDOVER.md                            ← this file (training journey + V5.0 attempt)
├── docs/
│   └── PROJECT_STATUS.md                  ← full project state, all benchmark results
├── memory/
│   ├── MEMORY.md                          ← project memory index
│   ├── alpha_holdem.md                    ← V3/V4 specs, formulas, models, V4 final benchmark
│   ├── feedback_alpha_holdem_lessons.md   ← painful mistakes & corrections (now incl. V5)
│   ├── feedback_throughput_eval.md        ← NEW: gaming contention measurement rule
│   └── v5_optimization_plan.md            ← NEW: full V5.0-V5.4 EIR roadmap
├── scripts/
│   ├── alpha_holdem/
│   │   ├── network.py                     ← 8.15M params pseudo-Siamese CNN
│   │   ├── environment.py                 ← HUNL env (50/100/200bb), chip tracking
│   │   ├── train_mp3.py                   ← V4 PRODUCTION trainer (Trinal-Clip + K-best)
│   │   ├── train_v5.py                    ← NEW: V5.0 trainer (epsilon=0, both-player collect, latest-K)
│   │   ├── freeze_v4.ps1                  ← NEW: pick rolling/eval/live ckpt → v4_final.pt
│   │   ├── auto_launch_v5.ps1             ← NEW: watcher: 1B + flag → kill V4 → freeze → launch V5
│   │   ├── evaluate.py                    ← vs Random/CallStation/Aggressive
│   │   ├── play_slumbot.py                ← Slumbot HTTP API client
│   │   └── safe_watcher.py                ← auto-snapshots on healthy checkpoints
│   └── deep_cfr/
│       ├── game_state.py                  ← HUNLGameState (used by environment.py)
│       └── hand_eval.py                   ← hand evaluator
└── eval_logs/
    ├── slumbot_v4_700M_floor03_2k.log     ← 2K-hand checkpoints (wide CI, indicative only)
    ├── slumbot_v4_800M_floor03_2k.log
    ├── slumbot_v4_900M_floor03_2k.log
    ├── slumbot_v4_987M_20k_summary.md     ← NEW: 20.4K-hand 12-session benchmark (real CI ±21.9)
    ├── v5_train_sample.md                 ← NEW: V5.0 startup + stable training log excerpt
    ├── v3_baseline_2k.log
    └── h2h_v3_vs_v10_1000.log
```

---

## Training Journey (Chronological)

### Phase 0: Pre-AlphaHoldem (CFR Track — context)
Before AlphaHoldem we had a CFR-based pipeline producing value networks (V7→V10):
- 1,911 isomorphic flops × 200K iter CFR+ = ~14 days compute
- V10 (current production CFR bot): KL=0.307 strategy distance, deployed
- Realized further CFR scaling needed ~10x more compute
- Decision: pivot to end-to-end RL (AlphaHoldem)

### Phase 1: Initial AlphaHoldem V1 (Failed — Naive PPO)
**Setup:** 478K params (smaller than paper), standard PPO, 50bb env, K=0 (no pool)
**Training:** 20M hands, ~3 days
**Bug:** Threading-only (Python GIL), 63 hands/sec — too slow
**Result vs Slumbot:** -2,784 mbb (also wrong stack depth)

### Phase 2: V2 Attempts (Multiple architecture tries)
- `train.py`: sequential single-process (slow)
- `train_fast.py`: threaded — GIL bottleneck, only 1 CPU core used
- `train_mp.py`: multiprocessing per-iter spawn — Windows process spawn was 100x slower
- **`train_mp2.py`**: persistent MP with shared memory — **WORKED**, ~1,000-1,400 h/s

### Phase 3: V3 (1B hands at 50bb — naive PPO, no Trinal-Clip)
**Setup:**
- 8.15M params (matches paper's 8.6M)
- Persistent MP architecture
- Standard PPO (NO Trinal-Clip), gamma=1.0
- Naive self-play (NO opponent pool)
- 50bb stack depth (default)

**Training:** 1B hands, 14 days

**Critical observation:** vloss got stuck at 199 (couldn't go lower). This is the symptom of missing Trinal-Clip — paper specifically says without it, "value loss explodes".

**Results:**
- vs Random: +1,487 mbb (+148.7 bb/100) — strong vs simple opponents
- vs Call-station: +3,303 mbb — strong
- vs Aggressive: +2,793 mbb — learned to trap
- vs V10 (50bb head-to-head): **+2,301 mbb** — beat our own CFR bot
- **vs Slumbot (200bb): -2,784 mbb (-278.4 bb/100)** — got crushed

**Key mistake I made:** Initially declared V3 "failed" based on Slumbot result. User correctly pointed out I never tested V10 vs Slumbot for comparison. When I did, V10 also lost (-2,351 mbb). The "failure" was actually:
1. Both V3 and V10 trained at 50bb, Slumbot is 200bb (4x stack mismatch)
2. V3 ACTUALLY won 50bb head-to-head vs V10 by 2.3 BB/hand

**Diagnosis from user:** 4 critical paper deviations:
1. No Trinal-Clip PPO ← biggest miss
2. No K-best opponent pool ← also missing
3. gamma=1.0 instead of 0.999
4. 50bb instead of 200bb

### Phase 4: V4 First Attempt (Failed — entropy collapse)
**Fixes applied** (from user's correct paper-reading critique):
- ✅ Trinal-Clip PPO implemented (Eq. 3 + Eq. 4 with dynamic δ₂/δ₃)
- ✅ K-best opponent pool (K=5)
- ✅ gamma=0.999
- ✅ 200bb HUNL
- entropy_floor=0.1 (default) with 5x boost

**Training:** Started fresh, reached 7M hands

**What happened:** Entropy crashed to 0.015 (essentially deterministic policy). Adaptive boost activates at floor=0.1, but by then the policy has already collapsed.

**Recovery:** Killed training, restarted with entropy_floor=0.5.

### Phase 5: V4 Continued (500M-700M — Plateau)
**Config:** K=5, floor=0.5, LR decay (3e-4 → 1e-4 in second half)

**Training progress:**
- 80M: vloss 1,200, ent 1.18
- 200M: vloss 700
- 350M: vloss 422
- 500M: vloss 625 (snapshot saved)

**500M Slumbot eval:** -1,307 mbb (-130.7 bb/100) — significant improvement vs V3's -278.4 bb/100

**Then disaster at 700M:**
- vloss exploded 102 → 11,000 (90x increase)
- entropy 1.15 → 0.10
- rew100 vs pool dropped to -1.82

**Cause:** Pool-overfitting cycling. Model learned exploits against current pool, then snapshots updated, model needed new exploits, oscillated wildly.

### Phase 6: K=3 Attempt (Backfired)
**Hypothesis:** K=5 too many opponents causing rock-paper-scissors. Try K=3.

**Setup:** Restart from 500M ckpt, K=3, floor=0.5

**Result at 660M:** **-1,727 mbb (-172.7 bb/100)** — actually WORSE than 500M baseline.

**Lesson:** K=3 over-specialized to 3 specific snapshots, lost generalization to Slumbot. K=5 was correct all along.

### Phase 7: V4 Production Config (Current Best)
**Setup:** Restart from 500M, K=5, **floor=0.3** (lowered from 0.5), LR decay

**Why floor=0.3:**
- floor=0.5: too conservative, model couldn't sharpen → plateau at -130 bb/100
- floor=0.1: collapse risk
- floor=0.3: allows exploitation while preventing collapse

**Results (this is the breakthrough):**

| Hands | Slumbot bb/100 | mbb/hand | CI | Sample | Note |
|-------|---------------:|---------:|----|-------:|------|
| 500M | -130.7 | -1,307 | ±104 | 2K | baseline (K=5 floor=0.5) |
| 600M | -128.6 | -1,286 | ±102 | 2K | plateau |
| 700M | -112.9 | -1,129 | ±113 | 2K | floor=0.3 starts |
| **800M** | **-72.1** | **-721** | ±49 | 2K | **plateau breakthrough** |
| **900M** | **-69.5** | **-695** | ±76 | 2K | best 2K-hand result |
| 987M (2K) | -9.0 | -90 | ±70 | 2K | misleading point estimate, wide CI |
| **987M (20K)** | **-49.7** | **-497** | **±21.9** | **20.4K** | **REAL benchmark** |
| **1B (frozen)** | (in progress) | — | — | — | V4 final, V5 source |

**Paper @ 2.7B: +11.1 bb/100. Real gap to paper at V4 final: ~61 bb/100.**

The 987M 2K result was within the 20K CI (-71 to -28) — not wrong, just *uninformative*. 2K-hand benchmark CI is ±60-80 bb/100, only useful for detecting >100 bb/100 regressions. Don't quote 2K results without their CI.

---

## Critical Lessons Learned

### 1. **Read papers BEFORE coding, not after debugging**

I implemented V3 with naive PPO and lost 14 days of training before realizing Trinal-Clip is the paper's main contribution. The paper has a Table 2 ablation showing:
- Original PPO: ELO 1257
- Trinal-Clip PPO: ELO 1597 (+340)

**Always do an audit of paper's named contributions before considering implementation done.**

### 2. **Hyperparameter tuning is empirical — assumptions can be wrong**

I assumed K=3 would be more stable than K=5. Empirically false. The actual issue was entropy collapse (floor=0.1 too late), not pool size.

### 3. **Auto-save healthy checkpoints**

The 700M crash overwrote the healthy 700M model (live training kept saving the corrupted state). After this, I built `safe_watcher.py` that auto-copies the live ckpt to a "safe" file ONLY when health metrics are good (vloss < 1500, entropy > 0.8). Also creates rolling backups every 50M hands.

This saved us multiple times during V4 phase 7.

### 4. **CI matters at small samples**

I made the mistake of celebrating a 30-hand result of +1,290 mbb that was pure noise. Always run 2000+ hands for Slumbot benchmark; 500 hands has CI ±3,000 mbb which is meaningless.

### 5. **Stack depth must match benchmark**

Both V3 and V10 were trained at 50bb but Slumbot is 200bb. Massive performance hit (~2,000 mbb/hand) just from stack mismatch. Always train at the benchmark target stack.

---

## Production Config (Current Best)

```bash
python scripts/alpha_holdem/train_mp3.py \
  --device cuda \
  --workers 28 \
  --hands-per-iter 16384 \
  --total-hands 1000000000 \
  --starting-stack 200.0 \
  --lr 3e-4 \
  --gamma 0.999 \
  --delta1 3.0 \
  --ppo-epochs 4 \
  --mini-batch-size 1024 \
  --epsilon 0.15 \
  --entropy-coef 0.05 \
  --k-best 5 \
  --snapshot-every 200 \
  --save-interval 100 \
  --out models/alpha_holdem_v4.pt
```

In `train_mp3.py` defaults:
- `entropy_floor=0.3` (CRITICAL — was 0.5, dropped to 0.3 for breakthrough)
- LR decay: linear from `args.lr` to `args.lr/3` in second half of training

Run watcher in parallel:
```bash
python scripts/alpha_holdem/safe_watcher.py
```

---

## Trinal-Clip PPO Formula (from paper Eq. 3, 4)

**Policy loss:**
```
L^tcp = clip(clip(r_t, 1-ε, 1+ε), δ₁) · Â_t

ε = 0.2  (standard PPO)
δ₁ = 3.0  (outer policy bound)
```

**Value loss (THE key innovation):**
```
L^tcv = (clip(R_t, -δ₂, +δ₃) - V(s_t))²

δ₂ = hero chips committed in trajectory  ← DYNAMIC per trajectory
δ₃ = villain chips committed in trajectory  ← DYNAMIC per trajectory
```

The dynamic per-trajectory bounds prevent value loss explosion at deep stack depths (200bb has ±200 BB reward range).

Implementation in [scripts/alpha_holdem/train_mp3.py](scripts/alpha_holdem/train_mp3.py) `trinal_clip_ppo_update()` function.

---

## Slumbot API Protocol

For benchmarking against Slumbot 2019 (ACPC champion, current public benchmark):

- Base URL: `https://slumbot.com/slumbot/api/`
- Endpoints: `new_hand`, `act`
- Format: 200bb HUNL, SB=50 chips, BB=100 chips, Stack=20000 chips
- Action string: `"b200c/kb400"` (k=check, c=call, f=fold, bN=bet to N chips on this street)
- `client_pos`: 0=BB, 1=SB

**Bug we hit:** All-in must be capped at remaining stack on **current street**, not total stack. Slumbot rejects illegal bets silently and returns confused state.

Implementation: [scripts/alpha_holdem/play_slumbot.py](scripts/alpha_holdem/play_slumbot.py)

---

## What's Still Missing vs Paper

1. **Total compute**: 1B hands vs paper's 2.7B (~2.7x less)
2. **K value**: Paper didn't disclose. We use K=5, possibly suboptimal
3. **Snapshot frequency**: We do every 200 iter (~3.3M hands). Paper unclear.
4. **ELO update details**: We use simple K-factor=32. Paper unclear.
5. **Possible reward signal edge cases**: Not fully audited

The 80 bb/100 gap to paper is likely 50-70 bb/100 explainable by compute, plus 10-30 bb/100 unknowns.

---

## Scripts Quick Reference

| Script | Purpose |
|--------|---------|
| `network.py` | Network definition (8.15M params) |
| `environment.py` | HUNL env with chip tracking |
| `train_mp3.py` | **PRODUCTION TRAINER** (Trinal-Clip + K-best) |
| `safe_watcher.py` | Health-monitoring + auto-backup |
| `evaluate.py` | vs simple opponents (Random/CallStation/Aggressive) |
| `play_slumbot.py` | Slumbot 2000-hand benchmark |

Resume training:
```bash
python scripts/alpha_holdem/train_mp3.py --resume models/alpha_holdem_v4.pt [other args]
```

---

## Phase 8: V4 Final + Freeze (2026-05-07)

V4 reached 1B hands at 11:45:28 EDT 2026-05-07.

**20K-hand Slumbot benchmark (12 parallel sessions × 1,700 hands):**
- bb/100: **-49.73**
- mbb/hand: **-497.3**
- CI: ±21.9 bb/100
- Per-session range: +0.29 to -1.32 BB/hand (large run-to-run variance)
- Files: `eval_logs/slumbot_v4_987M_20k_summary.md`

**Freeze artifacts:**
- `models/alpha_holdem_v4_final.pt` — canonical V5 starting point (1000M live ckpt)
- `models/alpha_holdem_v4_final_1000M.pt` — tagged copy for audit trail
- `models/v4_freeze.log` — audit log

**Freeze script:** `scripts/alpha_holdem/freeze_v4.ps1`
- Picks: rolling >= MinHandsM → eval >= MinHandsM → live (only when V4 trainer stopped)
- Default MinHandsM=1000 (1B floor)
- Writes both canonical name + tagged copy

**Auto-launch watcher:** `scripts/alpha_holdem/auto_launch_v5.ps1`
- 5 phases: wait for 1B in log → wait for `models/v5_ready.flag` → kill V4 (if -KillV4) → freeze → launch V5
- Known issue: hidden powershell process died after invoking freeze_v4.ps1. Cause unclear (possibly stdout handling). Worked correctly through phases 1-3, freeze had to be re-run manually. V5 was launched manually.

---

## Phase 9: V5.0 Attempt (in flight, 2026-05-07/08)

**Motivation:** V5 plan (`memory/v5_optimization_plan.md`) targets EIR (Effective Information Rate), not just h/s. V5.0 was the "quick wins" phase — non-architectural changes designed to improve sample efficiency without rewriting hot paths.

**V5.0 changes vs V4 (`scripts/alpha_holdem/train_v5.py`):**
1. `--epsilon 0` default (no epsilon-greedy noise → clean PPO ratio)
2. Both-player transition collection in self-play hands (~2× trainable data per hand)
3. Action table cache (eliminate duplicate `state.legal_actions()` calls)
4. Flat obs view in inference (no list→array→tensor triple-copy)
5. **Latest-K** opponent pool (FIFO of K most recent), replacing K-best ELO ranking
6. Split shm: `assigned_opp_id` (main writes per iter) vs `request_model_id` (worker writes per inference) — fixes a V4 race condition where worker overwrote main's assignment
7. New monitoring metrics: `tdec/s` (trainable_decisions/sec), `inf_bs` (mean inference batch size), separate collect_time / ppo_time

**Resume strategy:**
- V5 launched with `--resume models/alpha_holdem_v4_final.pt --reset-optimizer` (load V4 weights, fresh Adam moments)
- LR start 1e-4 (V4 end LR, no shock); decays to lr/3 in second half of V5 training
- Pool initialized from V4's K-best snapshots, converted to LatestK form

**Decision rule (from V5 plan):**
> V5 must reach V4's bb/100 within 50% of V4's compute (i.e., faster convergence) AND maintain or improve final bb/100 vs Slumbot. If either fails, revert to V4.

### V5.0 in-flight observations (after ~1000 iters / +15M hands)

**Training health: GOOD** — vloss recovered from initial spike (1700) to V4-comparable range (~170-300). Entropy stable at 0.55-0.60 (well above 0.3 floor). No collapse risk.

**Throughput: REGRESSED**

Clean-window measurement (no GPU contention):
| Metric | V4 end | V5.0 clean | Ratio |
|---|---|---|---|
| h/s (raw) | 1300 | 660 | 51% |
| h/s (real, deflated) | 1300 | 550 | 42% |
| trans/sec | 1100 | 970 | 88% |
| trans/real-hand | 1.9 | 2.3 | 121% |

V5.0's both-player collect *did* succeed at producing 2.3× transitions per hand vs V4's 1.9×. But the per-action worker-side cost (dual `hand_buffers[player].append((ci.copy(), ai.copy(), ei.copy(), lm.copy(), ...))`, plus `last_actor` tracking, plus 2× pipe sends in self-play) more than ate the gain.

**Net: V5 produces fewer real hands/sec than V4, ~12% fewer trans/sec. EIR did not improve.**

### Misleading observations (corrected later)

- Reported "h/s 736 → 220, persistent degradation" → recommended rollback. User pointed out they were *gaming* during the window. RTX 4070 contention, not a V5 regression. Rule recorded in `memory/feedback_throughput_eval.md`.
- Reported "+2.07 rew100 = V5 winning" — actually V5 hero crushing its older self-pool, NOT a Slumbot-relevant improvement. Pool members are slightly stale V4 snapshots; current weights stomp them naturally. Vs Slumbot is the only real test.

### Iter counter inflation

V5's `iter_hands` counter inflates by ~1.2× because both-player collect adds 2 terminal markers per self-play hand (one per player). Logged `hands=N` is therefore ~1.2× the real hand count. When comparing V5 to V4 hand counts, divide V5's by 1.2 for apples-to-apples.

### V5.0 verdict (in progress)

**Speed dimension: failed.** V5.0 is slower than V4 in both h/s and trans/s. The V5 plan's "50% of V4 compute" target is unreachable on the speed axis alone.

**Strategy dimension: TBD.** Needs +50M hands of V5 training, then a 20K-hand Slumbot benchmark. If V5 vs Slumbot is meaningfully better than V4's -49.7 (e.g., ≤ -30 bb/100), the "more transitions per hand" mechanism is paying off and we keep V5. If not, rollback to V4 + V5.1 (ring buffer + FastHUNLState — the *real* speedup).

**Rollback plan:** V4 is fully preserved (`alpha_holdem_v4_final.pt` + `train_mp3.py`). To roll back, kill V5, resume V4: `python train_mp3.py --resume models/alpha_holdem_v4_final.pt --total-hands 2000000000 ...`.

---

## Acknowledgments / Self-Critique

This whole journey took 3+ weeks. Roughly half was wasted on:
1. V3 trained without Trinal-Clip (14 days lost)
2. K=3 experiment (3 days lost — wrong hypothesis)
3. floor=0.5 plateau (5 days stuck)
4. **V5.0 worker-side over-engineering** (1+ days, in flight) — the per-action Python work in workers was already the bottleneck; V5.0 added MORE per-action work and lost throughput as a result. V5.1's plan to move data accumulation to a shm ring buffer in main process is the actual fix.

If I had read the paper carefully on day 1 and just implemented `K=5, floor=0.3, Trinal-Clip` from the start, we'd have hit -70 bb/100 in 7-8 days instead of 21+ days.

**The remaining ~61 bb/100 gap to paper is mostly compute** (we have 1/2.7 of paper's hands). Closing it would need either more training or a more efficient game engine (current Python game logic is the bottleneck — only ~1000 h/s vs paper's likely 3000+).
