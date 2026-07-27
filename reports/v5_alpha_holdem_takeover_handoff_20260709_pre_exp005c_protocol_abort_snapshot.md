# AlphaHoldem V5 Takeover Handoff - 2026-07-10 Refresh

Checked at `2026-07-10 16:10 EDT`. Refresh live artifacts before acting.
This section supersedes the older snapshot details retained below.

## Authoritative 16:10 overlay

- Active PID `30224` is an `EXPLORATORY_PILOT_NO_METHOD_JUDGMENT`, not an
  EXP-005 method arm. It must stop at exact gate32700 / at least `535,989,661`
  hands. Endpoint stop watcher PID `51300` is pending; canonical survival is
  PASS with eight required watchers over `31800..32700`. No MEAS-001 or Slumbot
  evaluation is authorized for the pilot.
- EXP005-C lock v2 is read-only at
  `reports/v5_exp005c_design_lock_v2_20260710.json`, SHA256
  `2d64d3b82700d5bea2250121a09567e78f46b6bcc486a55d593acb33bcb86007`.
  The complete control-arm dry run passed checkpoint/config/tool/test/ledger
  verification and contains no inline watcher launch. No clean arm has launched.
- After pilot stop: launch control `per-iteration` and treatment `per-group/5`
  separately from the same gate31400 checkpoint, each fixed 20M actual hands,
  then exactly 100k common-deal paired endpoint evidence. Pilot, gate30700, a
  200-hand probe, adaptive pairs, and later endpoints are invalid substitutes.
- Program stop: EXP005-C FAIL/INCONCLUSIVE freezes Tier-2; PASS allows only the
  exact treatment endpoint promotion20k. Relative-to-V4 CI lower bound must be
  positive; a favorable point estimate is insufficient. Nonstrong promotion
  freezes Tier-2 and enters route review.
- VALUE-AUDIT-001 supports a critic/reward-scale problem, so W1 is eligible only
  if a route pivot is later reached and W1 alone is selected. ASSET-AUDIT-001
  found no compatible full-game 200bb v55/9slot_v5/Slumbot-ready asset; W2 is
  currently ineligible. Neither audit authorizes a change now.
- Latest official evidence remains gate30700 promotion20k: `20,400`
  greedy-direct hands, `-153.2999 bb/100`, CI `[-187.6945,-118.9052]`, not
  strong. No V4/L5/L6 claim.
- Automated fail-closed non-Slumbot chain is armed: stop `8080`, transient
  supervisor `35928`, control launch/freeze `56172/42484`, treatment
  launch/freeze `50452/26560`, primary `28280`, and promotion/formal program
  `21528`. All downstream states are pending and identity/hash-gated. Promotion
  additionally requires a fresh-V4 Welch CI lower bound above zero. Full V5
  tests pass `195/195`; rearm contract
  passes `14/14`.
- A reporting-only poker research inference layer is implemented and mandatory
  for future method selection. The real 500M-versus-250M audit covers
  `20,400/20,400` hands and `12/12` source sessions, but correctly classifies
  its 16 multiplicity-controlled slice associations as localization rather
  than action regret. Current consolidated permissions block causal action,
  cycle, global non-convergence, broad-generalization, L5/L6, route-pivot, and
  new-behavior claims while EXP005-C is active. See
  `reports/v5_poker_researcher_capability_implementation_20260710.md/json`.

The older live-state fields below are audit history and do not override this overlay.

## Objective

The canonical goal is [V5_CURRENT_GOAL.md](../docs/V5_CURRENT_GOAL.md).
Target L6 remains near `+11.1 bb/100` versus Slumbot. L5 requires 100k+
official greedy-direct hands, positive bb/100, and a positive 95% CI lower
bound. Nothing weaker proves strength.

## Live state

- Run: `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710`.
- Candidate trainer PID `30224` resumed frozen gate31400 / `515,989,661`
  hands at `14:29 EDT`. Source SHA256 is
  `bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`;
  old PID `48476` stopped during the guarded cutover.
- Manifest-verified behavior change is exactly EXP-005: assignment
  `per-iteration -> per-group`, five balanced groups. EXP-002 multi-env,
  EXP-003 mirror/bounded-K flags, EXP-004 priors `0.01/0.02`, optimizer,
  pool/PPO, env/obs/action versions, and from-zero lineage are unchanged.
