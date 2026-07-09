# Phase B Per-Class KL (Option B) — Result (2026-06-07)

Supervisor cycle 5. Implemented + tested Option B (the last untried RL-on-PPO-from-BC lever)
before declaring the axis dead. Per-class anchor KL: pin the fold/call/raise/allin CLASS
distribution to BC while leaving within-class (card-dependent raise-size) choice free —
intended to fix the CC-drift mechanism that sank the full-dist Phase B 1M run (-74).

## Implementation (in-budget, local, reversible)
- `scripts/alpha_holdem/phase2/train_population_ppo.py`: added `class_kl_to_anchor()` (4-way
  fold/call/raise/allin class marginal KL) + `--kl-mode {full,class,both}` flag (default `full`
  = prior behavior, zero change unless selected). Reuses existing `anchor_kl_coef` + its
  data-driven decay. No env/reward/action-space/observation change. Syntax-checked, smoke-clean.
- Slot grouping: fold={0}, call={1}, raise={2..7}, allin={8}.

## Runs (same config as Phase B 1M, only kl-mode/coef changed; seed 42)
| run | coef | outcome | final mix | Slumbot |
|---|---|---|---|---|
| full-dist (cycle 4) | 0.05 | completed 1M | F66/CC27/R6.5 | **~-74** |
| class-KL c05 | 0.05 | **HARD STOP @650k** (critic vloss>1000×3) | **F77/CC11**/R(polarized slot7) | not benched (degenerate, ~floor) |
| class-KL c20 | 0.20 | HARD STOP @800k (critic vloss>1000×3) | **F67/CC24**/R9 (BC-shaped, CC pinned) | **-60.51** ±35 (full 8000 hands) |

## Findings
1. **Class-KL @0.05 is a WEAKER anchor than full-dist @0.05.** Full-dist penalizes drift on all
   9 slots (more restoring force); the 4-class marginal let fold climb to 77% and CC collapse to
   11% — then the critic diverged (vloss 1766→3368) → hard stop at 650k. Degenerate polarized
   policy (77% fold, raise mass pinned to one pot-size slot). WORSE than the full-dist run.
2. **Class-KL @0.20 DOES pin the class dist** (ckl ~0.8, CC held at 22-24% = BC level, fold ~67%,
   BC-shaped throughout). This is the faithful Option-B realization. But it ALSO hard-stopped
   (critic vloss explosion at 800k) and the policy benches **-60.51 bb/100 ±35 (full 8000 hands,
   7/8 sessions Slumbot-significant)** — the same regression band as full-dist (-74) and the
   warm-critic ceiling (-57). It does NOT approach BC's -45.
3. **Mechanism (why Option B can't work):** the failure is per-decision discipline — WHICH hands
   call vs fold — which is largely ORTHOGONAL to the class marginal. Pinning the aggregate
   fold/call/raise proportions (what class-KL does) does not constrain per-hand choices, so the
   RL gradient still drifts individual decisions toward exploiting the training pool (flat-call
   showdown leaks). Freeing within-class raise sizing adds nothing. Class-KL controls the same
   SHAPE the full-dist run already preserved — and shape was never the problem.

## Verdict: Option B EXHAUSTED. PPO-from-BC axis is DEAD.
The full RL-continuation-from-BC family now spans:
- RL-1 5M: -57 | warm-critic 500k/1.5M: -57 | Phase B full-dist 1M: -74 | class-KL c20: ~-60.
None beats the BC anchor's **-45**. Two distinct anchor forms (full-dist, per-class) at multiple
coefs all land -57 to -74. The ceiling is structural to PPO-finetune-from-BC, not a KL-form tuning
problem. Additional KL variants (asymmetric one-sided, per-class coef sweep) would only re-pin the
same SHAPE and cannot touch the per-decision-discipline mechanism.

A secondary, separately-actionable observation: **the critic keeps diverging** (vloss>1000 hard-stop
on both class-KL runs) under mixed-opponent returns even from the kl30_60ep warmup. The value head
cannot track the mixed-pool return distribution — consistent with the warm-critic reports' "critic
re-fits but doesn't converge tight." This is a critic-architecture/target problem, not a policy one.

## Recommendation — pivot to Option E (off PPO-from-BC)
The structural ceiling needs a different algorithm, not more RL continuation. Candidates:
- **E1 (CFR-guided value target):** train the value head against CFR/solver EV targets (we have the
  V3 pipeline + vnet-v10) instead of self-play returns — directly fixes the diverging-critic root.
- **E2 (teacher distillation):** distill a stronger teacher (deeper CFR resolve, or a stronger
  heuristic ensemble) into the policy, rather than RL-exploiting a weak pool.
- **E3 (better SL anchor):** the BC anchor (-45) is still the unbeaten best; improving the *teacher*
  (heuristic v4 / CFR-blended labels) and re-running BC may move the Level-1 reference itself.

E1 directly targets the one new structural defect this cycle surfaced (critic divergence) and reuses
existing CFR assets — recommended as the first E experiment.

## Budget / gates
- All work this cycle: in-budget (2 runs × ~5-6 min, 1 bench; no env/reward/action/obs change; new
  artifacts only, nothing overwritten/deleted; no champion promotion; no Slumbot-beating claim).
- The pivot to E is a **direction change** → user-gated. Surfacing for approval before building E1.

## Artifacts
- `models/ppo/phase_b_class_kl_1M/` (c05, hard-stop @650k)
- `models/ppo/phase_b_class_kl_c20_1M/` (c20, hard-stop @800k, BC-shaped, the Option-B candidate)
- `eval_logs/path_b/phase_b_class_kl_c20_part*.log` (Slumbot bench, in progress)
- trainer diff: `train_population_ppo.py` (class_kl_to_anchor + --kl-mode; default unchanged)
