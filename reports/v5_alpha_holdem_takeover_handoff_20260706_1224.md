# AlphaHoldem V5 Takeover Handoff - 2026-07-06 12:24 EDT

Scope: AlphaHoldem V5-from-zero Slumbot track in `C:\Users\a8594\CardPilot`.

## Update - 2026-07-07 01:24 EDT

This update supersedes the 00:36 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 01:24 EDT check.
- latest completed gate: `gate_10800`, PASS, checkpoint iter/hands `10800` / `177,210,246`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest queue/health refresh after gate 10800: live iter/hands about `10808` / `177,341,421`; checkpoint iter/hands `10800` / `177,210,246`; health `PASS`; refreshed queue effective h/s `727.20`; latest health-row h/s about `593.0`.
- latest post-gate review: `v5_post_gate_review_10800.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; preflop probe `WARN` with `5` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter10800_200h.json`; latest checkpoint rows were call-station `+172.16 bb/100` and aggressive `-385.00 bb/100`; latest was best in the call-station scripted trend but not aggressive. This remains 200-hand internal fixed-opponent smoke evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail regression shape: warning count changed `+1`; mean greedy preflop call rose by about `+0.017`; mean greedy preflop raise fell by about `-0.493`; warnings now include SB-open overfold plus BB facing-open overfold/call-suppression cases.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10900`; internal strength watch next target is `11000`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `22,789,754` checkpoint hands remaining at the status refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-07 00:36 EDT

This update supersedes the 23:55 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 00:36 EDT check.
- latest completed gate: `gate_10700`, PASS, checkpoint iter/hands `10700` / `175,569,563`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest queue/health refresh after gate 10700: live iter/hands about `10703` / `175,618,735`; checkpoint iter/hands `10700` / `175,569,563`; health `PASS`; refreshed queue effective h/s `771.68`; latest health-row h/s about `637.0`.
- latest post-gate review: `v5_post_gate_review_10700.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `4` warnings; internal probe `NOT_SCHEDULED`.
- latest internal probe remains `internal_strength_probe_iter10600_200h.json`; latest checkpoint rows were call-station `-3.81 bb/100` and aggressive `+258.50 bb/100`; latest was not best in either scripted-opponent trend. This remains 200-hand internal fixed-opponent smoke evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail mixed shape: warning count changed `0`; mean greedy preflop call fell by about `-0.002`; mean greedy preflop raise fell by about `-0.089`; all four warnings remain argmax-suppressed calls in SB-open, BB-vs-open, and SB-vs-3bet cases despite mean call probabilities around `0.239-0.296` and greedy call rates around `0.000-0.001`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10800`; internal strength watch next target is `10800`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `24,430,437` checkpoint hands remaining at the status refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 23:55 EDT

This update supersedes the 23:10 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 23:55 EDT check.
- latest completed gate: `gate_10600`, PASS, checkpoint iter/hands `10600` / `173,928,939`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest queue/health refresh after gate 10600: live iter/hands about `10608` / `174,060,215`; checkpoint iter/hands `10600` / `173,928,939`; health `PASS`; refreshed queue effective h/s `737.20`; latest health-row h/s about `1330.0`.
- latest post-gate review: `v5_post_gate_review_10600.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `4` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter10600_200h.json`; latest checkpoint rows were call-station `-3.81 bb/100` and aggressive `+258.50 bb/100`; latest was not best in either scripted-opponent trend. This remains 200-hand internal fixed-opponent smoke evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail mixed shape: warning count changed `0`; mean greedy preflop call rose by about `+0.002`; mean greedy preflop raise rose by about `+0.282`; all four warnings remain argmax-suppressed calls in SB-open, BB-vs-open, and SB-vs-3bet cases despite mean call probabilities around `0.197-0.290` and greedy call rates around `0.001-0.005`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10700`; internal strength watch next target is `10800`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `26,071,061` checkpoint hands remaining at the status refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 23:10 EDT

