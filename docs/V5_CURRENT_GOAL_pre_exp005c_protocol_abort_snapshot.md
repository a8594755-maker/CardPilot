# AlphaHoldem V5 Current Goal

## Goal

Work on the AlphaHoldem V5-from-zero Slumbot track in
`C:\Users\a8594\CardPilot`.

Final target: L6, approximately `+11.1 bb/100` versus Slumbot. A valid L5 win
claim requires at least `100,000` official greedy-direct Slumbot hands,
`bb/100 > 0`, and a 95% CI lower bound `> 0`. No weaker signal supports a
strength claim.

Current operational objective: treat the active EXP-005 continuation as
`EXPLORATORY_PILOT_NO_METHOD_JUDGMENT`. PID `30224` may run unchanged to the
existing endpoint at or above `535,989,661` hands for execution, provenance,
and descriptive stability data only. The pilot cannot produce EXP-005
PASS/FAIL, launch MEAS-001, promotion20k, or formal100k, or support V4/L5/L6
inference. Before that endpoint, lock EXP005-C: a clean gate31400 same-start
control (`per-iteration`) and treatment (`per-group/5`), each with a fixed 20M
actual-hand budget and identical optimizer/pool/seed/deal-stream/other flags.
Its primary method evidence is a pre-registered 100k common-deal paired
treatment-endpoint versus control-endpoint difference. EXP-003 remains
terminally `INCONCLUSIVE` and must not be reopened.
Formal100k must use the exact checkpoint that passed that target's promotion20k
gate; another checkpoint's strong gate is never transferable. Official direct
sessions must fail closed unless `BelowNormal` priority is applied.

## Governing documents

Read in this order before acting:

1. `AGENTS.md` - canonical V5 contract and current handoff pointer.
2. `docs/V5_TRAINING_PLAYBOOK.md` - lifecycle, gates, signal limits, and Ops log.
3. `docs/V5_POKER_RESEARCHER_DECISION_CONTRACT.md` - mandatory separation of
   loss localization, association, counterfactual action regret, same-start
   method effects, cross-play cycles, seed scope, and formal strength.
4. `reports/v5_training_method_audit_20260706.md` - audited problems and verified-correct behavior.
5. `reports/v5_method_improvement_roadmap.md` - ranked experiments and do-not-do list.
6. `reports/v5_experiment_ledger.md` - read the append-only Ops tail from `2026-07-07 14:40` through EOF.
7. Before each action, refresh the active run's manifest, health, dashboard,
   queue, latest gate/review, and Slumbot evidence. Live artifacts override
   this snapshot.

## Operational state machine

This section is intentionally written without a hard-coded "wait for gate N" command.
The mutable snapshot below reports the current N; the transition rules decide what to do
when that number becomes stale.

1. `EXP005_PILOT_RUNNING`: preserve candidate PID/flags through the existing
   endpoint and collect only execution/provenance/descriptive stability data.
   All method judgment, MEAS-001, Slumbot evaluation, and strength inference are
   machine-blocked for this run.
2. `EXP005C_DESIGN_LOCK`: before pilot endpoint, create an immutable lock binding
   the unique gate31400 checkpoint SHA, same-start control/treatment flags, 20M
   actual-hand budgets, optimizer/pool/seed/deal stream, numerical CI/gates,
   abort/rollback, provenance schema, test results, and ledger prefix SHA.
3. `EXP005C_CLEAN_ARMS`: after the pilot stops, launch control and treatment as
   isolated runs from the same gate31400 checkpoint. A cutover without a valid
   pre-existing design lock and ledger binding must fail closed.
4. `EXP005C_PRIMARY_100K`: freeze each first eligible endpoint and run exactly
   100k common-deal paired evidence comparing treatment endpoint to control
   endpoint. The 200-hand probe is smoke-only. No adaptive extension, second
   seed, later checkpoint, or gate30700 substitution.
5. `EXP005C_PROGRAM_STOP`: FAIL or INCONCLUSIVE freezes all Tier-2 from-zero
   tuning; 2.7B is not a reason to continue. PASS alone allows exact-treatment-
   endpoint promotion20k.
6. `PROMOTION_STOP`: promotion must include a relative-to-V4 difference CI;
   a point estimate above `-71.4` is insufficient. Strong same-checkpoint
   promotion allows formal100k; non-strong freezes Tier-2 and starts a route
   pivot review.
7. `ROUTE_PIVOT`: VALUE-AUDIT-001 may authorize only EXP-W1; ASSET-AUDIT-001
   may authorize only EXP-W2. Select at most one. Never bundle reward
   normalization, value warmup, BC initialization, and CFR teacher.

Operational self-correction rules:

- Preserve user intent, but replace stale mutable facts with exact live state.
- Resolve same-tier identity conflicts fail-closed; never reuse another checkpoint's
  quality, probe, promotion, or formal result.
- Reporting/control-plane repairs are allowed when trainer behavior is unchanged, tests
  pass, original artifacts are preserved, and the Ops log receives an append-only
  correction/censure.