- Latest refresh: health `PASS`, stderr empty, live approximately
  `31445 / 516,729,346`, saved checkpoint `31400 / 515,989,661`; initial
  collect rate about `3,647 h/s`. Do not use startup rows for the fixed
  throughput judgment.
- Canonical watcher rearm survival is `PASS`, coverage `31500..32700`.
  EXP-003 freeze/bundle are explicitly skipped because its judgment is
  terminal. Promotion20k is skipped until the frozen EXP-005 20M endpoint and
  MEAS-001 judgment; formal100k is skipped until strong same-checkpoint
  promotion evidence.
- Fixed endpoint is the first exact checkpoint at or above `535,989,661`
  actual hands, expected gate32700. No early method judgment is allowed.
- Gate31500 passed exactly at `517,633,535` hands: health PASS, internal
  `REGRESSION_RISK_INTERNAL` with delta mean/lower
  `-631.375 / -630.411`, preflop `WARN2`, local guardrails regressed. This is
  early local-only evidence and does not authorize method judgment.
- The 14:47 gate31500 Ops row's stale EXP-003 eligibility sentence is censured;
  the patched watcher follows lineage-parent judgment artifacts. Focused Ops
  tests pass `6/6`, full V5 `154/154`, and canonical coverage is now
  `31600..32700` with survival PASS.
- Provisional speed diagnosis uses the exact pre-cutover 20M window and latest
  60 candidate rows: weighted effective h/s `1,457.517 / 1,499.908`, ratio
  `1.0291`; current decision `CONTINUE_SPEED_GATE_CURRENTLY_PASS`. It is not the
  terminal 20M judgment.

## Completed 500M phase (historical)

- Audit: `reports/v5_500m_promotion_readiness_audit_20260710.md/json`, verdict
  `WAITING_BLOCKED_EXPECTED`.
- The promotion plan remains blocked exactly by `training_hands` and the current
  exact-checkpoint `quality_gate`; no Slumbot launch occurred.
- Formal100k is now pinned to the exact checkpoint whose same-target
  promotion20k gate has `promotion_20k_strong=true`; a gate from another
  checkpoint cannot authorize it.
- Official direct sessions now abort if `BelowNormal` priority cannot be
  applied.
- Verification passed: focused `9/9`, full V5 unittests `151/151`, rearm checks
  `14/14`. These are control-plane changes only; trainer behavior is unchanged.

## Experiments and measurement

- EXP-002: `ADOPTED_RETAINED` multi-env (`multi`, 16 envs/worker, min batch
  slots 256, deadline 1000 us).
- EXP-003: terminal judgment `INCONCLUSIVE`. The trainer flags remain active,
  but the first eligible frozen bundle cannot be rerun, extended, or moved to
  a later checkpoint. Frozen gate `24900 / 409,058,520`, SHA256
  `060e73affd87d577d87fe6b21b328c5c325f3f1e8975f57bef4bfff514abd020`;
  `post_vs_native` CI half-width `22.199 > 20.0`.
- EXP-004: stable prior floor preflop/postflop `0.01/0.02`; `0.005` was rolled
  back and zero prior is blocked.
- EXP-005: `RUNNING_FIXED_20M_WINDOW`; registration is
  `reports/v5_exp005_group_assignment_registration_20260710.md/json`.
  Endpoint, throughput/stability rules, MEAS-001 sample size/seed contract,
  abort criteria, and rollback are frozen. EXP-006 bundling is forbidden.
- MEAS-001 is now `IMPLEMENTED_VALIDATED_NOT_LAUNCHED` in
  `v5_prospective_measurement_design_meas001_20260710.md/json`. It fixes
  100,000 common-deal mirrored pairs and paired causal estimands for a future,
  separately registered method experiment. It does not reopen EXP-003, select
  the next method, or authorize a trainer change. Focused tests passed `10/10`;
  all `14` V5 regression scripts passed (`142` unittests plus `14` rearm
  checks). No measurement was launched.

## Latest evidence

