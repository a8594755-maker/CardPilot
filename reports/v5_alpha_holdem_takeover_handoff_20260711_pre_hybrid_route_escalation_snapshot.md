# V5 AlphaHoldem Takeover Handoff - 2026-07-11

Checked: 2026-07-11T17:08:00Z

## Immutable objective

- AlphaHoldem V5-from-zero 200bb HUNL; official strength only from greedy-direct Slumbot.
- L5 requires 100k+, bb/100 > 0 and CI lower > 0; L6 additionally near +11.1.
- EXP-002 retained; EXP-003 terminal INCONCLUSIVE; EXP-004 priors 0.01/0.02.
- EXP005-C and EXP-W1 remain terminal FAIL classifications; 2.7B is not continuation authority.

## Authoritative route-pivot state

- Decision: `NO_CANDIDATE_PREREGISTRATION_AUTHORIZED_INCONCLUSIVE_NO_LAUNCH`.
- Artifact: `reports/v5_post_expw1_route_pivot_decision_20260711.json`, SHA `af9c2f9cefa6a5bbfd66e4bdeed6769a5c93a7650a3d6499456be8935451cc67`.
- Corrected reviewer recognizes EXP-W1 terminal warmup abort and prevents VALUE-AUDIT reuse; it also rejects incomplete schema-only cross-play.
- Real review result: `PROGRAM_STOP_NO_CAUSALLY_SUPPORTED_PIVOT_YET`; focused tests11/11 and combined suite18/18 PASS.
- Current evidence: official staged L0; loss/preflop associations only; internal probes local-only; high-KL mechanism support but isolated EXP-006A frozen selection gate false; W1 terminal; W2 asset missing; action regret missing; cross-play missing.
- EXP-007 ELO pool is only a plausible hypothesis. It is not preregistration-ready because the competitive-vs-loss-kbest measurement, identities, sample/CI and runtime gates are not frozen.
- All trainer/watchers stopped. Generic cadence, promotion, formal and Slumbot paths blocked.

## Next valid action

- Design and audit a reporting-only common-deal pool-selection measurement. Do not register or launch EXP-007 until a future exact permission artifact passes.
- Do not reopen W1, reinterpret realized losses as action regret, claim cycling, or continue by budget inertia.

## Official strength

- L0: 20,400 greedy-direct hands, -153.2999 bb/100, 95% CI [-187.6945, -118.9052].