- New evidence may re-rank a candidate before registration. It may not change a launched
  experiment's sample size, seed, threshold, deadline, or meaning.
- Local diagnostics generate hypotheses and mechanism checks. Only the registered gate
  authorizes a behavior decision, and only formal official evidence authorizes strength.
- Before selecting a future behavior change, run the reporting-only poker research
  review. Realized terminal/line/hole losses cannot authorize action-specific tuning;
  a temporal-cycle claim needs a complete common-deal cross-play matrix; a one-seed
  method result is conditional rather than a general method claim.

## Current state

Snapshot: `2026-07-10 16:10 EDT`; refresh before acting.

Authoritative current overlay (later gate chronology is retained as history):

- Active run:
  `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710`.
- The active EXP-005 continuation is classified only as
  `EXPLORATORY_PILOT_NO_METHOD_JUDGMENT`. It cut over at `14:29 EDT` from frozen gate31400 /
  `515,989,661` hands, SHA256
  `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`.
  Old trainer PID `48476` stopped; candidate PID `30224` is alive.
- Manifest identity is `per-group`, `opponent_groups=5`; EXP-002 multi-env,
  EXP-003 mirror/bounded-K, EXP-004 priors `0.01/0.02`, optimizer, pool, PPO,
  env/obs/action versions, and from-zero lineage are unchanged.
- Health is `PASS`, trainer stderr is empty, and the initial stabilized collect
  rate is approximately `3.3k-4.1k h/s`. This is startup/operational evidence,
  not the fixed-window throughput judgment.
- Canonical watcher rearm survival is `PASS` with exact gate/internal coverage
  `31800..32700`. Eight required watchers include exact-endpoint stop watcher
  PID `51300`, pending for gate32700 / `535,989,661`. EXP-003, MEAS-001,
  promotion20k, and formal100k are blocked for the pilot.
- Fixed endpoint: exact gate32700 with at least `535,989,661` hands. The stop
  watcher fails closed on PID, command, manifest, gate, checkpoint, and hand
  identity. MEAS-001 and official promotion have not launched.
- The authoritative immutable EXP005-C design lock is v2:
  `reports/v5_exp005c_design_lock_v2_20260710.json`, SHA256
  `2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007`.
  Its complete control-arm dry-run preflight passed. No clean arm has launched;
  both wait for the pilot to stop.
- `VALUE-AUDIT-001` supports a critic/reward-scale problem (explained variance
  `-0.1240`, calibration slope `0.2742`, RMSE/target-SD `1.0609`) but makes W1
  eligible only at an actual route pivot, not now.
- `ASSET-AUDIT-001` found no compatible complete-game 200bb v55 / `9slot_v5`
  / Slumbot-ready asset. W2 is ineligible.
- The remaining non-Slumbot chain is armed fail-closed: pilot stop PID `8080`,
  transient-read supervisor PID `35928`, control launch PID `56172`, control
  endpoint freeze PID `42484`, treatment launch PID `50452`, treatment endpoint
  freeze PID `26560`, exactly-100k primary PID `28280`, and promotion/formal
  program PID `21528`. Each downstream
  watcher is `PENDING` and cannot advance without the prior exact PASS/hash.
  Full V5 regression is `195/195`; canonical rearm contract is `14/14`.
- Machine-readable completion audit:
  `reports/v5_exp005c_goal_completion_audit.json/md` is currently
  `IN_PROGRESS`, `5` pending, `0` failed. It must reach `COMPLETE` before the
  persistent goal may be marked achieved.
  Reporting-only audit watcher PID `7416` refreshes this artifact and has no
  experiment-advance authority.
- First candidate gate31500 passed exactly at `517,633,535` hands with health
  PASS. Internal verdict is `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-631.375 / -630.411 bb/100`; preflop `WARN2`, checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Early local regression does not override the
  fixed 20M judgment rule.
- The original 14:47 gate31500 Ops row's EXP-003 eligibility sentence is
  append-only censured; all numeric gate fields remain valid. The Ops watcher
  now follows lineage ancestors to the terminal EXP-003 judgment. See
  `reports/v5_gate31500_ops_lineage_censure_20260710.md/json`.
- Provisional fixed-window speed diagnosis is
  `CONTINUE_SPEED_GATE_CURRENTLY_PASS`: exact baseline/candidate weighted
  effective h/s `1,457.517 / 1,499.908`, ratio `1.0291`. This is operational
  evidence only; terminal speed judgment remains at the fixed endpoint.
- Latest official result remains the audited gate30700 promotion20k: `20,400`
  greedy-direct hands, `-153.300 bb/100`, 95% CI
  `[-187.695, -118.905]`; `promotion_20k_strong=false`, so no formal100k and no
  V4/L5/L6 strength claim.

Historical pre-cutover chronology below is audit context and must not override
the authoritative overlay.

- Active run:
  `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709`.
- Trainer PID `48476` is alive and was not restarted. Latest refreshed health
  is `PASS`. Live iter/hands were approximately
  `31292 / 514,212,862`; saved checkpoint is
  `31200 / 512,698,792`.