- Official gate30700 promotion20k completed with a full audited bundle:
  `20,400` greedy-direct hands, `-153.2999 bb/100`, 95% CI
  `[-187.6945, -118.9052]`, `promotion_20k_strong=false`. Formal100k is
  blocked and there is no V4/L5/L6 claim.
- The completed loss review found a large 250M-to-500M policy-distribution
  lurch and supported EXP-005. The fixed EXP-006A direct gate did not pass, so
  exactly EXP-005 was registered and cut over from gate31400.
- Gate31400 source evidence: exact PASS at `515,989,661`; health PASS;
  internal `MIXED_INTERNAL`, delta mean/lower `+14.020 / -238.797 bb/100`;
  preflop `WARN1`. These are local method diagnostics, not strength evidence.

The older gate chronology below is retained for audit context.

- Gate `27500`: exact PASS at `451,830,746` hands. Internal probe provenance is
  valid and verdict is `MIXED_INTERNAL`, delta mean/lower `+283.043 / +108.467
  bb/100`; preflop remains `WARN` with one SB-open overlimp warning. Review is
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. This is local-only evidence.
- Gate `27600`: exact PASS at `453,475,071` hands. Exact probe and aggregate
  identities match; verdict `MIXED_INTERNAL`, delta mean/lower `-345.678 /
  -94.704 bb/100`; preflop `WARN` with four call-suppression warnings. Review is
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; this remains local-only evidence.
- Reporting incident: the original 02:48 Ops row copied gate 27500's delta
  fields before the 27600 L6 aggregate refreshed. The row is preserved and its
  two delta fields are superseded by the append-only CENSURE plus
  `reports/v5_gate27600_reporting_race_censure_20260710.md/json`. The reviewer
  now fails closed on aggregate-target mismatch. Full tests `152/152`, rearm
  checks `14/14`, watcher survival `PASS`, range `27700..28800`; trainer
  untouched.
- Gate `27700`: exact PASS at `455,119,923` hands. The new aggregate identity
  gate passed with exact target `MATCH`; verdict `REGRESSION_RISK_INTERNAL`,
  delta mean/lower `-3.925 / -35.529 bb/100`, target rows call-station `+0.785`
  and aggressive `+193.0`. Preflop is `WARN` with four call-suppression
  warnings. Review remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only.
- Gate `27800`: exact PASS at `456,766,342` hands. The post-review guard held
  the exact valid target probe in `PENDING_L6_AGGREGATE_IDENTITY` with null
  deltas while aggregate remained at 27700, then completed only after exact
  27800 `MATCH`. Verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `+79.608 / -225.279`, target rows call-station `-149.0`, aggressive `+502.0`;
  preflop `WARN` with one SB-open overlimp warning. Local-only.
- Gate `27900`: exact PASS at `458,412,500` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `+138.500 / +460.381`,
  target rows call-station `-45.75`, aggressive `+675.75`. Preflop is `PASS`
  with zero warnings; checkpoint delta is
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only and no early promotion.
- Cadence refreshed at checkpoint 27900 with quality accepted and exactly one
  failed check: `training_hands`. No launchable key or active launch exists;
  quality must be re-established on the eventual launch checkpoint.
- Gate `28000`: exact PASS at `460,057,601` hands with snapshot pool `5/5`,
  `per-iteration` assignment and `loss-kbest`. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `+19.875 / -186.083`,
  target rows call-station `-216.0`, aggressive `+885.75`; preflop `PASS` with
  zero warnings. Review `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only.
- Cadence refreshed at checkpoint 28000 with quality accepted and only
  `training_hands` failing; no launchable key or active launch.
- Gate `28100`: exact PASS at `461,703,003` hands. Aggregate identity `MATCH`,
  verdict `MIXED_INTERNAL`, delta mean/lower `+457.500 / +589.227`, target rows
  call-station `+86.0`, aggressive `+1498.75`; preflop `PASS` with zero
  warnings. Review `REVIEW_REQUIRED_NO_AUTO_RESTART`; internal-only despite
  positive local diagnostics.
- Cadence refreshed at checkpoint 28100 with quality accepted and only
  `training_hands` failing; no launchable key or active launch.
- Gate `28200`: exact PASS at `463,348,302` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`; aggregate deltas are unavailable and
  remain null. Target rows call-station `+83.58`, aggressive `+564.75`;
  preflop `WARN` with four call-suppression warnings, checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Review `REVIEW_REQUIRED_NO_AUTO_RESTART`;
  local-only.
