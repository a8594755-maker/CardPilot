# AlphaHoldem V5 Takeover Handoff - 2026-07-09

Checked at `2026-07-09 17:19 EDT`. This handoff supersedes the 2026-07-06
takeover snapshot. Always refresh live artifacts before acting.

## Objective

The canonical current goal is `docs/V5_CURRENT_GOAL.md`. The target remains L6
near `+11.1 bb/100` versus Slumbot. L5 requires 100k+ official greedy-direct
hands, positive bb/100, and a positive 95% CI lower bound.

## Live state

- Run:
  `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709`.
- Trainer PID `48476`, health `PASS`, stderr empty.
- Saved checkpoint: gate 24200 / `397,542,929` hands. Live health row at the
  snapshot: iter 24270 / `398,694,646` hands.
- Collect-only recent mean: about `4,064 h/s`. Effective recent mean including
  PPO: about `1,606 h/s`; PPO share about 60%.
- Core/reporting watchers: health, dashboard, append-only Ops log, gate
  sequence, eval cadence, internal strength, and checkpoint archive.
  Gate/internal coverage ends at 24900; latest canonical rearm survival PASS.
- No active Slumbot or mirror child at the snapshot.

## Experiments

- EXP-002: adopted/retained multi-env path (`multi`, 16 envs/worker, min batch
  slots 256, deadline 1000 us).
- EXP-003: active from gate21800 / `358,064,575`; mirrored deals and bounded
  K=200 all-in EV are on, with `aiev_skip=0`. First eligible judgment checkpoint
  is a PASS checkpoint `>=408,064,575`, expected near gate24900.
- EXP-004: preflop 0.005 step failed and was rolled back. Stable floor is
  preflop prior 0.01 / postflop prior 0.02. Zero prior is not authorized.

## Evidence

- Fresh V4 current-harness baseline: 20,400 greedy hands,
  `-71.383 bb/100`, CI `[-92.222, -50.543]`.
- Latest current-line promotion20k: 20,400 greedy hands,
  `-140.151 bb/100`, CI `[-178.386, -101.916]`, full bundle PASS,
  candidate/strong false, L0.
- Latest formal V5: 100,000 greedy hands, `-100.248 bb/100`, CI
  `[-112.407, -88.088]`, full bundle PASS, L0.
- No stronger-than-V4, L5, or L6 claim is allowed.

## Correct next action

Keep the trainer unchanged through the first PASS checkpoint at or above
`408,064,575`. Do not restart, decay priors, start EXP-005/006/007, execute a
throughput sweep, hand-launch Slumbot, or tune from 200-hand probes.

At eligibility, follow
`reports/v5_exp003_judgment_protocol_20260709.md`: freeze the first eligible
checkpoint and produce the three-role 25k-pair causal mirror bundle. A valid
bundle becomes `REVIEW_READY`, not `DONE`; a separate ADOPT/ROLLBACK judgment is
required.

## Control-plane corrections made in this handoff

- `v5_next_action_queue.py` no longer treats one precise candidate mirror as an
  EXP-003 success. It requires the three causal roles and an explicit judgment.
- EXP-003 mirror ETA now uses effective wall-clock h/s rather than collect-only
  h/s.
- External eval queue entries are stage-aware; 500M promotion20k is no longer
  mislabeled as a guarded quick5k, and duplicate promotion entries are removed.
- `v5_throughput_sweep_plan.py` now inherits all active EXP-002/003 execution
  flags, blocks impossible min-batch capacity, and requires explicit opt-in for
  a hands-per-iteration change because that changes PPO cadence.

These are reporting/planning safeguards only. The live trainer, weights, flags,
and training process were not changed. The watcher fleet was canonically
rearmed to load the safeguards and add the repaired Ops watcher.