- Recent collect-only throughput was about `4,028 h/s`; effective wall-clock
  throughput was about `1,481 h/s` (`1,529 h/s` long window). Treat these as distinct metrics;
  effective h/s governs ETA.
- A transient health monitor exit at iter `27101` was caused only by one recent
  postflop batch with call `0.030`. The rolling diagnosis found no intervention
  due, subsequent action mix recovered, and health returned to `PASS`. This was
  not a trainer restart trigger.
- Canonical watcher rearm completed with survival `PASS`; active gate/internal
  coverage is now `30700..31800`, derived from live/checkpoint high water after
  consecutive 30500/30600 quality blocks. Seven required watchers were alive after rearm, terminal EXP-003 and
  nonlaunchable legacy Slumbot watchers were correctly skipped, and trainer
  PID `48476` was untouched.
- EXP-002 is adopted and retained: multi rollout, 16 envs/worker, min
  inference slots 256, deadline 1000 us.
- EXP-004 remains at the stable global-prior floor: preflop `0.01`, postflop
  `0.02`. The `0.005` step was rolled back; zero prior is not authorized.
- EXP-003 remains active in the trainer configuration (mirrored deals plus
  deterministic bounded-K=200 all-in EV, `aiev_skip=0`) but its method
  judgment is terminally `INCONCLUSIVE`. Its frozen gate `24900` checkpoint is
  `409,058,520` hands with SHA256
  `060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020`.
- The EXP-003 fixed three-role bundle had positive point estimates, but
  `post_vs_native` CI half-width was `22.199`, above the fixed `20.0` limit.
  Do not add pairs, change seeds, rerun the bundle, or substitute a later
  checkpoint.
- MEAS-001 is implemented and validated in
  `reports/v5_prospective_measurement_design_meas001_20260710.md/json`. It
  fixes 100,000 common-deal mirrored pairs and paired causal estimands for a
  future separately registered experiment. It does not reopen EXP-003 and is
  not a trainer-change authorization. Focused tests passed `10/10`; all 14 V5
  regression scripts passed (`142` unittests plus `14` rearm checks). No
  100k-pair measurement was launched.
- Gate `27500` passed exactly at checkpoint `27500 / 451,830,746`. Its internal
  probe identity is valid with verdict `MIXED_INTERNAL`, delta mean/lower
  `+283.043 / +108.467 bb/100`; post-gate review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. The preflop probe improved from five
  warnings at 27400 to one at 27500 but remains `WARN` for SB-open overlimp.
- Gate `27600` passed exactly at checkpoint `27600 / 453,475,071`. The exact
  target probe is valid; authoritative L6 aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `-345.678 / -94.704 bb/100`. Preflop is
  `WARN` with four argmax-call-suppression warnings; review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. These are local-only signals.
- The first 02:48 Ops row for gate 27600 copied gate 27500's internal delta
  fields during a post-review/L6-aggregate refresh race. It remains byte
  preserved, but those two fields are superseded by the append-only CENSURE and
  `reports/v5_gate27600_reporting_race_censure_20260710.md/json`. Post-gate
  review now remains `PENDING_L6_AGGREGATE_IDENTITY` until aggregate iteration
  exactly matches the target. Full V5 tests pass `152/152`; rearm checks pass
  `14/14`; canonical watcher survival is `PASS` for `27700..28800`.
- Gate `27700` passed exactly at checkpoint `27700 / 455,119,923`. The new
  aggregate-identity guard was exercised successfully: aggregate target is
  exact `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-3.925 / -35.529 bb/100`. Target rows were call-station `+0.785` and
  aggressive `+193.0 bb/100`; preflop remains `WARN` with four
  argmax-call-suppression warnings. Review is
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; this is local-only evidence.
- Gate `27800` passed exactly at checkpoint `27800 / 456,766,342`. It exercised
  the full race guard: after the exact target probe completed, review stayed
  `PENDING_L6_AGGREGATE_IDENTITY` with null verdict/deltas while the aggregate
  remained at 27700; only after aggregate target 27800 `MATCH` did it complete.
  Final verdict is `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `+79.608 / -225.279 bb/100`; target rows call-station `-149.0`, aggressive
  `+502.0`; preflop is `WARN` with one SB-open overlimp warning. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence.
- Gate `27900` passed exactly at checkpoint `27900 / 458,412,500`. Aggregate
  target identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+138.500 / +460.381 bb/100`; target rows call-station `-45.75`,
  aggressive `+675.75`. The exact-checkpoint preflop probe is `PASS` with zero
  warnings and checkpoint delta is
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; this local improvement is not Slumbot
  strength evidence and does not authorize an early promotion.
- Cadence independently refreshed against checkpoint 27900 and accepted its
  exact quality gate; the 500M preview remains `BLOCKED` solely on
  `training_hands`. Launchable key is null and active launches are empty. This
  does not transfer the quality PASS to a later checkpoint: the launch-boundary
  checkpoint must pass again.