This update supersedes the 22:27 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 23:10 EDT check.
- latest completed gate: `gate_10500`, PASS, checkpoint iter/hands `10500` / `172,288,037`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest queue/health refresh after gate 10500: live iter/hands about `10505` / `172,370,077`; checkpoint iter/hands `10500` / `172,288,037`; health `PASS`; refreshed queue effective h/s `773.42`; latest health-row h/s about `661.0`.
- latest post-gate review: `v5_post_gate_review_10500.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `4` warnings; internal probe `NOT_SCHEDULED`.
- latest internal probe remains `internal_strength_probe_iter10400_200h.json`; latest checkpoint rows were call-station `+15.57 bb/100 +/-92.71` and aggressive `+203.75 bb/100 +/-1057.89`. This remains 200-hand internal fixed-opponent smoke evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail mixed shape: warning count changed `0`; mean greedy preflop call moved by about `-0.000`; mean greedy preflop raise rose by about `+0.050`; all four warnings remain argmax-suppressed calls in SB-open, BB-vs-open, and SB-vs-3bet cases despite mean call probabilities around `0.168-0.223`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10600`; internal strength watch next target is `10600`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `27,711,963` checkpoint hands remaining at the status refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 22:27 EDT

This update supersedes the 21:40 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 22:27 EDT check.
- latest completed gate: `gate_10400`, PASS, checkpoint iter/hands `10400` / `170,647,317`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 10400: live iter/hands about `10406` / `170,745,772`; checkpoint iter/hands `10400` / `170,647,317`; health `PASS`; refreshed queue effective h/s `753.18`; latest health-row h/s about `660.0`.
- latest post-gate review: `v5_post_gate_review_10400.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; preflop probe `WARN` with `4` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter10400_200h.json`; latest checkpoint rows were call-station `+15.57 bb/100 +/-92.71` and aggressive `+203.75 bb/100 +/-1057.89`. This remains 200-hand internal fixed-opponent smoke evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail regression shape: warning count changed `2 -> 4`; mean greedy preflop call fell by about `-0.391`; mean greedy preflop raise rose by about `+0.390`; all four warnings are argmax-suppressed calls in SB-open, BB-vs-open, and SB-vs-3bet cases despite mean call probabilities around `0.247-0.273`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10500`; internal strength watch next target is `10600`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `29,352,683` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 21:40 EDT

This update supersedes the 20:59 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 21:40 EDT check.
- latest completed gate: `gate_10300`, PASS, checkpoint iter/hands `10300` / `169,006,639`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 10300: live iter/hands about `10302` / `169,039,459`; checkpoint iter/hands `10300` / `169,006,639`; health `PASS`; refreshed queue effective h/s `794.30`; latest health-row h/s about `1301.0`.
- latest post-gate review: `v5_post_gate_review_10300.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `2` warnings; internal probe `NOT_SCHEDULED` for 10300.
- latest internal probe remains `internal_strength_probe_iter10200_200h.json`; latest checkpoint rows were call-station `-77.01 bb/100 +/-91.82` and aggressive `-980.50 bb/100 +/-1120.59`; latest was not best in either scripted-opponent trend. This remains 200-hand internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail mixed shape: warning count changed `5 -> 2`; mean greedy preflop call rose by about `+0.391`; mean greedy preflop raise fell by about `-0.271`; remaining warnings are SB-open greedy overfold `0.469` and underraise `0.110`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10400`; internal strength watch next target is `10400`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `30,993,361` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 20:59 EDT

This update supersedes the 20:13 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 20:59 EDT check.
- latest completed gate: `gate_10200`, PASS, checkpoint iter/hands `10200` / `167,365,451`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 10200: live iter/hands about `10208` / `167,496,797`; checkpoint iter/hands `10200` / `167,365,451`; health `PASS`; refreshed queue effective h/s `741.38`; latest health-row h/s about `1021.0`.
- latest post-gate review: `v5_post_gate_review_10200.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; preflop probe `WARN` with `5` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter10200_200h.json`; latest checkpoint rows were call-station `-77.01 bb/100 +/-91.82` and aggressive `-980.50 bb/100 +/-1120.59`; latest was not best in either scripted-opponent trend. This remains 200-hand internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail regression shape: warning count changed `0 -> 5`; mean greedy preflop call fell by about `-0.059`; mean greedy preflop raise fell by about `-0.230`; warnings are SB open argmax-suppressed call plus overfold, and argmax-suppressed calls in BB-vs-open and SB-vs-3bet cases.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10300`; internal strength watch next target is `10400`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `32,634,549` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 20:13 EDT

