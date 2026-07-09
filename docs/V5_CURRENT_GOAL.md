# AlphaHoldem V5 Current Goal

## Goal

Work on the AlphaHoldem V5-from-zero Slumbot track in
`C:\Users\a8594\CardPilot`.

Final target: L6, approximately `+11.1 bb/100` versus Slumbot. A valid L5 win
claim requires at least `100,000` official greedy-direct Slumbot hands,
`bb/100 > 0`, and a 95% CI lower bound `> 0`. No weaker evidence may support a
strength claim.

Current operational objective: complete and honestly judge EXP-003 at its
registered `>=50M` post-cutover gate without introducing another
behavior-affecting change.

## Governing documents (read in this order)

1. `AGENTS.md` - canonical V5 contract and current handoff pointer.
2. `docs/V5_TRAINING_PLAYBOOK.md` - lifecycle, gates, signal limits, and Ops log.
3. `reports/v5_training_method_audit_20260706.md` - audited problems and
   verified-correct behavior.
4. `reports/v5_method_improvement_roadmap.md` - ranked experiments and the
   do-not-do list.
5. `reports/v5_experiment_ledger.md` - read the append-only Ops log from
   `2026-07-07 14:40` through EOF. The Ops tail overrides stale seeded/header
   status and static snapshots.
6. Before every action, identify the live trainer/run and read its
   `run_manifest.json`, `health_status.json`, `v5_dashboard_watch_status.json`,
   `v5_next_action_queue.json`, latest `gate_*_status.json`, and latest
   `v5_post_gate_review_*.json`. Live artifacts override this snapshot.

## Current state

Snapshot: `2026-07-09 17:19 EDT`; refresh before acting.

- Active run:
  `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709`.
- Trainer PID `48476`; health `PASS`; trainer stderr empty. Saved checkpoint
  `24200 / 397,542,929` hands; live health row about
  `24270 / 398,694,646` hands. Gate 24200 and its post-gate evidence are
  complete; the queue is waiting for gate 24300.
- EXP-002 multi-env is adopted and retained: `multi`, 16 envs/worker,
  inference min slots 256, deadline 1000 us.
- EXP-003 is active: mirrored self-play deals plus deterministic bounded-K=200
  all-in EV. `aiev_skip=0`; no judgment has occurred.
- EXP-004 is held at the stable floor: preflop prior `0.01`, postflop prior
  `0.02`. The `0.005` step was rolled back; step-3/zero prior is not authorized.
- EXP-003 cutover baseline is gate 21800 / `358,064,575`. Judgment is eligible
  only at the first `PASS` checkpoint `>=408,064,575`; approximately 10.52M
  checkpoint hands remained at this snapshot. Use effective wall-clock h/s for
  ETA, not collect-only h/s.
- Throughput has two meanings and both must be reported: recent collect-only
  mean about `4,064 h/s`; effective wall-clock mean about `1,606 h/s` including
  PPO. PPO consumed about 60% of the recent iteration wall time.
- Fresh V4 current-harness Slumbot baseline: 20,400 greedy hands,
  `-71.383 bb/100`, CI `[-92.222, -50.543]`. The old `-49.7` baseline is
  superseded.
- Latest formal V5 evidence: 100,000 greedy hands, `-100.248 bb/100`, CI
  `[-112.407, -88.088]`, complete bundle, L0.
- Latest current-line promotion evidence: 20,400 greedy hands,
  `-140.151 bb/100`, CI `[-178.386, -101.916]`, complete bundle,
  `candidate=false`, `strong=false`, L0. Formal100k remains blocked until a
  promotion gate has `strong=true`.

## Hard rules

- Ops log is append-only UTF-8, one row per event. Never edit historical Ops
  rows or force an audit verdict.
- One behavior-affecting change per judgment window. While EXP-003 is open:
  no prior decay, trainer-method change, restart for inspection, live
  throughput sweep, EXP-005/006/007 launch, or checkpoint cherry-picking.
- Watcher re-arm only through
  `scripts/alpha_holdem/v5_rearm_watchers.ps1`.
- Official evidence is greedy-direct Slumbot with the complete hand-level
  bundle.
- Fixed mirrors use frozen checkpoints, identical protocol/seed, the v55-native
  75M anchor, and anchor OOD `<=0.15`. Legacy V4-anchor mirrors failing the OOD
  gate are quarantined.
- Internal 200-hand probes and training action mix are health/localization
  signals only.
- Never execute a throughput plan that fails to inherit the active EXP-002 and
  EXP-003 flags. Changing `hands_per_iter` also changes PPO cadence and is a
  separate behavior-affecting experiment, not a pure speed sweep.

## Execution order

1. Keep the current trainer running unchanged to the first `PASS` checkpoint
   `>=408,064,575` (expected near gate 24900). Continue ordinary health/gate
   reporting. Do not extend the training window post hoc.
2. Judge EXP-003 using the frozen three-role causal bundle in
   `reports/v5_exp003_judgment_protocol_20260709.md`: pre-cutover gate21800 vs
   native75M, eligible candidate vs native75M, and the same candidate directly
   vs gate21800. All three use 25,000 pairs, seed 20260709, greedy argmax on
   both sides, starting stack 200bb, and OOD `<=0.15`.
3. Treat a complete valid bundle as `REVIEW_READY`, never as automatic success.
   Write an explicit ADOPT/ROLLBACK judgment artifact and append one Ops row.
   Apply the registered health, throughput, counter, CI, and rollback gates.
4. Only after EXP-003 closes, choose one next method experiment through a fresh
   ledger entry. Do not automatically schedule prior-to-zero. Default research
   queue if evidence does not justify a different choice: EXP-005 group
   opponent assignment, EXP-006 isolated KL early-stop, then EXP-007 ELO-ranked
   K-best pool, one change per window.
5. Next external cadence is promotion20k at 500M if its quality gate passes.
   Launch formal100k only after `promotion_20k_strong=true`.

## Reporting

At every gate boundary report run ID, checkpoint/live iter and hands,
collect-only and effective h/s, health, experiments in flight, latest valid
native-anchor mirror, latest official Slumbot result, artifact completeness,
and exact next action/gate. Append one honest Ops row per event.

## Escalate to the user only for

Breaking from-zero on the main line, a V6 observation/architecture launch,
abandoning 2.7B, two consecutive reverted Tier-1 experiments, spending money,
or newly required authority outside the registered gate/rollback rules.