- Gate `28000` passed exactly at checkpoint `28000 / 460,057,601`, including
  snapshot checks: pool snapshots `5/5`, opponent assignment `per-iteration`,
  pool strategy `loss-kbest`. The exact target probe remained
  `PENDING_L6_AGGREGATE_IDENTITY` with null deltas until aggregate target 28000
  `MATCH`, then completed as `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `+19.875 / -186.083 bb/100`; target rows call-station `-216.0`, aggressive
  `+885.75`. Preflop is `PASS` with zero warnings; checkpoint delta is
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`; review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. Local-only evidence.
- Cadence independently refreshed at checkpoint 28000, accepted quality, and
  remained `BLOCKED` solely on `training_hands`; launchable key is null and
  active launches are empty. Quality remains checkpoint-local.
- Gate `28100` passed exactly at checkpoint `28100 / 461,703,003`. The exact
  target probe stayed `PENDING_L6_AGGREGATE_IDENTITY` with null deltas until
  aggregate target 28100 `MATCH`, then completed as `MIXED_INTERNAL`, delta
  mean/lower `+457.500 / +589.227 bb/100`; target rows call-station `+86.0`,
  aggressive `+1498.75`. Preflop is `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`; review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. Positive local diagnostics remain
  internal-only and do not authorize promotion or a strength claim.
- Cadence independently refreshed at checkpoint 28100, accepted quality, and
  remained `BLOCKED` solely on `training_hands`; no launchable key or active
  launch exists.
- Gate `28200` passed exactly at checkpoint `28200 / 463,348,302`. Aggregate
  target identity is `MATCH` and verdict `REGRESSION_RISK_INTERNAL`; the
  aggregate delta fields are genuinely unavailable and remain null rather than
  being imputed or copied. Target rows are call-station `+83.58`, aggressive
  `+564.75`. Preflop regressed to `WARN` with four argmax-call-suppression
  warnings; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`; review
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. Local-only evidence.
- Cadence independently refreshed at checkpoint 28200 and returned to two
  blockers, `training_hands` and `quality_gate`; no launchable key or active
  launch. This confirms earlier quality PASS results were not transferred.
  These are local-only signals and do not justify a trainer change.
- Gate `28300` passed exactly at checkpoint `28300 / 464,993,502`. Aggregate
  target identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+55.210 / +183.019 bb/100`; target rows are call-station
  `-58.5` and aggressive `+817.25`. Preflop remains `WARN` with four warnings:
  SB-open overlimp, SB-open underraise, and BB underraise versus both min-open
  and 3bb-open. Checkpoint delta is `LOCAL_GUARDRAILS_MIXED`; review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. These are local-only signals and do not
  offset the negative official Slumbot evidence.
- Cadence independently refreshed at checkpoint 28300 and remains blocked by
  exactly `training_hands` and `quality_gate`; launchable key is null and no
  launch is active. The 28300 quality WARN is not transferable to the future
  launch checkpoint, which must be judged from its own exact artifacts.
- Gate `28400` passed exactly at checkpoint `28400 / 466,638,377`. Aggregate
  target identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+8.780 / -152.443 bb/100`. At this snapshot boundary the current
  checkpoint entered the K-best pool as `pool_id114_466M`; its target rows are
  call-station `-122.69` and aggressive `+899.0`. Preflop remains `WARN` but
  improved from four warnings to one SB-open overlimp warning; checkpoint delta
  is `LOCAL_GUARDRAILS_MIXED`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence.
- Cadence refreshed against checkpoint 28400 and remains blocked by exactly
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active. The canonical rearm that followed passed survival for `28500..29600`
  without touching the trainer or launching Slumbot.
- Gate `28500` passed exactly at checkpoint `28500 / 468,283,337`. Aggregate
  target identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `-463.905 / -417.873 bb/100`; target rows are call-station
  `-418.75` and aggressive `+267.25`. Preflop regressed from one warning to
  four argmax call-suppression warnings; checkpoint delta is
  `LOCAL_GUARDRAILS_REGRESSED`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence that reinforces policy
  shape instability but does not authorize an intervention before 500M.
- Cadence independently refreshed at checkpoint 28500 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch. No quality result from another checkpoint is transferable.
- Gate `28600` passed exactly at checkpoint `28600 / 469,929,538`, including
  snapshot checks: pool `5/5`, opponent assignment `per-iteration`, pool
  strategy `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`;
  verdict remains `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `+783.250 / +868.739 bb/100`. Snapshot `pool_id115_469M` rows are
  call-station `+92.75` and aggressive `+1322.25`. Preflop is `WARN` with two
  SB-open overlimp/underraise warnings; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Positive local values remain internal-only and do
  not offset negative official Slumbot evidence.
- Cadence independently refreshed at checkpoint 28600 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `28700` passed exactly at checkpoint `28700 / 471,574,569`. Aggregate
  identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-363.163 / -622.659 bb/100`; target rows are call-station `-28.325` and
  aggressive `+717.0`. Preflop improved to `PASS` with zero warnings;
  checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Review
  remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence.
- Cadence independently refreshed at checkpoint 28700, accepted its exact
  quality gate, and remains blocked solely by `training_hands`; launchable key
  is null and no launch is active. This quality PASS remains non-transferable.
- Gate `28800` passed exactly at checkpoint `28800 / 473,218,725`, including
  snapshot checks: pool `5/5`, opponent assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+903.288 / +816.730 bb/100`; target rows
  are call-station `+691.25` and aggressive `+1804.0`. Preflop remains `PASS`
  with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; positive local diagnostics remain
  internal-only.