This update supersedes the 19:29 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted; watcher PIDs `9340`, `50348`, `54716`, `30276`, and `41668` were alive at the 20:13 EDT check.
- latest completed gate: `gate_10100`, PASS, checkpoint iter/hands `10100` / `165,724,572`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 10100: live iter/hands about `10104` / `165,790,185`; checkpoint iter/hands `10100` / `165,724,572`; health `PASS`; refreshed queue effective h/s `746.52`; latest health-row h/s about `1121.0`.
- latest post-gate review: `v5_post_gate_review_10100.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`; preflop probe `PASS` with `0` warnings; internal probe `NOT_SCHEDULED` for 10100.
- latest internal probe remains `internal_strength_probe_iter10000_200h.json`, verdict `REGRESSION_RISK_INTERNAL`; delta mean/lower versus 9800 internal `-305.255` / `-200.843 bb/100`. This remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail improvement shape: warning count changed `4 -> 0`; mean greedy preflop call rose by about `+0.059`; mean greedy raise fell by about `-0.012`; Slumbot strength remains unproven.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10200`; next scheduled internal probe is `10200`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `34,275,428` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 19:29 EDT

This update supersedes the 18:43 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_10000`, PASS, checkpoint iter/hands `10000` / `164,083,868`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 10000: live iter/hands about `10004` / `164,149,527`; checkpoint iter/hands `10000` / `164,083,868`; health `PASS`; refreshed queue effective h/s `707.24`; latest health-row h/s about `522.0`.
- latest post-gate review: `v5_post_gate_review_10000.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; preflop probe `WARN` with `4` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter10000_200h.json`, verdict `REGRESSION_RISK_INTERNAL`; latest rows were call-station `-65.75 bb/100 +/-295.97` and aggressive `+585.50 bb/100 +/-1055.17`; delta mean/lower versus 9800 internal `-305.255` / `-200.843 bb/100`. This remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail regression shape: warning count increased `1 -> 4`; mean greedy preflop call fell by about `-0.659`; mean greedy raise rose by about `+0.412`; all four probe cases warn that greedy argmax suppresses call despite mean call probability around `0.265-0.297`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10100`; next scheduled internal probe is `10200`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `35,916,132` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 18:43 EDT

This update supersedes the 17:59 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9900`, PASS, checkpoint iter/hands `9900` / `162,443,070`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 9900: live iter/hands about `9904` / `162,508,744`; checkpoint iter/hands `9900` / `162,443,070`; health `PASS`; refreshed queue effective h/s `716.46`; latest health-row h/s about `633.0`.
- latest post-gate review: `v5_post_gate_review_9900.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `1` warning; internal probe `NOT_SCHEDULED` for 9900.
- latest internal probe remains `internal_strength_probe_iter9800_200h.json`, verdict `REGRESSION_RISK_INTERNAL`; latest rows were call-station `+40.01 bb/100 +/-151.04` and aggressive `+1090.25 bb/100 +/-1408.93`; delta mean/lower versus 9600 internal `+306.723` / `-156.638 bb/100`. This remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail shape at 9900 is mixed, not a strength claim: warning count improved `4 -> 1`, mean greedy preflop call rose by about `+0.657`, mean greedy raise fell by about `-0.617`; the remaining warning is SB open overlimp, greedy SB limp/call rate `0.686`.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_10000`; next scheduled internal probe is `10000`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `37,556,930` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 17:59 EDT

