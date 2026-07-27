# V5 Training Playbook — canonical operating workflow

Date: 2026-07-06. Author: Claude (Fable 5).
Audience: Codex or any agent operating the AlphaHoldem V5-from-zero Slumbot track WITHOUT
human or Fable supervision. This document is the HOW; the WHAT is in
`reports/v5_method_improvement_roadmap.md`; the WHY is in
`reports/v5_training_method_audit_20260706.md`; the record of every change is
`reports/v5_experiment_ledger.md`.

This playbook does not replace the evidence rules in `AGENTS.md` ("User-Mandated
AlphaHoldem Workflow") — it extends them with the speed and training-method workstreams.
On any conflict, AGENTS.md evidence/claim rules win.

---

## 0. Prime directives (read every session)

1. **The goal is Slumbot bb/100, proven by CI.** Nothing else is a success metric.
   L5 = 100k+ official greedy hands, bb/100 > 0, 95% CI lower bound > 0. L6 = near +11.1.
2. **One variable at a time.** Never land two behavior-affecting changes in the same
   continuation window. Reporting/monitoring changes are exempt.
3. **Pre-register before you touch the trainer.** Every trainer/env change gets a ledger
   entry (hypothesis, expected effect, gate, abort criteria, rollback) BEFORE the code runs.
4. **Never lose lineage.** Continuations use `v5_continue_after_gate.ps1` semantics:
   resume from a verified gate checkpoint with `--allow-resume --no-reset-optimizer`,
   preserving `fresh_from_zero_lineage`. Archive the pre-change checkpoint path in the
   ledger entry.
5. **A noisy signal cannot justify a change.** Minimum evidence to act is defined per
   signal in §3. If the signal's CI includes "no effect", the verdict is INCONCLUSIVE, not
   "slightly better".
6. **Throughput is a first-class objective.** At 600 h/s, paper scale takes ~52 days.
   Speed work that passes its gates is not a deviation — it is the plan.
7. **When in doubt: keep training, collect evidence, write the ledger entry.** The
   default action is always "continue + measure", never "intervene + hope".

## 1. The operating loop (repeat forever)

```
┌─> A. HEALTH: dashboard/queue/gate checks (existing watchers) ── FAIL -> §6 incident
│   B. MEASURE: throughput snapshot + mirrored internal eval at each snapshot cadence
│   C. MILESTONE: Slumbot quick5k per cadence (25-50M); 20k at 250M+; 100k only for claims
│   D. DECIDE: consult §4/§5 decision trees — is a registered experiment due?
│   E. EXECUTE: one experiment through the §2 lifecycle (or nothing)
└── F. RECORD: ledger update + trend ledger refresh + takeover handoff update
```

Cadence guidance: A continuously (watchers already do); B every 200-iter snapshot;
C per eval-cadence watcher; D/E/F at gate boundaries only.

## 2. Experiment lifecycle (mandatory for ANY trainer/env change)

### 2.1 Register
Add a ledger entry (`reports/v5_experiment_ledger.md`) with ALL fields filled:
ID, date, problem ref (audit S*/M*), hypothesis, exact change (flags/diff), expected
effect + metric, gate (pass criteria + sample size + deadline), abort criteria, rollback
path, status=REGISTERED.

### 2.2 Validate offline
- `python -m py_compile` on every touched file.
- CPU smoke: `python scripts/alpha_holdem/train_v5.py --device cpu --workers 1
  --hands-per-iter 4 --total-hands 4 --ppo-epochs 1 --mini-batch-size 4
  --snapshot-every 1 --save-interval 1 --run-dir tmp/<exp_id>_smoke --run-id <exp_id>
  --overwrite --max-runtime-seconds 120` (+ the experiment's flags).
- For env/encoding changes: fixed-seed trace equivalence test (see §5.2) — REQUIRED.
- For speed changes: short GPU A/B (5-10 min each) in a scratch run dir if feasible.

### 2.3 Cutover (controlled)
- Wait for the next gate PASS. Freeze + archive the current checkpoint (ledger records path).
- Stop trainer / relaunch continuation with the new flag(s)/code via the documented
  continuation path. NEVER hot-edit code under a running PID.
- New run-dir suffix names the experiment (existing convention), watchers re-armed.

### 2.4 Judge at the gate you registered
- Pass -> status=ADOPTED, keep it, update AGENTS.md snapshot.
- Fail/abort -> status=REVERTED, roll back to the archived checkpoint + prior code path,
  write what was learned. A reverted experiment with a clear lesson is a SUCCESS of the
  process. Silence is the only failure.

### 2.5 Never
- Stack a second change while the first is inside its judgment window.
- Extend a failing experiment's window because "it looks like it's turning around".
- Rename success criteria after launch.

## 3. Signals: what each one may and may not justify

| Signal | Sample | Approx CI | May justify | May NOT justify |
|---|---|---|---|---|
| train log (vloss/ent/kl/mix) | continuous | — | incident response; PPO-band tuning (R8) | any strength claim or strategy tuning |
| internal probe 200h vs scripted | 200 | ±300-900 bb/100 | smoke alarm only | tuning, regression verdicts |
| **mirrored internal eval (R7)** | 10k pairs | ~±8-15 bb/100 | experiment gates; progress trend | Slumbot claims |
| Slumbot quick5k | 5k | ±40-60 bb/100 | milestone calibration; >100 bb/100 regressions | tuning on deltas <60; claims |
| Slumbot promotion 20k | 20k | ±20-25 bb/100 | "better than V4" candidacy | L5/L6 |
| Slumbot formal 100k | 100k+ | ±10 bb/100 | L5/L6 claims (with CI rule) | — |

Rule of thumb: an effect must exceed the signal's CI to count. Design experiments around
the mirrored internal eval — it is the only cheap signal with usable resolution. Build it
first (roadmap R7) if it does not exist yet.

## 4. Speed workstream — how to make training faster

### 4.1 Measurement protocol (before ANY speed work)
1. 200-iteration window from `latest_train.log`: record mean h/s, tdec/s, inf_bs,
   collect s, ppo s. Confirm no GPU contention (no gaming/benchmarks — see
   `memory/feedback_throughput_eval.md` rule).
2. Attribute time: collect% vs ppo%. Today: collect ≈ 91%. Only attack the dominant term.
3. Record the baseline in the ledger entry. All speed gates compare against THIS window.

### 4.2 Priority order (from the roadmap; do not reorder without new evidence)
R1 batched multi-env rollout → R2 engine fast path → R11 bf16/compile.
Windows micro-tuning (timer resolution, spin-waits, priorities) is allowed but measure
first — do not assume sleep granularity; instrument the poll loops before touching them.

### 4.3 Speed gates (adopt only if ALL pass)
- h/s ratio ≥ the registered target (R1: ≥2.0x; R2: ≥1.5x; micro: ≥1.1x) over ≥10 iters
  clean window (`v5_throughput_compare.py` exists for exactly this).
- Health PASS streak ≥ 3 gates post-cutover; entropy/vloss/action-mix in normal bands.
- No semantic drift: for env/encoding changes, the §5.2 equivalence test passed BEFORE
  cutover; for scheduler-only changes (batching), action-mix and rew100 bands unchanged.
- Mirrored internal eval (if available): no regression beyond CI at the next snapshot.

### 4.4 Known traps
- Do not run CUDA sweeps/benchmarks concurrently with the trainer PID.
- `--opponent-assignment` interacts with inference batching (documented 2.3x); any worker
  restructure must preserve per-hand assignment semantics and hand accounting
  (`hand_marker`), or 150M/250M cadence targets go wrong.
- Both-player collect made V5.0 SLOWER once (HANDOVER.md Phase 9). Every "more data per
  hand" idea must be judged on real-hands/sec AND trans/sec, not either alone.

## 5. Training-method workstream — how to improve the model

### 5.1 Priority order (from the roadmap)
R7 measuring stick → R3 variance reduction → R6 prior decay → R5 group assignment →
R8 PPO stability → R4 ELO pool → tier 3.

### 5.2 Env/encoding equivalence test (required for R2, and any obs-touching change)
Script requirement: instantiate old env and new env with the same seed; step both with the
same action sequence for ≥1,000 hands; assert byte-identical card_info / action_info /
extra_info / legal_mask at every decision and identical rewards at every terminal.
Any intentional semantic change (e.g. all-in EV rewards, R3b) is NOT an equivalence change —
it gets its own experiment with reward-semantics explicitly registered.

### 5.3 Method gates (adopt only if ALL pass)
- Health: PASS streak ≥ 3 gates post-cutover.
- Primary: mirrored internal eval vs anchors improves (or registered non-inferiority
  holds) over the registered window — default ≥30M hands / ≥2 snapshot points.
- Guard: next scheduled quick5k does not regress by >60 bb/100 (its own CI) vs the last
  pre-change quick5k.
- The change's own micro-metric moved as hypothesized (e.g. R3: vloss at matched hands
  clearly below the pre-change trend; R8: kl into 0.01-0.02 band; R6: priors ramped to 0
  without SB-open collapse).

### 5.4 Tuning discipline (extends AGENTS.md rule "don't tune from bb/100 alone")
- No new hand-crafted action priors. The existing ones are scheduled for decay (R6).
  If a leak persists after R3+R4+compute, the answer is more/better training signal, not
  frequency shaping — escalate to the user instead of adding priors.
- Hyperparameter changes (lr, entropy, K, snapshot cadence) are experiments like any
  other: ledger entry, one at a time, judged on the mirrored internal eval.
- Never switch the official eval policy off greedy.

### 5.5 The Slumbot loss-review loop (unchanged, now with teeth)
After every official Slumbot result, run the existing loss-report/hand-review/artifact
pipeline (see AGENTS.md §Slumbot Hand-Log Review). Its output feeds DIAGNOSIS —
localize which street/position/bucket leaks — but intervention requires the §2 lifecycle
plus a Tier-1/2 roadmap justification. Hand review localizes; it does not license tuning.

### 5.6 Poker-research inference gate

Apply `docs/V5_POKER_RESEARCHER_DECISION_CONTRACT.md` before registering the next
behavior change.

1. Run `v5_loss_inference_audit.py` on the complete official dump bundle. Its
   session-cluster CIs, opportunity rates, and multiplicity-adjusted comparisons are
   descriptive/associational only. A hero-fold bucket, losing line, or hole family does
   not identify counterfactual action value or regret.
2. If the diagnosis claims self-play cycling, require a complete frozen common-deal
   snapshot payoff matrix and a PASS audit from `v5_crossplay_cycle_audit.py`. Action
   rates, KL, and 200-hand probes nominate the hypothesis but cannot prove the cycle.
3. Run `v5_poker_research_review.py` over the loss, action-regret, cross-play, value,
   asset, method, and official artifacts. Missing artifacts remain MISSING. The reviewer
   never authorizes a launch; it defines which claims and registrations are supportable.
4. A same-start one-seed PASS may select that one candidate model but must be labeled
   `CONDITIONAL_SINGLE_SEED_METHOD_EFFECT`. A general method claim needs at least two
   preregistered independent paired seeds.
5. Action-specific tuning requires a validated `v5.action_regret.audit.v1` artifact or
   a separately registered same-state controlled experiment. Do not invent a
   counterfactual from realized Slumbot terminal winnings.

## 6. Incident response (health FAIL or crash)

1. Trainer died: inspect console.err.log; if clean OOM/transient → relaunch continuation
   from latest verified checkpoint (same flags), note in ledger ops log. Recurring → open
   an incident entry, bisect the last change.
2. Entropy collapse (<0.3 sustained with boost active): do NOT restart immediately —
   snapshot the state for forensics, then restore from the last healthy checkpoint;
   check whether a recent experiment's judgment window overlaps; revert it if so.
3. vloss explosion (>10x rolling median for >20 iters): same forensic-then-restore path.
4. Windows-level (GPU driver, reboot): relaunch continuation; verify watchers; refresh
   dashboard; nothing else.
5. Any incident during an experiment's judgment window voids the window — restart the
   measurement, do not judge on contaminated data.

## 7. Milestone protocol (evidence ladder — unchanged from AGENTS.md, summarized)

- quick5k per eval-cadence (currently every 25-50M): calibration only; full artifact
  bundle mandatory (hands JSONL, dumps, CI, gate, loss report, audit, hand review).
- 250M+: promotion20k vs fresh V4 direct baseline (-71.383 ± 20.839, 20.4k hands;
  `reports/v4_vs_slumbot_fresh_20260709_final.json` supersedes the old -49.7 baseline).
  Clear improvement → candidate.
- Candidate + mirrored internal eval positive vs V4 anchor → schedule formal 100k.
- Claims: only from the formal 100k with the CI rule. No exceptions, no approvals override.

## 8. Reporting template (every gate-boundary report)

```
run_id / checkpoint iter+hands / h_s effective / health
experiments: <ledger IDs in flight + status + window progress>
mirrored internal eval: <candidate vs anchors, N pairs, bb/100 ± CI>
latest official Slumbot: <milestone, bb/100, CI, class>
next: <the single next action and which gate it waits on>
```

### 8.1 Single audit trail — MANDATORY (added 2026-07-07 after first audit)

The Ops log table in `reports/v5_experiment_ledger.md` is the ONE append-only audit
trail. Detailed reports may live in their own files, but each of the following events
MUST also get one row in the Ops log, appended at the time of the event, with a pointer
to the detail file:

- every official Slumbot result (milestone, bb/100, CI, artifact-bundle status)
- every mirrored internal eval artifact (candidate, anchors, result, CI)
- every incident (eval stall, crash, watcher death) + root-cause status
  (root cause CONFIRMED / SUSPECTED / UNKNOWN — do not write a guess as a conclusion)
- every experiment status transition (REGISTERED→RUNNING→ADOPTED/REVERTED)
- every trainer continuation/restart and every watcher add/remove
- one summary row per 100-gate monitoring window even if nothing happened
  ("gates 9200-10800 all PASS, no interventions")

Audit standard: a reviewer must be able to reconstruct WHAT happened in any window from
the Ops log ALONE, then drill into detail files only for WHY. If an event is not in the
Ops log, it did not happen — a scattered record is a missing record.

## 9. Escalate to the user (only these)

- Any proposal to break the from-zero contract (e.g. distillation, resume from V4).
- Architecture/obs-version changes (V6): register + design, but get sign-off before launch.
- Abandoning the 2.7B target or the run itself.
- Two consecutive REVERTED Tier-1 experiments (means the plan's assumptions are wrong —
  re-audit instead of thrashing).
- Anything requiring spending money or external services beyond Slumbot API.

Everything else inside this playbook + AGENTS.md rules is pre-authorized: measure, register,
execute, judge, record, continue.