- Cadence independently refreshed at checkpoint 28800, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `28900` passed exactly at checkpoint `28900 / 474,864,258`. Aggregate
  identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-421.310 / -271.139 bb/100`; target rows are call-station `-155.37` and
  aggressive `+1808.0`. Preflop regressed from PASS to `WARN` with one SB-open
  overlimp warning; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. Review
  remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; this reversal again shows why
  checkpoint-local quality cannot be transferred.
- Cadence independently refreshed at checkpoint 28900 and returned to exact
  blockers `training_hands` and `quality_gate`; launchable key is null and no
  launch is active.
- Gate `29000` passed exactly at checkpoint/live `29000 / 476,509,985`,
  including snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`; verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `-660.250 / -389.437 bb/100`;
  snapshot `pool_id117_476M` rows are call-station `-74.87` and aggressive
  `+407.0`. Preflop remains `WARN` with one SB-open overfold warning;
  checkpoint delta `LOCAL_GUARDRAILS_MIXED`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence.
- Cadence independently refreshed at checkpoint 29000 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `29100` passed exactly at checkpoint `29100 / 478,155,874`. Aggregate
  identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-16.020 / -361.813 bb/100`; target rows are call-station `-99.66` and
  aggressive `+399.75`. Preflop improved to `PASS` with zero warnings;
  checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Review
  remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only evidence.
- Cadence independently refreshed at checkpoint 29100, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active. Quality remains checkpoint-local.
- Gate `29200` passed exactly at checkpoint `29200 / 479,800,561`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`; verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `+549.330 / +683.415 bb/100`;
  target rows are call-station `+90.25` and aggressive `+1308.5`. Preflop
  remains `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Positive local evidence remains
  internal-only.
- Cadence independently refreshed at checkpoint 29200, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29300` passed exactly at checkpoint `29300 / 481,446,177`. Aggregate
  identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-799.000 / -824.612 bb/100`; both target rows are negative: call-station
  `-113.5`, aggressive `-85.75`. Preflop regressed to `WARN` with SB-open
  overlimp and underraise warnings; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. This is a strong local regression signal but
  remains insufficient to replace the registered 500M official boundary.
- Cadence independently refreshed at checkpoint 29300 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `29400` passed exactly at checkpoint `29400 / 483,090,386`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`; verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `+1172.845 / +931.855 bb/100`.
  Target rows diverge sharply: call-station `-136.31`, aggressive `+2282.75`.
  Preflop regressed to `WARN` with four argmax call-suppression warnings;
  checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. This split diagnostic remains
  internal-only and is not a strength or intervention signal.
- Cadence independently refreshed at checkpoint 29400 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `29500` passed exactly at checkpoint `29500 / 484,734,368`. Aggregate
  identity is `MATCH`; verdict `MIXED_INTERNAL`. Aggregate delta fields are
  genuinely unavailable and remain null rather than being imputed. Divergent
  local rows are call-station `-142.92` and aggressive `+1924.50 bb/100`.
  Preflop remains `WARN` with three warnings and checkpoint delta is
  `LOCAL_GUARDRAILS_MIXED`. This is local-only evidence and does not authorize
  a trainer change.
- The original 08:27 gate29500 Ops row is append-only preserved but censured for
  a stale template sentence that called the already-completed EXP-003 bundle
  eligible. `v5_ops_log_watch.py` now binds the exact valid terminal judgment
  artifact before emitting method guidance. Its actual gate29500 reconstruction
  reports terminal `INCONCLUSIVE` and forbids reruns, extra pairs, seed changes,
  or later-checkpoint substitution. Focused tests pass `5/5`; the full V5 suite
  passes `153/153`; canonical watcher rearm survival passes for `29600..30700`;
  trainer PID `48476` remained alive and untouched.
- Cadence remains blocked on `training_hands` and the exact-checkpoint
  `quality_gate`; launchable key is null and no Slumbot launch is active.