This update supersedes the 17:15 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9800`, PASS, checkpoint iter/hands `9800` / `160,801,918`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/queue refresh after gate 9800: live iter/hands about `9805` / `160,884,009`; dashboard health is `WARN` due preflop all-in frequency, but `v5_health_warning_diagnosis.json` is `HEALTH_WARN_TRANSIENT_OR_LOCAL`; latest health-row h/s about `575.0`, refreshed queue/cadence effective h/s `721.04`.
- latest post-gate review: `v5_post_gate_review_9800.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; preflop probe `WARN` with `4` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter9800_200h.json`, verdict `REGRESSION_RISK_INTERNAL`; latest rows were call-station `+40.01 bb/100 +/-151.04` and aggressive `+1090.25 bb/100 +/-1408.93`; delta mean/lower versus 9600 internal `+306.723` / `-156.638 bb/100`. This remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- local guardrail regression shape: warning count increased `0 -> 4`; mean greedy preflop call fell by about `-0.109`; mean greedy raise rose by about `+0.177`; argmax suppresses call in SB-open, BB-vs-min-open, BB-vs-3bb-open, and SB-vs-3bet probe cases.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_9900` while tracking `health_warning_diagnosis`; next internal probe is `10000`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `39,198,082` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 17:15 EDT

This update supersedes the 16:29 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9700`, PASS, checkpoint iter/hands `9700` / `159,161,397`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` remain covered by the gate sequence.
- latest dashboard/trend refresh after gate 9700: live iter/hands about `9707` / `159,276,241`, health `PASS`, latest health-row h/s about `654.0`; the refreshed cadence/queue snapshot from live iter `9704` reports effective h/s `792.34`.
- latest post-gate review: `v5_post_gate_review_9700.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `3` warnings; internal probe `NOT_SCHEDULED` for 9700. That review's embedded `next_action` text still says `gate_9700`, but the refreshed authoritative `v5_next_action_queue.json` says `Wait for gate_9800`.
- latest internal probe remains `internal_strength_probe_iter9600_200h.json`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower versus 9400 internal `-588.818` / `-162.363 bb/100`, mean latest `+258.407 bb/100`, lower bound `-58.218`; this remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_9800` and `internal_probe_9800`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `40,838,603` checkpoint hands remaining at the cadence refresh. Promotion20k/formal100k remain waiting on `250,000,000` checkpoint hands.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 16:29 EDT

This update supersedes the 15:44 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9600`, PASS, checkpoint iter/hands `9600` / `157,520,998`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` all passed.
- latest dashboard/trend refresh after gate 9600: live iter/hands about `9604` / `157,586,602`, health `PASS`, effective h/s about `796.36`.
- latest post-gate review: `v5_post_gate_review_9600.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `3` warnings; internal probe `COMPLETED`.
- latest internal probe: `internal_strength_probe_iter9600_200h.json`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower versus 9400 internal `-588.818` / `-162.363 bb/100`, mean latest `+258.407 bb/100`, lower bound `-58.218`; this remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_9700`; next internal probe is `9800`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `42,479,002` checkpoint hands remaining at the refresh.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 15:44 EDT

This update supersedes the 14:59 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9500`, PASS, checkpoint iter/hands `9500` / `155,880,147`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` all remain covered by the gate sequence.
- latest dashboard/trend refresh after gate 9500: live iter/hands about `9503` / `155,929,403`, health `PASS`, effective h/s about `716.28`.
- latest post-gate review: `v5_post_gate_review_9500.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED` with warning count `2 -> 5`; preflop probe `WARN` with `5` warnings; internal probe is `NOT_SCHEDULED` for 9500.
- latest internal probe remains `internal_strength_probe_iter9400_200h.json`, verdict `LATEST_BEST_INTERNAL`, delta mean/lower versus 9200 internal `+1117.770` / `+1093.981 bb/100`, mean latest `+847.225 bb/100`, lower bound `+104.145`; this remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_9600` and `internal_probe_9600`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000` with `44,119,853` checkpoint hands remaining at the refresh.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 14:59 EDT