- Cadence refreshed at checkpoint 28200 with exact blockers `training_hands`
  and `quality_gate`; no launchable key or active launch. Earlier checkpoint
  quality PASS was not transferred.
- Gate `28300`: exact PASS at `464,993,502` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `+55.210 / +183.019`;
  target rows call-station `-58.5`, aggressive `+817.25`. Preflop remains
  `WARN` with four warnings covering SB overlimp/underraise and BB underraise
  versus min-open and 3bb-open; checkpoint delta `LOCAL_GUARDRAILS_MIXED`.
  Review remains `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only.
- Cadence independently refreshed against checkpoint 28300 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch. Quality remains exact-checkpoint-local.
- Gate `28400`: exact PASS at `466,638,377` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `+8.780 / -152.443`.
  The current checkpoint is pool snapshot `pool_id114_466M`; target rows are
  call-station `-122.69`, aggressive `+899.0`. Preflop improved from four
  warnings to one SB-open overlimp warning; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only.
- Cadence refreshed at checkpoint 28400 with exact blockers `training_hands`
  and `quality_gate`, null launchable key, and no active launch. The subsequent
  canonical rearm passed survival for `28500..29600` without touching trainer
  behavior or launching Slumbot.
- Gate `28500`: exact PASS at `468,283,337` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-463.905 / -417.873`;
  target rows call-station `-418.75`, aggressive `+267.25`. Preflop regressed
  from one warning to four argmax call-suppression warnings; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Review remains
  `REVIEW_REQUIRED_NO_AUTO_RESTART`; local-only.
- Cadence independently refreshed at checkpoint 28500 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `28600`: exact PASS at `469,929,538` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+783.250 / +868.739`; snapshot `pool_id115_469M` rows
  call-station `+92.75`, aggressive `+1322.25`. Preflop is `WARN` with two
  SB-open overlimp/underraise warnings; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Positive local values remain internal-only.
- Cadence independently refreshed at checkpoint 28600 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `28700`: exact PASS at `471,574,569` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-363.163 / -622.659`;
  target rows call-station `-28.325`, aggressive `+717.0`. Preflop improved to
  `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Local-only.
- Cadence independently refreshed at checkpoint 28700, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active. Quality PASS is non-transferable.
- Gate `28800`: exact PASS at `473,218,725` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+903.288 / +816.730`; target rows call-station `+691.25`, aggressive
  `+1804.0`. Preflop remains `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Positive local values remain
  internal-only.
- Cadence independently refreshed at checkpoint 28800, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `28900`: exact PASS at `474,864,258` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-421.310 / -271.139`;
  target rows call-station `-155.37`, aggressive `+1808.0`. Preflop regressed
  to `WARN` with one SB-open overlimp warning; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Local-only.
- Cadence independently refreshed at checkpoint 28900 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29000`: exact PASS at checkpoint/live `476,509,985` hands with
  snapshot pool `5/5`, assignment `per-iteration`, strategy `loss-kbest`,
  version `v5.zero`. Aggregate identity `MATCH`, verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `-660.250 / -389.437`;
  snapshot `pool_id117_476M` rows call-station `-74.87`, aggressive `+407.0`.
  Preflop remains `WARN` with one SB-open overfold warning; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Local-only.
- Cadence independently refreshed at checkpoint 29000 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29100`: exact PASS at `478,155,874` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-16.020 / -361.813`;
  target rows call-station `-99.66`, aggressive `+399.75`. Preflop improved to
  `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Local-only.
- Cadence independently refreshed at checkpoint 29100, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29200`: exact PASS at `479,800,561` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+549.330 / +683.415`; target rows call-station `+90.25`,
  aggressive `+1308.5`. Preflop remains `PASS` with zero warnings; checkpoint
  delta `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Local-only.
- Cadence independently refreshed at checkpoint 29200, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29300`: exact PASS at `481,446,177` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `-799.000 / -824.612`;
  target rows call-station `-113.5`, aggressive `-85.75`. Preflop regressed to
  `WARN` with SB-open overlimp/underraise warnings; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Strong local regression, but still
  internal-only.
