# V5 Method Improvement Roadmap — ranked by expected value

Date: 2026-07-06. Author: Claude (Fable 5).
Basis: `reports/v5_training_method_audit_20260706.md` (problem IDs S1-S4, M1-M10 referenced below).
Execution discipline: every item here must go through `docs/V5_TRAINING_PLAYBOOK.md` and be
registered in `reports/v5_experiment_ledger.md` BEFORE any code lands in the trainer.

Ranking criterion: (expected Slumbot-relevant gain) x (confidence) / (effort + risk).

---

## Tier 1 — do these first (highest EV, well-understood)

### R1. Batched multi-env rollout (fixes S1) — THE throughput fix

Each worker process runs M=16-32 environments instead of 1. Worker steps every env to its
next decision point, writes M observations into its shm slot block, requests inference for
all of them at once. Main-side inference logic is unchanged except shm layout becomes
(W x M) slots.

- Expected: inf_bs ~10 → 300-900; effective h/s 600 → 2,500-5,000. 2.7B hands: 52 days → 10-14 days.
- Effort: 2-4 days (worker loop rewrite + shm layout + throughput gate validation).
- Risk: medium (concurrency bugs). Mitigation: obs-equivalence smoke (fixed seed, M=1 must
  reproduce current behavior), then throughput gate ≥2x before cutover, standard
  post-cutover health watch.
- Note: keep the per-hand opponent-assignment read and hand accounting semantics identical.

### R2. Engine + encoding fast path (fixes S2, S3)

a) In-place `apply()` variant for rollout (no full clone per action); sample 9 cards
   instead of full-deck shuffle; cache card tensor between decisions (update only on
   street change).
b) Incremental action-history encoding: maintain the (25,4,5) tensor per env, appending
   one slot per action — removes the per-decision `get_actions_by_street()` full replay.
   Store pot-at-action-time while at it (prepares M8 fix for a future obs version, but do
   NOT change encoded values in the current run — bit-equivalence required).
c) Shm ring buffer for transitions (replaces pickled pipe sends).

- Expected: 2-4x CPU-side; multiplies with R1 (they compose: R1 fixes batching, R2 fixes
  per-decision cost).
- Effort: 3-5 days. Risk: HIGH if done carelessly — the encoding must stay bit-identical.
  Mandatory gate: fixed-seed trace test — 1,000 hands stepped by old and new env produce
  byte-identical (card_info, action_info, extra_info, legal_mask) at every decision.

### R3. Variance reduction: mirrored deals + all-in runout EV (fixes M1) — THE sample-efficiency fix

a) **Mirrored self-play deals**: in self-play mode, each worker plays every deal twice with
   hole cards swapped between seats (same board). Both trajectories train (they already do
   under both-player collect); the luck component now cancels in expectation within each
   iteration's gradient.
b) **All-in runout EV**: when both players are all-in before river, set the terminal reward
   to exact equity x pot (evaluator exists in `deep_cfr/hand_eval.py` / poker-evaluator)
   instead of the single sampled runout. Log it as a reward-semantics deviation (it changes
   the reward definition from sampled to expected — strictly variance-reducing, same mean).

- Expected: this is the standard poker trick set; gradient variance from dealt luck drops
  massively; the critic (vloss ~2000) finally gets a learnable target. Best candidate for
  "same hands, more progress".
- Effort: a) 1-2 days, b) 1-2 days. Risk: low-medium; a) changes deal correlation (log it),
  b) changes reward semantics (register + validate).
- Validation: vloss trajectory at matched hand counts; mirrored internal eval (R7) trend;
  next quick5k must not regress.

### R7. Mirrored-deal internal evaluation vs frozen anchors (fixes M9) — build BEFORE method experiments

A benchmark script that plays N duplicate-deal hand pairs (same cards, seats swapped)
between a candidate checkpoint and each FROZEN anchor:
- anchor A: `models/alpha_holdem_v4_final.pt` (V4 1B, known -49.7 vs Slumbot)
- anchor B: best previous V5 checkpoint (rolling)

10k mirrored pairs gives roughly the discriminating power of ~100k independent hands for
skill differences. This becomes the PRIMARY between-Slumbot progress signal and the gate
for every method experiment in this roadmap. Without it, no experiment can be judged.

- Effort: 1-2 days (evaluate.py already has head-to-head scaffolding; add duplicate
  dealing + CI output).
- Risk: none to the trainer (read-only, uses frozen checkpoints, runs on CPU/GPU gaps).
- Priority note: build this FIRST — it is the measuring stick for everything else.

---

## Tier 2 — high value, do after Tier 1 measurement exists

### R4. Real strength-ranked opponent pool (fixes M2)