This update supersedes the 14:38 gate/waiting fields while keeping the 150M Slumbot incident details below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9400`, PASS, checkpoint iter/hands `9400` / `154,239,468`; fresh-from-zero lineage, env `v55`, obs `v55`, action space `9slot_v5`, actual hand accounting, opponent assignment `per-iteration`, and pool strategy `loss-kbest` all passed.
- latest dashboard/trend refresh after gate 9400: live iter/hands about `9405` / `154,321,517`, health `PASS`, recent h/s about `667.66`.
- latest post-gate review: `v5_post_gate_review_9400.json`, overall `REVIEW_REQUIRED_NO_AUTO_RESTART`; checkpoint delta `LOCAL_GUARDRAILS_MIXED`; preflop probe `WARN` with `2` warnings.
- latest internal probe: `internal_strength_probe_iter9400_200h.json`, verdict `LATEST_BEST_INTERNAL`, delta mean/lower versus 9200 internal `+1117.770` / `+1093.981 bb/100`, mean latest `+847.225 bb/100`, lower bound `+104.145`; this remains internal fixed-opponent evidence only and cannot support Slumbot/V4/L5/L6 claims.
- latest official greedy Slumbot evidence remains 150M quick5k direct4: `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`.
- next action queue after refresh: wait for `gate_9500`; next internal probe is `9600`; next external Slumbot cadence target is `quick5k_200M`, waiting on checkpoint hands >= `200,000,000`.
- EXP-002 remains registered only. Do not launch a batched multi-env rollout cutover until the documented gate-boundary lifecycle, offline validation, and one-change window rules are satisfied.

## Update - 2026-07-06 14:38 EDT

This markdown handoff has a newer status than the original 12:24 snapshot below.

- trainer PID `56876` is still the live trainer and was not restarted.
- latest completed gate: `gate_9300`, PASS, checkpoint iter/hands `9300` / `152,598,633`.
- latest dashboard/trend refresh after 150M Slumbot: live iter/hands about `9361` / `153,599,616`, health `PASS`, effective h/s about `560`.
- latest official greedy Slumbot evidence: 150M quick5k direct4, `5,000` hands, `-94.900 bb/100`, 95% CI `[-124.555, -65.246]`, evidence class `quick_screen`, L0.
- artifact status for 150M direct4: CI summary, promotion gate, dump analysis, loss report JSON/MD, selector replay, artifact audit JSON/MD, and hand review JSON/MD exist; artifact audit `PASS`, hand review `PASS`, promotion gate `FAIL`, selector replay clean `True`.
- 150M loss shape: SB/BB `-95.678` / `-94.123`; hero_fold/showdown `-230.719` / `-26.692`; SB open fold/call/raise/all-in `0.0076` / `0.9780` / `0.0144` / `0.0000`; BB vs open call/raise `0.8025` / `0.1161`.
- interpretation: latest Slumbot point estimate is down from 100M (`-85.037` to `-94.900`), but quick5k deltas under about `60 bb/100` remain too noisy to justify a training change by themselves. No stronger-than-V4, L5, or L6 claim is allowed.
- incident note: the wrapper-launched `quick5k_150M` and `rerun1` stalled in Slumbot HTTPS connect with zero hand rows; the completed evidence is the direct4 replacement. Details are in `reports/v5_slumbot_150M_eval_incident_20260706.md`.
- current next action: wait for `gate_9400` and `internal_probe_9400`, then refresh/read `v5_post_gate_review_9400.json/md`. The next external Slumbot cadence target is `quick5k_200M`; promotion20k/formal100k remain waiting for later gates.

## Active Run

- run_id: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- run_dir: `models\alpha_holdem_v5_from_zero\v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- trainer PID: `56876`, responding at last check; it was not stopped or restarted.
- latest dashboard snapshot checked at `2026-07-06T16:23:42Z`: checkpoint iter/hands `9100` / `149,316,834`; live iter/hands `9107` / `149,431,640`; health `PASS`; recommendation `Wait for gate_9200`.
- latest queue snapshot checked at `2026-07-06T16:23:42Z`: first action `gate_9200`, status `WAITING`; `internal_probe_9200` is also waiting; `quick5k_150M` is waiting on checkpoint hands >= `150,000,000`.