- Cadence independently refreshed at checkpoint 29300 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29400`: exact PASS at `483,090,386` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `+1172.845 / +931.855`; target rows diverge, call-station
  `-136.31` and aggressive `+2282.75`. Preflop regressed to `WARN` with four
  argmax call-suppression warnings; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only.
- Cadence independently refreshed at checkpoint 29400 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29500`: exact PASS at `484,734,368` hands. Aggregate identity `MATCH`,
  verdict `MIXED_INTERNAL`; aggregate delta fields are genuinely unavailable
  and remain null. Target rows call-station `-142.92`, aggressive `+1924.5`.
  Preflop is `WARN` with SB overlimp/underraise and BB 3bb-open overcall;
  checkpoint delta `LOCAL_GUARDRAILS_MIXED`. Local-only.
- Cadence independently refreshed at checkpoint 29500 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29600`: exact PASS at checkpoint/live `486,379,183` hands with
  snapshot pool `5/5`, assignment `per-iteration`, strategy `loss-kbest`,
  version `v5.zero`. Aggregate identity `MATCH`, verdict
  `REGRESSION_RISK_INTERNAL`, delta mean/lower `-901.548 / -757.761`;
  snapshot `pool_id120_486M` rows call-station `-286.015`, aggressive `+264.5`.
  Preflop has four argmax call-suppression warnings; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. The repaired Ops watcher live-verifiably emits
  terminal EXP-003 `INCONCLUSIVE` and forbids rerun.
- Cadence independently refreshed at checkpoint 29600 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `29700`: exact PASS at checkpoint/live `488,023,806` hands. Aggregate
  identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+547.355 / +408.378`; target rows call-station `+287.945`, aggressive
  `+785.25`. Preflop improved to `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`. Internal-only.
- Cadence independently refreshed at checkpoint 29700, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29800`: exact PASS at `489,669,515` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+198.993 / +319.828`; target rows call-station `+64.93`, aggressive
  `+1406.25`. Preflop remains `PASS` with zero warnings; checkpoint delta
  `LOCAL_GUARDRAILS_PASS_STRENGTH_UNPROVEN`. Internal-only.
- Cadence independently refreshed at checkpoint 29800, accepted exact quality,
  and remains blocked solely by `training_hands`; launchable key is null and no
  launch is active.
- Gate `29900`: exact PASS at `491,314,339` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower `+25.285 / +103.177`;
  target rows call-station `+104.75`, aggressive `+1417.0`. Preflop regressed
  to `WARN` with SB-open overfold and BB overfold against min-open/3bb-open;
  checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. Local-only.
- Cadence independently refreshed at checkpoint 29900 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `30000`: exact PASS at `492,958,809` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+57.960 / -220.033`; target rows call-station `-79.83`, aggressive
  `+1717.5`. Preflop is `WARN` with SB overlimp/underraise and BB overcall;
  checkpoint delta `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30000 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `30100`: exact PASS at `494,603,729` hands. Aggregate identity `MATCH`,
  verdict `MIXED_INTERNAL`, delta mean/lower `-578.000 / -555.476`; target rows
  call-station `-239.83`, aggressive `+721.5`. Preflop is `WARN` with SB
  overlimp/underraise and BB overfold; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30100 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch.
- Gate `30200`: exact PASS at `496,248,804` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+819.603 / +968.756`; target rows call-station `+0.125`, aggressive
  `+2120.75`. Preflop is `WARN` with SB overlimp/underraise; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30200 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch. Saved-checkpoint distance to 500M is `3,751,196` hands.
- Gate `30300`: exact PASS at `497,894,785` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `REGRESSION_RISK_INTERNAL`, delta
  mean/lower `-689.453 / -706.749`; target rows call-station `-149.78`,
  aggressive `+891.75`. Preflop is `WARN` with greedy-call suppression in SB
  open, both BB facing-open cases, and SB-vs-3bet, plus BB min-open overfold;
  checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`. Internal-only.
