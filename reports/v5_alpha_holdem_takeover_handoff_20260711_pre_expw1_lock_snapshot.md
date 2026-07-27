# V5 AlphaHoldem Takeover Handoff - 2026-07-11

Checked: 2026-07-11T07:03:49.2223140Z

## Immutable objective

- AlphaHoldem V5-from-zero, full 200bb HUNL, official greedy-direct Slumbot.
- L5: 100k+ official hands, bb/100 > 0, 95% CI lower > 0. L6 additionally near +11.1 bb/100.
- EXP-002 retained; EXP-003 terminally INCONCLUSIVE; EXP-004 priors fixed 0.01/0.02.
- Ledger append-only, fail-closed, exact checkpoint identity, complete bundle, one behavior change.
- Remaining 2.7B budget is not continuation authority.

## Authoritative current state

- Historical EXP-005 pilot: EXPLORATORY_PILOT_NO_METHOD_JUDGMENT.
- EXP005-C: EXP005C_FAIL_PROTOCOL_ABORT.
- Design lock SHA256: 2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007.
- First60 effective h/s: control 2658.731142; treatment 1101.197545; ratio 0.4141816098 < 0.85.
- Treatment after row60: POST_PROTOCOL_EXPLORATORY_ONLY.
- Primary stopped at 7,083 partial pairs; MEAS-001/promotion/formal forbidden; Tier-2 frozen.
- All generic cadence/downstream launch paths terminal blocked; heartbeat paused.

## Route pivot

- Corrected researcher review: ROUTE_PIVOT_EXP_W1_ELIGIBLE_REQUIRES_REGISTRATION.
- EXP005-C supplies protocol-failure evidence only, not a poker-effect estimate.
- W1 is the only eligible route and is worth moving into exact-design preregistration work.
- Generic W1 is not registered. Preferred first design candidate is isolated value-head-only warmup because it preserves reward semantics; this preference is not launch authority.
- W2 is ineligible. No behavior, trainer, MEAS, promotion, formal, or Slumbot launch is authorized.
- Next: freeze one exact W1 variable, checkpoint/lineage, data, budget, optimizer/seeds, rollback and gates; then preregistration review only.

## Official strength

- L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].