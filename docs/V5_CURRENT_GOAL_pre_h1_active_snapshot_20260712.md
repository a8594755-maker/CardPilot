# V5 Current Goal

Checked: 2026-07-12T02:44:00Z

## Layer 1 — Immutable objective (never changes on experiment outcomes)

- General strong 200bb HUNL agent; official greedy-direct Slumbot is the milestone evaluator.
- L5 claim: 100k+ official greedy-direct hands, bb/100 > 0, 95% CI lower > 0. L6: additionally near +11.1 bb/100.
- Ledger append-only, fail-closed, exact checkpoint identity, complete bundle, one behavior change per window.
- Terminal experiment states are permanent and must not be reopened: EXP-002 RETAINED; EXP-003
  TERMINAL_INCONCLUSIVE; EXP-004 priors fixed 0.01/0.02; EXP005-C `EXP005C_FAIL_PROTOCOL_ABORT`;
  EXP-W1 `EXP_W1_FAIL_WARMUP_GATE`. All their forbidden evidence and downstream paths remain closed.

## Layer 2 — Route (changed by explicit user escalation, 2026-07-11)

- The from-zero constraint is LIFTED. The user explicitly escalated and authorized abandoning the
  V5-from-zero route identity on 2026-07-11 (ledger event
  `v5-user-route-escalation-hybrid-goal-20260711`). "From-zero" is no longer part of the objective.
- This escalation supersedes the post-EXP-W1 route-pivot decision
  `NO_CANDIDATE_PREREGISTRATION_AUTHORIZED_INCONCLUSIVE_NO_LAUNCH` (artifact
  `reports/v5_post_expw1_route_pivot_decision_20260711.json`, SHA256
  `af9c2f9cefa6a5bbfd66e4bdeed6769a5c93a7650a3d6499456be8935451cc67`).
  That decision was correct under the from-zero constraint; the constraint itself
  has now been removed by the user. The decision artifact remains preserved and read-only.
- The remaining 2.7B-hand figure is a resource cap only; it grants no continuation authority (unchanged).
- New route: HYBRID —
  (a) fix critic magnitude and targets;
  (b) warm-start policy and value by distilling the repo's 200bb CFR assets into the V5
      architecture — this CREATES the compatible asset whose absence blocked the old W2 route;
      do not assume a pre-existing compatible checkpoint;
  (c) opponent-pool (league) training with a complete audited common-deal cross-play matrix;
  (d) play-time subgame resolving on top of the blueprint for official evaluation.
- Milestone ladder. Official Slumbot hands are spent only at milestones; routine gates use the
  internal duplicate/mirror eval (`v5_mirror_eval.py`) and frozen opponent panels. M1–M4 thresholds
  are advisory until frozen inside a window preregistration; L5/L6 are immutable.
  - M0 (current): L0, -153.3 bb/100 over 20,400 official hands.
  - M1: warm-start point >= V4 baseline (-71.4 bb/100), 20k official hands, CI separated from M0.
  - M2: blueprint policy alone > -40 bb/100, 20k official hands.
  - M3: blueprint + resolver > -15 bb/100, 20k official hands.
  - M4: point estimate > 0, 40k official hands (pre-L5; still no strength claim).
  - M5 = L5: 100k+ official hands, 95% CI lower > 0.

## Layer 3 — Window plan (each window requires its own immutable preregistration before launch)

- H1 — REGISTERED_NO_LAUNCH. Immutable preregistration
  `reports/v5_hybrid_h1_preregistration_20260711.json`, SHA256
  `bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab`; independent
  audit v2 PASS21/21 SHA `eef20d4373e012f9232163c9cc902a62e07de9d34743f243e35680c909ccca0f` and tamper/authority tests12/12. Integrated critic-v2 treatment fixes all critic values
  to effective-stack units (/200; PopArt forbidden), uses a detached deep 256→256→128→1
  value head, and retunes value_coef0.5→1.0. Same-start control/treatment are fixed20M each.
  H1-CAL-001 primary requires normalized held-out MSE reduction point≥15% and bootstrap95%
  lower≥10%, with h/s≥0.85 and entropy non-inferior. Training metrics only; official hands0.
  Registration authorizes implementation/offline validation only; launch authority remains NONE
  until H1-CAL-001, implementation validation, immutable design lock and preflight all PASS.
- H2 — variance-reduced value targets: generalize the bounded-K runout EV correction from
  all-in-only to all showdown terminals. Gate: registered value-target variance reduction plus
  internal mirror eval non-inferior.
- H3 — CFR/BC warm-start (new run lineage): distill 200bb CFR solutions into the V5 network for
  policy; supervise the value head with CFR counterfactual values. Includes building and QA-ing
  the distillation dataset from the Path-1 200bb solve output. Gate: M1.
- H4 — opponent league: fixed-mix pool (snapshots, heuristics v1–v3.1, V4, warm-start anchor) with
  a complete audited common-deal cross-play matrix. This window absorbs the EXP-007 pool
  hypothesis and the previously permitted frozen common-deal pool-selection measurement design;
  that design work may proceed as reporting-only preparation for H4 at any time.
  Gate: complete matrix, no cycle, internal panel improvement.
- H5 — play-time resolver on the blueprint for official evaluation. Gate: M3.
- One behavior change per window, judged only at its registered gate. Re-ranking H-windows before
  registration is allowed when new frozen evidence justifies it; post-registration redesign is not.

## Stop rule

- Each window carries a fixed registered hands/GPU budget. Two consecutive windows ending FAIL or
  without registered-gate progress trigger an automatic route review; no inertia continuation.

## Authority

- This document grants direction, not launch authority. Every trainer or evaluation launch still
  requires its window's immutable preregistration, preflight identity checks, and watcher arm to PASS.
- User blanket in-goal autonomous execution authorization (2026-07-11) applies to this goal.
  Evidence gates, immutable locks, fail-closed rules, claim standards, no-spend/no-secret rules,
  and platform security approvals remain binding.
- Next valid action: implement critic-v2 and H1-CAL-001 reporting-only holdout tooling, complete
  offline fixtures/tamper tests, then publish a separate immutable H1 design lock. No arm launch
  before implementation validation, calibration-bundle audit, lock verification and canonical
  watcher preflight all PASS.

## Official strength

- L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].
