# V5 Current Goal

Checked: `2026-07-11T06:40:36.1271080+00:00`

## Immutable objective

- AlphaHoldem V5-from-zero, full 200bb HUNL, official greedy-direct Slumbot.
- L5: 100k+ official hands, bb/100 > 0, 95% CI lower > 0. L6 additionally near +11.1 bb/100.
- EXP-002 retained; EXP-003 terminally INCONCLUSIVE; EXP-004 priors fixed 0.01/0.02.
- Ledger append-only, fail-closed, exact checkpoint identity, complete bundle, one behavior change.
- Remaining 2.7B budget is not continuation authority.

## Authoritative current state

- Historical EXP-005 pilot: ``EXPLORATORY_PILOT_NO_METHOD_JUDGMENT``.
- EXP005-C: ``EXP005C_FAIL_PROTOCOL_ABORT``.
- Design lock SHA256: ``2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007``.
- First60 effective h/s: control ``2658.731142``; treatment ``1101.197545``; ratio ``0.4141816098 < 0.85``.
- Failure artifact: ``reports/v5_exp005c_protocol_abort_failure_20260711.json`` SHA ``b10e61e06dd5b25d17c375250ac46d8cf955a709b0ba6f459f1c854610810026``.
- Treatment after row60: ``POST_PROTOCOL_EXPLORATORY_ONLY``.
- Incorrect primary stopped at 7,083 partial pairs; no method authority.
- MEAS-001, promotion20k, formal100k forbidden. Tier-2 frozen.
- All generic cadence/downstream launch paths terminal blocked; heartbeat paused.

## Route pivot

- W1 is candidate only because VALUE-AUDIT supports critic/reward-scale concerns; no registration or launch authorization.
- W2 is ineligible: ASSET-AUDIT found no compatible full-200bb asset.
- Next: fix researcher evidence verifier, then review whether W1 alone merits preregistration. Never auto-launch or bundle routes.

## Official strength

- L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].
