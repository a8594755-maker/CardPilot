# V5 AlphaHoldem Takeover Handoff - 2026-07-11

Checked: 2026-07-12T02:44:00Z

## Immutable objective

- General strong 200bb HUNL agent; official strength only from greedy-direct Slumbot.
- L5 requires 100k+, bb/100 > 0 and CI lower > 0; L6 additionally near +11.1.
- EXP-002 retained; EXP-003 terminal INCONCLUSIVE; EXP-004 priors 0.01/0.02.
- EXP005-C and EXP-W1 remain terminal FAIL classifications; 2.7B is a resource cap only.

## Authoritative route state (user escalation 2026-07-11)

- The user explicitly escalated and LIFTED the from-zero constraint (ledger event
  `v5-user-route-escalation-hybrid-goal-20260711`). The new authoritative goal is
  `docs/V5_CURRENT_GOAL.md`, SHA256 `533ef5359dcccdb7a8420df0c59482b560d5108005f3f1cfc384140799c3d228`.
- This supersedes decision `NO_CANDIDATE_PREREGISTRATION_AUTHORIZED_INCONCLUSIVE_NO_LAUNCH`
  (artifact `reports/v5_post_expw1_route_pivot_decision_20260711.json`, SHA
  `af9c2f9cefa6a5bbfd66e4bdeed6769a5c93a7650a3d6499456be8935451cc67`), which was correct under the
  now-removed from-zero constraint. The artifact stays preserved read-only.
- New route: HYBRID — critic magnitude/target fix; CFR/BC distillation warm-start (creates the
  compatible 200bb asset that the old W2 route lacked); opponent league with complete common-deal
  cross-play matrix (absorbs the EXP-007 hypothesis and the permitted pool-selection measurement
  design); play-time subgame resolving for official evaluation.
- Milestone ladder M0(-153.3) → M1(>= V4 -71.4, 20k) → M2(> -40, 20k) → M3(> -15, 20k) →
  M4(> 0 point, 40k) → M5 = L5. Official hands are spent only at milestones; routine gates use the
  internal duplicate/mirror eval and frozen panels.
- Window plan: H1 critic magnitude fix → H2 bounded-K showdown EV targets → H3 warm-start (gate M1)
  → H4 league + matrix → H5 resolver (gate M3). One behavior change per window; each window needs
  its own immutable preregistration before launch. Stop rule: two consecutive FAIL/no-progress
  windows force a route review.
- H1 is `REGISTERED_NO_LAUNCH`: preregistration
  `reports/v5_hybrid_h1_preregistration_20260711.json` SHA
  `bb998b84adb2cee4fa6c8f88861b612c556356c8b91fdae9d9c883b1c7b733ab`; audit-v2 21/21 SHA `eef20d4373e012f9232163c9cc902a62e07de9d34743f243e35680c909ccca0f`
  and tamper/authority tests12/12 PASS. critic-v2 is one integrated package: fixed /200
  effective-stack units (no PopArt), detached deep value head, value_coef0.5→1.0.
  Same-start fixed20M arms; H1-CAL-001 normalized-MSE/throughput/entropy gate only;
  official hands0. Launch authority remains NONE.- All trainer/watchers stopped. Generic cadence, promotion, formal and Slumbot paths remain blocked
  until a window preregistration explicitly unblocks its own measurement.

## Next valid action

- Implement critic-v2 and H1-CAL-001 reporting-only holdout tooling; run offline fixtures and
  tamper tests; then publish a separate immutable H1 design lock and preflight.
- Do not launch either arm before implementation validation, H1-CAL-001 bundle audit, lock
  verification and canonical blocked-watcher preflight all PASS.
- Do not reopen W1/EXP005-C. No official, promotion, formal or Slumbot hands in H1.
## Official strength

- L0: 20,400 greedy-direct hands, -153.2999 bb/100, 95% CI [-187.6945, -118.9052].