- Cadence independently refreshed at checkpoint 30300 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch. Saved-checkpoint distance to 500M is `2,105,215` hands.
- Gate `30400`: exact PASS at `499,539,051` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`.
  Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `-682.860 / -848.656`; target rows call-station `+53.0`, aggressive
  `-676.75`. Preflop is `WARN` with SB overfold/overlimp/underraise, BB
  min-open overfold/underraise, and BB 3bb-open underraise; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only.
- Cadence independently refreshed at checkpoint 30400 with exact blockers
  `training_hands` and `quality_gate`, null launchable key, and no active
  launch. Saved-checkpoint distance to 500M is `460,949` hands; the live
  counter does not qualify, so gate30500 remains the first eligible identity.
- Gate `30500`: exact PASS at `501,183,802` hands, the first saved checkpoint
  at or above 500M, with snapshot pool `5/5`, assignment `per-iteration`,
  strategy `loss-kbest`, version `v5.zero`, health `PASS`, and entropy above
  floor. Aggregate identity `MATCH`, verdict `MIXED_INTERNAL`, delta mean/lower
  `+1018.900 / +1355.847`; target rows call-station `+4.30`, aggressive
  `+1409.75`. Preflop is `WARN` with SB overlimp/underraise and BB overcall
  versus min-open/3bb-open; checkpoint delta `LOCAL_GUARDRAILS_MIXED`.
  Internal-only.
- Cadence independently refreshed at checkpoint 30500: `training_hands`
  passes, but `quality_gate` fails. Launchable key is null, active launch count
  is zero, and no promotion ran. Per the readiness audit, gate30600 is the next
  exact candidate; do not bypass or weaken quality.
- Gate `30600`: exact PASS at `502,828,646` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`, health
  `PASS`, and entropy above floor. Aggregate identity `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `-216.307 / -260.969`; target rows
  call-station `+415.935`, aggressive `+565.5`. Preflop is `WARN` with greedy
  call suppression in SB open, BB versus min-open/3bb-open, and SB versus 3bet;
  checkpoint delta `LOCAL_GUARDRAILS_MIXED`. Internal-only.
- Cadence independently refreshed at checkpoint 30600: `training_hands`
  passes, `quality_gate` fails, launchable key is null, active launch count is
  zero, and no promotion ran. This is the second consecutive >=500M exact
  checkpoint blocked on quality; gate30700 is the next covered candidate.
- Gate `30700`: exact PASS at `504,474,081` hands with snapshot pool `5/5`,
  assignment `per-iteration`, strategy `loss-kbest`, version `v5.zero`, health
  `PASS`, and entropy above floor. Aggregate identity `MATCH`, verdict
  `MIXED_INTERNAL`, delta mean/lower `+324.657 / +252.755`; target rows
  call-station `-50.5`, aggressive `+1681.25`. Preflop is `PASS` with zero
  warnings; checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`.
  Internal-only.
- Cadence selected gate30700 as the first >=500M exact health/quality PASS and
  launched the official greedy-direct promotion20k from frozen identity
  `30700 / 504,474,081`: direct launch, 12 x 1,700 = 20,400 hands. Plan and
  preflight passed; 12 workers use the same checkpoint at BelowNormal priority.
  Status is `RUNNING`; do not read partial scores.
- Gate `30800`: exact PASS at `506,119,032` hands. Aggregate identity `MATCH`,
  verdict `MIXED_INTERNAL`, delta mean/lower `+236.110 / +218.974`; target rows
  call-station `-7.78`, aggressive `+2110.75`. Preflop is `WARN` with one
  SB-open overlimp warning; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`.
  Internal-only; the frozen promotion identity remains gate30700.
- Gate `30900`: exact PASS at `507,763,528` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-623.937 / -469.024`; target rows call-station `-111.655`, aggressive
  `+966.75`. Preflop is `WARN` with greedy-call suppression in SB open and BB
  versus min-open; checkpoint delta `LOCAL_GUARDRAILS_REGRESSED`.
  Internal-only; the frozen promotion identity remains gate30700.