- Gate `29600` passed exactly at checkpoint/live `29600 / 486,379,183`,
  including snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`; verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `-901.548 / -757.761 bb/100`;
  snapshot `pool_id120_486M` rows are call-station `-286.015` and aggressive
  `+264.5`. Preflop remains `WARN` with four argmax call-suppression warnings;
  checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. The repaired Ops watcher was
  live-verified on this gate: its row binds terminal EXP-003 `INCONCLUSIVE` and
  forbids rerun, extra pairs, seed changes, or later-checkpoint substitution.
- Cadence independently refreshed at checkpoint 29600 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `29700` passed exactly at checkpoint/live `29700 / 488,023,806`.
  Aggregate identity is `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+547.355 / +408.378 bb/100`; target rows are call-station `+287.945` and
  aggressive `+785.25`. Preflop improved to `PASS` with zero warnings;
  checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Review
  remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; internal-only evidence.
- Cadence independently refreshed at checkpoint 29700, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29800` passed exactly at checkpoint `29800 / 489,669,515`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+198.993 / +319.828 bb/100`; target rows
  are call-station `+64.93` and aggressive `+1406.25`. Preflop remains `PASS`
  with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Internal-only evidence.
- Cadence independently refreshed at checkpoint 29800, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29900` passed exactly at checkpoint `29900 / 491,314,339`. Aggregate
  identity is `MATCH`; verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `+25.285 / +103.177 bb/100`; target rows are call-station `+104.75` and
  aggressive `+1417.0`. Preflop regressed to `WARN` with SB-open overfold and
  BB overfold versus min-open/3bb-open; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Local-only evidence.
- Cadence independently refreshed at checkpoint 29900 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `30000` passed exactly at checkpoint `30000 / 492,958,809`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+57.960 / -220.033 bb/100`; target rows
  are call-station `-79.83` and aggressive `+1717.5`. Preflop is `WARN` with
  SB overlimp/underraise and BB overcall; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Internal-only evidence.
- Cadence independently refreshed at checkpoint 30000 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `30100` passed exactly at checkpoint `30100 / 494,603,729`. Aggregate
  identity is `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `-578.000 / -555.476 bb/100`; target rows are call-station `-239.83` and
  aggressive `+721.5`. Preflop is `WARN` with SB overlimp/underraise and BB
  overfold; checkpoint delta `LOCAL_GUARDRAILS_MIXED`. Internal-only evidence.
- Cadence independently refreshed at checkpoint 30100 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active.
- Gate `30200` passed exactly at checkpoint `30200 / 496,248,804`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+819.603 / +968.756 bb/100`; target rows
  are call-station `+0.125` and aggressive `+2120.75`. Preflop is `WARN` with
  SB overlimp/underraise; checkpoint delta `LOCAL_GUARDRAILS_MIXED`. This is
  internal-only evidence and does not prove V4, L5, or L6 strength.
- Cadence independently refreshed at checkpoint 30200 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active. Saved-checkpoint distance to 500M is `3,751,196` hands.
- Gate `30300` passed exactly at checkpoint `30300 / 497,894,785`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `-689.453 / -706.749 bb/100`;
  target rows are call-station `-149.78` and aggressive `+891.75`. Preflop is
  `WARN` with five warnings: greedy argmax suppresses calls in SB open, both BB
  facing-open cases, and SB-vs-3bet, plus BB min-open overfold. Checkpoint delta
  is `LOCAL_GUARDRAILS_REGRESSED`. Internal-only evidence.
- Cadence independently refreshed at checkpoint 30300 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active. Saved-checkpoint distance to 500M is `2,105,215` hands.
- Gate `30400` passed exactly at checkpoint `30400 / 499,539,051`, including
  snapshot checks: pool `5/5`, assignment `per-iteration`, strategy
  `loss-kbest`, version `v5.zero`. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `-682.860 / -848.656 bb/100`; target rows
  are call-station `+53.0` and aggressive `-676.75`. Preflop is `WARN` with six
  warnings: SB open overfold/overlimp/underraise, BB min-open
  overfold/underraise, and BB 3bb-open underraise. Checkpoint delta is
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only evidence.
- Cadence independently refreshed at checkpoint 30400 with exact blockers
  `training_hands` and `quality_gate`; launchable key is null and no launch is
  active. Saved-checkpoint distance to 500M is `460,949` hands. The live
  counter crossing 500M does not qualify; the first eligible saved checkpoint
  remains gate 30500.
- Gate `30500` passed exactly at checkpoint `30500 / 501,183,802`, the first
  saved checkpoint at or above 500M. Snapshot checks passed: pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`, health
  `PASS`, entropy above floor. Aggregate identity is `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+1018.900 / +1355.847 bb/100`; target rows
  are call-station `+4.30` and aggressive `+1409.75`. Preflop is `WARN` with
  four warnings: SB overlimp/underraise and BB overcall versus both min-open
  and 3bb-open. Checkpoint delta is `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30500. `training_hands` now
  passes, but `quality_gate` fails; launchable key is null, active launches are
  zero, and no 500M promotion ran. The readiness audit requires the first
  saved checkpoint at or above 500M whose exact health and quality both pass,
  so gate 30600 is the next candidate; this is not permission to bypass or
  weaken quality.
- Gate `30600` passed exactly at checkpoint `30600 / 502,828,646`. Snapshot
  checks passed: pool `5/5`, assignment `per-iteration`, strategy `loss-kbest`,
  version `v5.zero`, health `PASS`, entropy above floor. Aggregate identity is
  `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `-216.307 / -260.969 bb/100`; target rows are call-station `+415.935` and
  aggressive `+565.5`. Preflop is `WARN` with four greedy-argmax call
  suppression warnings: SB open, BB versus min-open, BB versus 3bb-open, and
  SB versus 3bet. Checkpoint delta is `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30600. `training_hands` passes
  but `quality_gate` again fails; launchable key is null, active launches are
  zero, and no promotion ran. This is the second consecutive >=500M checkpoint
  blocked honestly on exact quality. Gate 30700 is the next covered candidate.
- Gate `30700` passed exactly at checkpoint `30700 / 504,474,081`. Snapshot
  checks passed: pool `5/5`, assignment `per-iteration`, strategy `loss-kbest`,
  version `v5.zero`, health `PASS`, entropy above floor. Aggregate identity is
  `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+324.657 / +252.755 bb/100`; target rows are call-station `-50.5` and
  aggressive `+1681.25`. Preflop is `PASS` with zero warnings; checkpoint delta
  is `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Internal-only evidence.
