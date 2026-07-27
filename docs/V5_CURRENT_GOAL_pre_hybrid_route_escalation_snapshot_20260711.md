# V5 Current Goal

Checked: 2026-07-11T17:08:00Z

## Immutable objective

- AlphaHoldem V5-from-zero, full 200bb HUNL, official greedy-direct Slumbot.
- L5: 100k+ official hands, bb/100 > 0, 95% CI lower > 0. L6 additionally near +11.1 bb/100.
- EXP-002 retained; EXP-003 terminally INCONCLUSIVE; EXP-004 priors fixed 0.01/0.02.
- EXP005-C remains `EXP005C_FAIL_PROTOCOL_ABORT`; EXP-W1 remains `EXP_W1_FAIL_WARMUP_GATE`.
- Ledger append-only, fail-closed, exact checkpoint identity, complete bundle, one behavior change.
- Remaining 2.7B budget is not continuation authority.

## Post-EXP-W1 route-pivot decision

- Authoritative decision: `NO_CANDIDATE_PREREGISTRATION_AUTHORIZED_INCONCLUSIVE_NO_LAUNCH`.
- Decision artifact SHA256: `af9c2f9cefa6a5bbfd66e4bdeed6769a5c93a7650a3d6499456be8935451cc67`.
- Completion audit 10/10, pending0/failed0, SHA256 ced73c6fac60914537c5b858a3208a5b6c1c809d2649852c8d47ca8396f50c53.
- Research reviewer was repaired to validate terminal EXP-W1 and prevent historical VALUE-AUDIT from reopening it; incomplete schema-only cross-play now fails closed.
- Validation: reviewer 11/11 PASS; combined researcher suite 18/18 PASS.
- W1 reopen denied; W2 lacks a compatible full-200bb v55 asset; action-specific tuning lacks validated action regret; cycle route lacks a complete common-deal matrix.
- Isolated EXP-006A did not pass its frozen historical selection threshold. EXP-007 remains a plausible upstream hypothesis but lacks a preregistered pool-selection measurement, immutable current baseline/window, and exact permission artifact.
- No behavior preregistration, trainer, generic cadence, promotion, formal, or Slumbot launch is authorized.
- All V5 Python trainer/watcher processes remain stopped; Tier-2 remains frozen.

## Next permitted direction

- Reporting-only design of a frozen common-deal pool-selection measurement that compares loss-kbest ranking with audited competitive ranking.
- The design must freeze snapshot identities, pair count, both-seat common deals, CI/multiplicity, runtime budget, abort and terminal rules.
- This is measurement design only. It is not EXP-007 registration and carries `NO_LAUNCH` authority.

## Authorization

- User blanket-authorized routine in-goal work without conversational approval questions.
- Platform security approvals, immutable evidence gates, spending, secrets, destructive and out-of-scope operations remain constrained.

## Official strength

- L0: 20,400 greedy-direct hands, -153.2999 bb/100, 95% CI [-187.6945, -118.9052].