- Gate `31000`: exact PASS at `509,408,918` hands. Aggregate identity `MATCH`,
  verdict `MIXED_INTERNAL`, delta mean/lower `+276.202 / -2.340`; target rows
  call-station `+427.25`, aggressive `+980.25`. Preflop is `PASS` with zero
  warnings; checkpoint delta `LOCAL_GUARDRAILS_IMPROVED_STRENGTH_UNPROVEN`.
  Internal-only; the frozen promotion identity remains gate30700.
- Gate `31100`: exact PASS at `511,054,065` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-563.335 / -137.498`; target rows call-station `-79.42`, aggressive
  `+360.25`. Preflop is `WARN` with greedy-call suppression across SB open, BB
  versus min/3bb open, and SB versus 3bet; checkpoint delta
  `LOCAL_GUARDRAILS_REGRESSED`. Internal-only; the frozen promotion identity
  remains gate30700.
- Gate `31200`: exact PASS at `512,698,792` hands. Aggregate identity `MATCH`,
  verdict `REGRESSION_RISK_INTERNAL`, delta mean/lower
  `-267.083 / -460.070`; target rows call-station `-512.585`, aggressive
  `+259.25`. Preflop is `WARN` with greedy-call suppression across SB open, BB
  versus min/3bb open, and SB versus 3bet; checkpoint delta
  `LOCAL_GUARDRAILS_MIXED`. Internal-only; the frozen promotion identity
  remains gate30700.
- Gate30700 promotion has completed 12/12 Slumbot parts and is in
  `SELECTOR_REPLAY`. Do not read or report the core score until selector replay
  and the complete CI/promotion/loss/audit/hand-review bundle settle.
- Gate `27200`: exact PASS at `446,895,262` hands. Internal probe is
  `MIXED_INTERNAL`; preflop probe `WARN` with 7 warnings. Review is
  `REVIEW_REQUIRED_NO_AUTO_RESTART`. These are local-only signals.
- Fixed pre-500M method diagnostic v2 ranks
  `EXP005_STRUCTURAL_PRIORITY`: 1,000-row KL median `0.0404`, KL>0.03 fraction
  `0.902`, KL>0.10 fraction `0.049`, clipfrac mean `0.2445`; isolated EXP-006A
  does not pass its complete gate. Last-10 exact-gate warnings are
  `[1,2,4,4,6,0,2,2,7,2]` (range 7, two PASS/WARN switches), supporting the
  EXP-005 structural hypothesis. This is not a cutover authorization. Artifact:
  `reports/v5_method_selection_diagnostic_pre500m_20260710_v2.json`. The v1
  artifact is superseded because its official-trend fields were null.
- V4 current-harness baseline: 20,400 greedy hands, `-71.383 bb/100`,
  CI `[-92.222, -50.543]`.
- Current-line promotion20k: 20,400 hands, `-140.151 bb/100`,
  CI `[-178.386, -101.916]`, complete bundle, `strong=false`, L0.
- Formal V5: 100,000 hands, `-100.248 bb/100`, CI
  `[-112.407, -88.088]`, complete bundle, L0.
- No stronger-than-V4, L5, or L6 claim is allowed.

## Correct next action

Keep the trainer and EXP-002/003/004 flags unchanged only through the
current-line `500M` evidence checkpoint. Gate30700 is the first exact quality
PASS and its promotion20k is running. Keep training unchanged, continue exact
gate reporting, and wait for the complete promotion bundle without reading
partial scores. Do not treat this as authorization
to carry the same method unchanged to 2.7B: the 500M official result is the
mandatory retain-or-change decision boundary.

Preserve the implemented and tested MEAS-001 contract without launching it.
Before any EXP-005/006/007, prior, PPO, pool, or speed behavior change, write a
separate complete experiment registration with its own baseline, fixed
candidate window, gates, abort criteria, and rollback.

If the 500M promotion is non-strong, use the audited loss bundle with the fixed
diagnostic. EXP-005 is the current provisional candidate; EXP-006A can replace
it only if the 500M-boundary direct-signal gate passes. Never bundle them.

The next official cadence is promotion20k at `500M` checkpoint hands if the
quality gate passes. About `5.4M` checkpoint hands remain; the current
effective-rate estimate is roughly `0.9-1.0h`. Formal100k remains
contingent on `promotion_20k_strong=true` from that exact promoted checkpoint;
otherwise finish the audited loss review and register exactly one next method
experiment.