## EXP-001 Status

EXP-001 mirrored-deal internal eval is adopted. It remains an internal-only measuring stick and cannot support Slumbot/L5/L6 strength claims.

Artifacts:

- `scripts\alpha_holdem\v5_mirror_eval.py`
- `<run_dir>\v5_mirror_eval_exp001_500p.json/md`
- `<run_dir>\v5_mirror_eval_exp001_10kp.json/md`
- `<run_dir>\v5_mirror_eval_exp001_priorv5_25kp.json/md`

Adopted gate evidence:

- active 9000 vs V4 final: `-92.02 bb/100 +/-13.31`, `10,000` mirrored pairs
- active 9000 vs prior V5 59M: `+27.98 bb/100 +/-18.61`, `25,000` mirrored pairs

Use this as the primary cheap signal for later experiment gates. It is not official Slumbot evidence.

## EXP-002 Status

EXP-002 batched multi-env rollout is formally registered in `reports\v5_experiment_ledger.md`; launch is pending.

- baseline gate: `9100`, checkpoint hands `149,316,834`
- baseline health: `PASS`
- baseline trainer config: workers `22`, hands_per_iter `16384`, opponent_assignment `per-iteration`, pool_strategy `loss-kbest`, fresh_from_zero `true`
- throughput audit baseline: tail_60 effective h/s `596.8`, tail_240 effective h/s `455.0`, mean inference batch size `12.15`, collect mean `25.11s`, PPO mean `3.60s`, GPU utilization `14%`
- planned suffix: `_exp002_multienv_r1`
- gate: offline validation first, then controlled gate-boundary cutover only; `v5_throughput_compare.py` must show h/s ratio >= `2.0` and candidate mean inf_bs >= `300`, followed by 3 post-cutover health PASS gates and no semantic/accounting drift
- read-only implementation note: `reports\v5_exp002_multienv_design_20260706.md`
- current status: no EXP-002 trainer code has been landed or launched in the live run

## Official Slumbot

- latest official greedy Slumbot evidence: 100M quick5k, `5,000` hands, `-85.037 bb/100`, 95% CI `[-129.224, -40.851]`, evidence class `quick_screen`, L0.
- trend remains `SLUMBOT_POINT_ESTIMATE_DOWN`; no stronger-than-V4, L5, or L6 claim is allowed.
- latest loss shape: SB/BB `-115.046` / `-55.028`; hero_fold/showdown `-167.737` / `-10.629`; top preflop loss buckets `sb_open_c`, `bb_vs_open_lt2.5bb_f`, `sb_open_raise_lt2.5bb`.
- analysis coverage: `WARN_HISTORICAL_INCOMPLETE`, complete/total `6/7`; only 50M remains incomplete due missing decision dumps.

## Latest Gate/Post-Gate

- latest completed gate: `gate_9100`, PASS, checkpoint iter/hands `9100` / `149,316,834`.
- latest completed post-gate review: `v5_post_gate_review_9100.json`, `REVIEW_REQUIRED_NO_AUTO_RESTART`.
- checkpoint delta: `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`.
- internal probe at 9100: `NOT_SCHEDULED`; latest internal remains 9000 `REGRESSION_RISK_INTERNAL`, delta mean/lower `-82.500` / `-107.725`.
- preflop probe: `PASS`, warning_count `0`.

## Next Action

Wait for `gate_9200` and `internal_probe_9200`, then refresh/read `v5_post_gate_review_9200.json/md`. If checkpoint hands are >= `150,000,000`, allow the `quick5k_150M` Slumbot cadence job and require the full hand-log/loss-review/artifact bundle before interpreting the score. Do not launch EXP-002 cutover until the documented gate-boundary lifecycle allows it.
