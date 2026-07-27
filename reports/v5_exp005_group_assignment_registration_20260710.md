# EXP-005 Group Opponent Assignment Registration

Registered at `2026-07-10 14:10 EDT`; implementation validated at `14:17 EDT`;
cut over at `14:29 EDT`; reclassified at `15:00 EDT`. The current run is now
`EXPLORATORY_PILOT_NO_METHOD_JUDGMENT`. It may run to the existing endpoint for
execution, assignment-provenance, and stability data only.

## Problem and evidence

M3 is now supported by the complete 500M loss review. With
`opponent_assignment=per-iteration`, every PPO update sees one opponent mode.
Official behavior swung from passive at the 250M promotion to extremely
raise-heavy at 500M while external performance stayed decisively negative.
The fixed EXP-006A gate did not pass.

Evidence inputs are frozen by path/hash in the JSON companion. The official
causal anchor is gate30700 / 504,474,081, not a later checkpoint.

## Hypothesis

Partitioning workers into five balanced, reshuffled groups per iteration, with
one group forced to self-play and four groups assigned pool opponents, will
make every PPO update see a mixture of opponent distributions. This should
reduce checkpoint-to-checkpoint preflop/internal swings without sacrificing
more than 10% effective throughput.

## Exact single behavior change

- Add `--opponent-assignment per-group` and `--opponent-groups 5`.
- Randomly reshuffle worker membership every iteration.
- Split workers into five balanced groups.
- Choose one group for self-play at `self_play_fraction=0.2` and assign each
  remaining group one pool snapshot; use distinct snapshots when available.
- Keep assignment constant within each group for the iteration.

Everything else is frozen: EXP-002 multi rollout flags, EXP-003 mirrored deals
and bounded-K all-in EV, EXP-004 global priors `0.01/0.02`, network/obs/env,
PPO/Trinal-Clip math, LR, entropy coefficient/floor, K=5 loss-kbest pool,
workers, hands per iteration, and official greedy Slumbot selector.

## Cutover input

Cutover is allowed only at the first exact PASS gate after implementation and
tests pass. At cutover, freeze and hash that exact saved checkpoint, record it
in the append-only Ops log, and resume through the standard continuation path.
Do not substitute unsaved live weights. Planned suffix:
`_exp005_pergroup5_r1_20260710`.

The cutover source is now frozen at exact gate `31400 / 515,989,661`:
`v5_exp005_cutover_gate31400_checkpoint.pt`, SHA256
`bcbb46bd01d62fcdea602269b7047323315d4e9bbcf447ea0323e289fde11a8e`.

Implementation was validated and the exact gate31400 source was frozen. The old
trainer PID `48476` was stopped only during the guarded cutover. Candidate PID
`30224` resumed the frozen checkpoint with manifest-verified `per-group/5`
assignment; all other registered flags are unchanged. The fixed endpoint is the
first exact saved checkpoint with at least `535,989,661` hands, expected at gate
`32700`. Canonical watcher coverage `31500..32700` passed survival.

## Fixed judgment window

> Superseded for method judgment. This section is retained as historical
> registration context only. The pilot may not produce EXP-005 PASS/FAIL,
> launch MEAS-001, promotion20k, or formal100k, or support V4/L5/L6 inference.
> Only a new immutable EXP005-C clean same-start design may judge the method.

- Candidate endpoint: first exact saved checkpoint at or above cutover hands
  plus `20,000,000` actual training hands; no early success judgment.
- Operational checks from launch: group-assignment invariants, health PASS,
  stderr clean, checkpoint freshness, actual-hand accounting, and no trainer
  flag drift.
- Speed gate: effective h/s must be at least 90% of the fixed pre-cutover
  baseline; abort if below 85% after one reporting-only diagnosis.
- Stability gate over the fixed 20M window: compare exact-gate preflop warning
  range/status switches, internal delta swing amplitude, and value-loss
  variance with the frozen 20M pre-cutover window. Require improvement in at
  least two of the three and no material worsening in the third.
- MEAS-001: after the endpoint checkpoint is frozen, run the registered
  100,000 common-deal pairs using the frozen gate30700 official anchor as the
  pre checkpoint and the endpoint as post. Require a valid terminal bundle and
  direct-causal non-inferiority; no adaptive extension or second seed.
- External gate: if endpoint health/quality pass, run one official
  greedy-direct promotion20k with the full bundle. It must improve versus the
  gate30700 `-153.300` reference by more than noise or at minimum be
  non-inferior while the registered stability/MEAS gates pass. This still
  cannot prove L5/L6.

## Abort and rollback

Abort on group invariant failure, incorrect self-play mixture, incorrect
actual-hand accounting, crash/health failure traced to the change, effective
h/s below 85%, checkpoint/lineage mismatch, or MEAS-001 terminal failure.
Rollback at the next exact gate using the frozen cutover checkpoint and
`--opponent-assignment per-iteration`. Do not change priors, PPO, pool, or
selector during rollback.

## Provisional speed diagnosis

The one reporting-only diagnosis after gate31500 uses the exact pre-cutover
20M actual-hand window `495,989,661..515,989,661` and the latest 60 candidate
rows. Baseline/candidate weighted effective h/s is `1,457.517 / 1,499.908`,
ratio `1.0291`; therefore the current decision is
`CONTINUE_SPEED_GATE_CURRENTLY_PASS`. Collect-only h/s and inference batch size
are lower, but PPO time is also lower. This is not the terminal endpoint speed
judgment and cannot support a poker-strength claim.

## Claim discipline

Internal stability and MEAS-001 are method evidence only. L5 still requires
100k+ official greedy-direct hands, positive bb/100, and positive 95% CI lower
bound. L6 additionally requires near `+11.1 bb/100`.

This pilot has no method-judgment or external-evaluation authority. Its endpoint
does not unlock MEAS-001 or Slumbot evaluation.