At each snapshot event (every 200 iters), run a fast round-robin: candidate vs each
current pool member, 1-2k mirrored deals each (cheap with R1+R3a; minutes of wall time).
Update ELO; keep top K=5 by ELO. This replaces the `loss-kbest` proxy with the paper's
actual selection criterion.

- Expected: pool actually contains the strongest historical versions; removes a silent
  failure mode where the agent trains vs weak opponents while metrics look fine.
- Effort: 2-3 days. Risk: low (selection logic only; pool format unchanged).
- Validation: log pool ELO table per snapshot; mirrored internal eval trend over ≥30M hands.

### R5. Group opponent assignment (fixes M3)

Partition workers into G=4-5 groups; each group samples its own opponent per iteration
(one group forced self-play to keep the 0.2 fraction). Inference already groups by
request_model_id, so batches stay large (K+1 batches instead of 1). Every PPO update then
sees a MIXTURE of opponents instead of a single one.

- Expected: removes per-update distribution lurching; should visibly calm internal-probe
  swings and vloss bounce.
- Effort: <1 day (`assign_opponents()` only). Risk: low. Add `--opponent-assignment per-group`.

### R6. Decay the action priors to zero (fixes M4)

Schedule: halve all active prior coefs every 25M hands until <0.005, then 0. Register as
an experiment with explicit abort criteria (if SB open collapses back to limp>0.5 AND
mirrored internal eval regresses, reconsider — but with R3 in place the value signal
should hold the raise frequency up on its own merits).

- Effort: trivial (flag change at a controlled continuation). Risk: low with R7 in place.
- Rationale: priors are shaping action FREQUENCIES without hand-strength conditioning;
  evidence (75M→100M flat, guardrail oscillation) says they are not buying Slumbot bb.

### R8. PPO stability pass (fixes M5, M6)

- KL early-stop: break the epoch loop when approx_kl > 0.03.
- Entropy coef schedule: linear 0.05 → 0.01 over the first 1B hands; keep floor=0.3 boost
  as a safety net only.
- Optional: value-target rescale by /200 with matching δ2/δ3 and GAE rescale (M7) — pure
  reparameterization, do it in the same registered change.

- Effort: <1 day. Risk: low. Validation: kl/clipfrac land in 0.01-0.02 band; entropy
  declines smoothly; mirrored internal eval does not regress.

---

## Tier 3 — worth exploring after Tiers 1-2 are validated

- **R9. Longer-lag pool diversity (M10)**: reserve 1-2 pool slots for old snapshots
  (e.g. 50M+ hands old). Cheap ablation.
- **R10. Auxiliary value features**: give the value head (not the policy) side information
  at train time — e.g. current equity vs uniform range — as an auxiliary prediction target
  to speed critic learning. Logged deviation; policy input unchanged.
- **R11. bf16 rollout inference + torch.compile** after R1 makes batches big enough to matter.
- **R12. Obs version V6** (fix M8 pot-at-action-time + slot overflow) — bundle all obs
  changes into one version bump with its own from-zero ablation or careful fine-tune;
  never hot-swap obs semantics mid-run.
- **R13. Async actor-learner** (old V5.4 idea) — only if R1+R2 still leave GPU idle.

## Explicitly NOT recommended right now

- **More hand-crafted priors / callguard as official policy** — treats symptoms, fights the
  objective, and the evidence is already negative (audit M4).
- **CFR-teacher distillation into the from-zero run** — violates the from-zero contract
  (`reports/v5_from_zero_contract.md`); would invalidate lineage gates. If ever explored,
  it is a separate run, not this one.
- **Architecture changes (bigger net, transformers)** before throughput + variance are
  fixed — compute is the binding constraint; a bigger net makes it worse.
- **Restart from scratch** — nothing in the audit indicates corrupted learning; the run is
  healthy-but-slow-and-noisy. Fix the loop, keep the hands.

## Sequencing summary (what Codex should actually do, in order)

```
1. R7  mirrored internal eval        (measuring stick; no trainer risk)
2. R1  batched multi-env rollout     (throughput 4-8x; gate: ≥2x h/s + health)
3. R3  mirrored deals + all-in EV    (sample efficiency; gate: R7 trend + quick5k)
4. R6  decay action priors           (simplify objective; gate: R7 trend)
5. R5  group opponent assignment     (stability; gate: probe variance shrinks)
6. R8  KL early-stop + entropy sched (stability; gate: kl band + R7 trend)
7. R4  ELO pool                      (paper alignment; gate: R7 trend over 30M+)
8. R2  engine fast path              (more throughput; gate: bit-equivalence + ≥1.5x)
```

One change per continuation window. Details, gates, and rollback procedures:
`docs/V5_TRAINING_PLAYBOOK.md`.