- Cadence selected gate30700 as the first saved checkpoint >=500M whose exact
  health and quality both pass. The official greedy-direct promotion20k is now
  `RUNNING` from frozen identity `30700 / 504,474,081`, direct launch,
  `12 x 1,700 = 20,400` hands. Plan/preflight passed; exactly 12 workers were
  observed on the same frozen checkpoint at Windows BelowNormal priority.
  Read no partial score and make no strength claim until the complete bundle is
  final.
- Gate `30800` passed exactly at checkpoint `30800 / 506,119,032`. Aggregate
  identity is `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+236.110 / +218.974 bb/100`; target rows are call-station `-7.78` and
  aggressive `+2110.75`. Preflop is `WARN` with one SB-open overlimp warning;
  checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. Internal-only. This later gate
  does not alter the frozen gate30700 promotion identity.
- Gate `30900` passed exactly at checkpoint `30900 / 507,763,528`. Aggregate
  identity is `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-623.937 / -469.024 bb/100`; target rows are call-station `-111.655` and
  aggressive `+966.75`. Preflop is `WARN` with greedy-argmax call suppression
  in SB open and BB versus min-open; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only. The frozen promotion identity
  remains gate30700.
- Gate `31000` passed exactly at checkpoint `31000 / 509,408,918`. Aggregate
  identity is `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+276.202 / -2.340 bb/100`; target rows are call-station `+427.25` and
  aggressive `+980.25`. Preflop is `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Internal-only. The frozen
  promotion identity remains gate30700.
- Gate `31100` passed exactly at checkpoint `31100 / 511,054,065`. Aggregate
  identity is `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-563.335 / -137.498 bb/100`; target rows are call-station `-79.42` and
  aggressive `+360.25`. Preflop is `WARN` with greedy-call suppression in SB
  open, BB versus min/3bb open, and SB versus 3bet; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only. The frozen promotion identity
  remains gate30700.
- Gate `31200` passed exactly at checkpoint `31200 / 512,698,792`. Aggregate
  identity is `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-267.083 / -460.070 bb/100`; target rows are call-station `-512.585` and
  aggressive `+259.25`. Preflop is `WARN` with greedy-call suppression in SB
  open, BB versus min/3bb open, and SB versus 3bet; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Internal-only. The frozen promotion identity
  remains gate30700.
- The gate30700 promotion completed all 12 Slumbot parts and is now in
  `SELECTOR_REPLAY`. The replay remains bundle-finalization work; do not read or
  report the core score before selector replay, CI, promotion gate, loss
  report, artifact audit, and hand review all settle.
- The fixed pre-500M method-selection diagnostic is
  `reports/v5_method_selection_diagnostic_pre500m_20260710_v2.json`. Over 1,000
  training rows, KL median is about `0.0404`, KL `>0.03` fraction `0.902`, KL
  `>0.10` fraction `0.049`, and clipfrac mean `0.2445`; the full isolated
  EXP-006A support gate does not pass. The last 10 exact gates have preflop
  warning counts `[1,2,4,4,6,0,2,2,7,2]`, range `7`, with 2 PASS/WARN
  switches, so EXP-005 has structural support. This is prospective ranking
  only; no cutover is authorized before the 500M result and full loss review.
  The earlier same-name artifact without `_v2` is superseded because its trend
  parser left official Slumbot fields null; it must not be ingested.
- Fresh V4 current-harness baseline: 20,400 greedy hands,
  `-71.383 bb/100`, CI `[-92.222, -50.543]`.
- Latest current-line promotion20k: 20,400 greedy hands,
  `-140.151 bb/100`, CI `[-178.386, -101.916]`, complete bundle,
  `strong=false`, L0.
- Latest formal V5: 100,000 greedy hands, `-100.248 bb/100`, CI
  `[-112.407, -88.088]`, complete bundle, L0.
- The 500M promotion20k is running from exact gate30700. Do not inspect or log
  partial scores. Completion requires all hands/dumps, CI, promotion gate,
  selector replay, loss report, artifact audit, and hand review. Formal100k
  remains blocked unless this exact-checkpoint promotion returns
  `promotion_20k_strong=true`;
  the shorter cadence
  ETA derived from collect rate is not governing. Formal100k
  launches only when `promotion_20k_strong=true` and is pinned to the exact
  promoted checkpoint.
- The readiness audit is
  `reports/v5_500m_promotion_readiness_audit_20260710.md/json`, verdict
  `WAITING_BLOCKED_EXPECTED`. It hardened exact-checkpoint formal provenance
  and fail-closed BelowNormal priority. Focused tests passed `9/9`, the full V5
  suite passed `151/151`, and rearm checks passed `14/14`. No Slumbot run was
  launched and no trainer behavior changed.

## Hard rules

- The Ops log is append-only UTF-8, one row per event. Never edit historical
  rows or force an audit verdict.
- One behavior-affecting change per judgment window. EXP-003 is terminally
  `INCONCLUSIVE`; do not treat positive point estimates, local probes, or
  training health as adoption evidence.
- MEAS-001 is measurement-only. Before any behavior change, separately register
  the exact method change, hypothesis, baseline checkpoint, hand window, gates,
  abort criteria, and rollback.
- Watcher rearm uses only `scripts/alpha_holdem/v5_rearm_watchers.ps1` and must
  never replay a missed historical gate.
- Gate PASS requires filename target, declared target, and saved checkpoint
  identity to match exactly. A later checkpoint is `STALE_CHECKPOINT`, not PASS.
- A target-named internal probe must embed that same checkpoint iteration;
  mismatches are local-only quarantine artifacts.
- Official evidence is greedy-direct Slumbot with the full hand-level bundle.
  Internal probes, action mix, mirrors, and self-play reward do not prove V4,
  L5, or L6.
- Never change `hands_per_iter` as a speed-only adjustment; it changes PPO
  cadence and requires its own registered experiment.

## Execution order

1. Keep the trainer and its current EXP-002/003/004 flags unchanged. Continue
   exact gate/internal health reporting through the active `30700..31800`
   watcher range; gate `31200` is complete and gate `31300` is next. In
   parallel, monitor the gate30700 promotion bundle without reading partial
   scores. This
   canonical range covers the first eligible 500M checkpoint.
2. Treat all exact-gate internal/preflop signals as local monitoring evidence
   only. Continue the same fail-closed cadence; do not restart or tune from a
   single probe.
3. Preserve the validated MEAS-001 evaluator, source-bundle, aligned-pair,
   hash-bound manifest/result, collision, partial-bundle, and one-shot terminal
   contracts. Do not launch its fixed 100k-pair measurement until a future
   behavior experiment has been separately registered with frozen inputs.
4. Preserve EXP-003's frozen bundle and terminal judgment. MEAS-001 is the
   prospective measuring rule for a future experiment, not a remeasurement of
   EXP-003.
5. Let the duplicate-safe cadence launch official greedy-direct promotion20k
   at the first exact checkpoint with at least `500,000,000` hands only when
   health and quality gates pass. Require hands JSONL, decision dumps, CI,
   promotion gate, dump analysis, loss report, artifact audit, and hand review.
6. If `promotion_20k_strong=true`, launch formal100k on that exact promoted
   checkpoint and judge only by the L5/L6
   rules. If promotion is not strong, do not launch formal100k: compare the full
   hand review with repeated preflop/internal evidence, then separately
   pre-register exactly one next behavior experiment. The fixed pre-500M
   diagnostic currently ranks EXP-005 group opponent assignment; isolated
   EXP-006A may replace it only if the 500M-boundary diagnostic passes its full
   direct-signal gate. Never bundle them.
7. Do not launch EXP-005, EXP-006, EXP-007, prior decay, throughput sweep, or
   any other behavior change before its own complete registration and normal
   cutover authorization.
8. Keep the localized Slumbot hypothesis separate from intervention. Current
   evidence flags SB limp/under-raise shape, BB defense, and showdown/big-pot
   realization; require repeatable multi-source evidence and a registered
   context-conditioned plan, never a blanket action prior.

## Operational completion gates

This evidence phase is complete only when all applicable items below have
authoritative artifacts:

1. Exact gate/probe collection remains fail-closed through the selected 500M
   checkpoint; trainer health and stderr are reviewed at the launch boundary.
2. MEAS-001 implementation tests pass and its evaluator/manifest contract is
   frozen before any future behavior experiment uses it. `COMPLETED` on
   `2026-07-10`; no measurement was launched.
3. The 500M promotion20k either completes with the full audited hand-level
   bundle or is honestly blocked by a recorded health/quality condition.
4. The post-promotion decision is recorded: formal100k launch after a strong
   result, or one fully pre-registered next method experiment after a non-strong
   result. Neither branch by itself is a V4/L5/L6 strength claim.

## Reporting

At each valid gate boundary report run ID, checkpoint/live iter and hands,
collect-only and effective h/s, health, active experiments, EXP-003 status,
latest official Slumbot evidence, artifact completeness, and the exact next
action/gate. Append one honest Ops row per event.

## Escalate to the user only for

Breaking from-zero on the main line, a V6 observation/architecture launch,
abandoning 2.7B, two consecutive reverted Tier-1 experiments, spending money,
or authority outside the registered gate/rollback rules.
