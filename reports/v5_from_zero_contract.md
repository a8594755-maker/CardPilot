# AlphaHoldem V5 From-Zero Contract

Generated: 2026-07-03

## Goal

Build V5 from random initialization as an AlphaHoldem-style 200bb HUNL end-to-end RL agent.

Reference: Zhao et al., "AlphaHoldem: High-Performance Artificial Intelligence for Heads-Up No-Limit Poker via End-to-End Reinforcement Learning", AAAI 2022.

Primary benchmark: Slumbot at 200bb HUNL.

L6 target: approach the paper claim, approximately +111.56 mbb/hand, or +11.1 bb/100, versus Slumbot.

Formal success gate: 100k+ Slumbot hands with bb/100 > 0 and 95% CI lower bound > 0. L6 is stronger: near +11.1 bb/100.

## Training Method

- Start from random initialization, not V4, BC, Slumbot-proxy, or CFR-distilled checkpoints.
- Use the AlphaHoldem pseudo-Siamese network:
  - card tensor branch
  - action-history tensor branch
  - extra-state branch
  - policy head and value head
- Use 200bb HUNL environment to match Slumbot stack depth.
- Use 9 discrete actions:
  - fold
  - check/call
  - six pot-fraction raise buckets
  - all-in
- Train with actor-critic PPO and Trinal-Clip policy/value losses.
- Use a K-best-style historical self-play opponent pool with K=5 by default.
  Future V5 launches default to `loss-kbest`, a Trinal-Clip selection-loss
  proxy for paper-style K-best survivor selection. FIFO `latest` remains
  available only as an ablation/legacy mode.
- Default paper-scale target is 2.7B hands.

## Logged Deviations From Paper

The paper does not fully disclose several implementation details. V5 may tune these, but every deviation must be logged and benchmarked:

- K value and pool selection rule
- entropy coefficient and entropy floor
- snapshot frequency
- self-play versus pool sampling fraction
- learning-rate schedule
- reward/value normalization
- throughput optimizations
- environment bug fixes
- anti-collapse guardrails

## Implementation Alignment Audit

Checked against the current worktree on 2026-07-03:

- network alignment: PASS
  - `scripts/alpha_holdem/network.py` implements separate card tensor, action-history tensor, and extra-state branches, fused into policy and value heads.
- action-space alignment: PASS
  - `environment_v55.py` keeps the 9-slot action space: fold, check/call, six pot-fraction raise slots, and all-in.
- 200bb environment alignment: PASS
  - current V5 run uses `--starting-stack 200 --env-version v55`.
- Trinal-Clip PPO alignment: PASS
  - `train_v5.py` calls `trinal_clip_ppo_update` from `train_mp3.py`.
  - that update applies standard PPO ratio clipping, the delta1 cap for negative-advantage policy ratios, and committed-chip value bounds via `[-hero_chips, +villain_chips]`.
- reward perspective alignment: PASS
  - `environment_v55.step()` returns terminal reward from the player who just acted.
  - `train_v5.py` records `last_actor` and converts terminal reward into each player's perspective before building transitions.
- opponent-pool alignment: PARTIAL PASS, ENGINEERING DEVIATION
  - `train_v5.py` now defaults to `--pool-strategy loss-kbest` rather than FIFO latest-K.
  - snapshots are ranked by `selection_loss = policy_loss + 0.5*log1p(value_loss)`, derived from Trinal-Clip update stats.
  - this is still not a paper-exact ELO survivor tournament; it is a single-GPU proxy that must be validated by internal probes and Slumbot gates.
  - legacy FIFO remains available as `--pool-strategy latest` for ablations and old-run comparison.
- Trinal-Clip instrumentation: FIXED FOR FUTURE RUNS, NOT HOT-APPLIED TO ACTIVE PROCESS
  - `trinal_clip_ppo_update` computes `clip_frac`, `delta1_bite_frac`, policy-ratio quantiles, and approximate KL.
  - `train_v5.py` now logs those diagnostics and writes them into `run_manifest.json` for future launches or restarts.
  - `v5_monitor.py`, `v5_progress.py`, and `v5_gate_watch.py` now remain compatible with both the active old log format and future logs that include those optional diagnostics.
  - the already-running `v5_zero_l6_fixedenv_20260703_1445` process was started before this logging patch, so its live log remains on the older format until a future run/restart.
  - training health is still monitored through entropy, value loss, throughput, action mix, pool snapshots, and checkpoint metadata.

## Implemented Run Contract

V5 now uses `scripts/alpha_holdem/train_v5.py` as the clean-from-zero trainer.

Default behavior:

- refuses `--resume` unless `--allow-resume` is explicitly passed
- writes an isolated run directory
- writes `init.pt` to prove random-init start
- writes `run_manifest.json` with paper reference, Slumbot target, config, and progress
- stores goal/config metadata inside checkpoints
- defaults to 2.7B total hands, 200bb, gamma=0.999, delta1=3.0, entropy floor 0.3
- defaults to `env_version=v55`, the fixed 200bb environment that repairs the legacy V4/V5 action-history and raise-cap issues
- writes `env_version`, `obs_version`, `action_space_version`, `starting_stack_bb`, and `actual_hand_accounting` into checkpoints so Slumbot evaluation does not guess the encoder
- counts `total_hands` as actual poker hands, not player terminal trajectories; the log's `terms=` field records terminal player trajectories separately

Smoke verified:

```bash
python scripts/alpha_holdem/train_v5.py --device cpu --workers 1 --hands-per-iter 4 --total-hands 4 --ppo-epochs 1 --mini-batch-size 4 --snapshot-every 1 --save-interval 1 --run-dir tmp/v5_smoke --run-id smoke --overwrite --max-runtime-seconds 120
```

Result:

- checkpoint version: `v5.zero`
- run id: `smoke`
- manifest `fresh_from_zero=true`
- checkpoint contains L6 target metadata
- resume guard rejects accidental `--resume`

Accounting smoke verified after the hand-count fix:

```bash
python scripts/alpha_holdem/train_v5.py --device cpu --workers 1 --hands-per-iter 4 --total-hands 4 --ppo-epochs 1 --mini-batch-size 4 --snapshot-every 1 --save-interval 1 --run-dir tmp/v5_accounting_smoke --run-id accounting --overwrite --max-runtime-seconds 120
```

Result:

- `hands=50`
- `terms=82`
- confirms actual poker hands and player terminal trajectories are no longer conflated

Fixed-environment smoke verified after wiring `env_version=v55` into V5:

```bash
python scripts/alpha_holdem/train_v5.py --device cpu --workers 1 --hands-per-iter 4 --total-hands 4 --ppo-epochs 1 --mini-batch-size 4 --snapshot-every 1 --save-interval 1 --run-dir tmp/v5_fixed_env_smoke --run-id fixed_env_smoke --overwrite --max-runtime-seconds 120
```

Result:

- checkpoint version: `v5.zero`
- `env_version=v55`
- `obs_version=v55`
- `actual_hand_accounting=True`
- `starting_stack_bb=200.0`
- Slumbot loader dry-run selected `Observation encoding: v55`

## Full V5 Launch Command

```bash
python scripts/alpha_holdem/train_v5.py \
  --device cuda \
  --workers 28 \
  --hands-per-iter 16384 \
  --total-hands 2700000000 \
  --starting-stack 200 \
  --env-version v55 \
  --lr 3e-4 \
  --gamma 0.999 \
  --delta1 3.0 \
  --entropy-coef 0.05 \
  --entropy-floor 0.3 \
  --k-best 5 \
  --pool-strategy loss-kbest \
  --pool-history-limit 200 \
  --self-play-fraction 0.2 \
  --opponent-assignment per-iteration \
  --snapshot-every 200 \
  --save-interval 100
```

This will create `models/alpha_holdem_v5_from_zero/<run-id>/`.

## Documented Engineering Deviations

### Loss-KBest Pool Selection

The paper describes maintaining historical competitors and selecting K best
survivors by ELO. The single-machine V5 trainer now moves closer to that target
than FIFO latest-K, but still does not run a full ELO tournament.

Implementation:

- `--pool-strategy loss-kbest` is the default for future V5 launches/restarts
- each snapshot records `selection_loss`, `selection_score`, and score components
- active `pool_snapshots` keep the K lowest-loss historical snapshots
- checkpoint metadata records `pool_strategy`, `pool_active_metadata`, and
  metadata-only `pool_candidate_history`
- `--pool-strategy latest` remains available for legacy comparison

Validation consequence:

- pool size alone is no longer enough; gate/watch tools can require
  `--expected-pool-strategy loss-kbest`
- this is still a logged deviation from paper-exact K-best/ELO and must be
  judged by Slumbot/internal evidence

### Opponent Assignment Batching

AlphaHoldem-style K-best self-play remains the training method, but future V5
launches/restarts now default to `--opponent-assignment per-iteration` instead
of the original independent per-worker sampler.

Reason:

- measured active-run throughput after the pool filled: average `h/s=424.1`,
  average `inf_bs=5.1`, average `collect=39.2s` over iterations 1000-1506
- measured early run before pool fragmentation: average `h/s=1,522.3`,
  average `inf_bs=22.3`, average `collect=10.9s` over iterations 1-99
- PPO update time is only about 2-3s per iteration, so the bottleneck is
  fragmented rollout inference, not PPO optimization

Implementation:

- `per-iteration`: each rollout iteration samples self-play or one pool
  snapshot for all workers; long-run opponent distribution is still governed by
  `self_play_fraction` and the configured historical opponent pool
- `per-worker`: preserves the original independent worker-level sampling for
  ablation

Verification:

- `python -m py_compile scripts/alpha_holdem/train_v5.py`
- CPU smoke with `--opponent-assignment per-iteration` completed and saved
  `tmp/v5_assignment_smoke/latest.pt`

This is a throughput-oriented deviation only. It does not change the Slumbot
promotion gates and cannot justify any L5/L6 claim without benchmark evidence.

### Checkpoint Continuation Lineage

V5 is required to originate from a fresh random initialization, but long runs
must still support checkpoint continuation. Formal gates therefore validate
`fresh_from_zero_lineage=True`, not merely `resume=None`.

Implementation:

- fresh V5 launches write `fresh_from_zero_lineage=True`
- continuation from a V5-from-zero checkpoint preserves that field
- checkpoints record the truth in `resume` and `lineage_parent_checkpoint`
- `lineage_root_run_id` records the original random-init run
- `v5_gate_watch.py` accepts a continuation checkpoint only if its lineage is
  still V5-from-zero

Verification:

- syntax check passed for `train_v5.py` and `v5_gate_watch.py`
- fresh CPU smoke wrote `tmp/v5_lineage_fresh/latest.pt`
- continuation CPU smoke resumed it with `--allow-resume --no-reset-optimizer`
- continuation checkpoint had `fresh_from_zero_lineage=True`,
  `lineage_root_run_id=lineage_fresh`, and
  `resume=tmp\v5_lineage_fresh\latest.pt`
- gate verifier returned PASS for the continuation checkpoint after CPU-smoke
  monitor thresholds were relaxed for the tiny local test

This rule is for preserving honest run provenance during operational restarts.
It does not allow V4, BC, Slumbot-specific, or other external checkpoints to be
counted as the V5-from-zero L6 run.

### Post-Gate Continuation Script

`scripts/alpha_holdem/v5_continue_after_gate.ps1` is the approved operational
path for applying future trainer fixes, such as opponent-assignment batching,
after a verified gate.

Safety rules:

- default mode is dry-run only
- gate verification must pass unless `-SkipGateCheck` is explicitly used for
  command-generation testing
- checkpoint metadata must prove V5 fixed-env lineage
- if the source trainer is still alive, execution refuses to launch unless
  `-StopOldTraining` is explicitly provided
- continuation uses `--allow-resume --no-reset-optimizer` so optimizer state is
  preserved

Validation performed:

- PowerShell parser check passed
- dry-run against the active checkpoint passed metadata validation
- pre-gate refusal test correctly rejected continuation while gate 1600 was
  still PENDING
- dry-run source-trainer detection reported the active source trainer PID
  before launch
- non-destructive post-gate dry-run watcher was parser-checked and armed for
  gate 1600; it only runs continuation dry-run after PASS
- no trainer was stopped and no continuation trainer was launched during
  validation

## Promotion Gates

A checkpoint can be considered for promotion only if:

- value loss does not explode
- entropy does not collapse
- action mix does not collapse into extreme fold/call/all-in behavior
- internal eval does not show broad regression
- Slumbot 20k hands clearly improves over the current baseline

Winning Slumbot cannot be claimed until:

- 100k+ hands are played
- bb/100 > 0
- 95% CI lower bound > 0

`scripts/alpha_holdem/slumbot_ci_from_hands.py` is the authoritative
classifier for saved per-hand Slumbot benchmark artifacts. It now outputs the
full L0-L6 milestone level, L5 blockers, and the delta versus the current
V4/BC-anchor baseline. It was syntax-checked and function-tested on
deterministic samples for L0 through L6 without calling the Slumbot API.

`scripts/alpha_holdem/v5_slumbot_promotion_gate.py` is the authoritative gate
wrapper for turning benchmark artifacts into promotion decisions. It checks
checkpoint metadata, V5-from-zero lineage, health status, CI JSON, and retained
per-hand artifacts before allowing 20k promotion, L5, or L6 decisions. It was
syntax-checked with positive and missing-artifact negative fixtures.

L6 cannot be claimed until the result is near +11.1 bb/100 versus Slumbot with enough hands to make the estimate meaningful.

### Post-Cutover Throughput Gate

`scripts/alpha_holdem/v5_throughput_compare.py` is the read-only engineering
gate for validating the planned batching cutover. It compares recent
`latest_train.log` windows from a baseline run and a candidate continuation run.

Default cutover acceptance thresholds:

- at least 10 baseline rows
- at least 10 candidate rows
- candidate h/s mean at least 1.25x baseline
- candidate `inf_bs` mean at least 1.8x baseline
- candidate `inf_bs` mean at least 8.0

Validation performed:

- Python compile check passed
- active-run self-compare passed with loose thresholds
- active-run self-compare failed with default cutover thresholds as expected

This gate does not evaluate poker strength. It exists only to prove that a
continuation using `--opponent-assignment per-iteration` actually improves the
pool-stage training throughput before committing long wall-clock time to it.

`scripts/alpha_holdem/v5_throughput_watch.py` is the optional post-cutover
watcher. `scripts/alpha_holdem/v5_continue_after_gate.ps1` can start it with
`-StartThroughputWatcher` after launching a continuation trainer. The watcher
does not start or stop training; it waits for enough candidate log rows, writes
`throughput_compare.json` and `throughput_compare.md`, and appends a final
throughput-only result to the launch report.

Watcher validation:

- Python compile check passed
- active-run self-compare passed with loose thresholds
- active-run self-compare failed with default cutover thresholds as expected
- continuation dry-run with `-StartThroughputWatcher` launched no process while
  `-Execute` was absent

`scripts/alpha_holdem/v5_health_watch.py` is the optional post-cutover health
watcher. `v5_gate_watch.py` reads `health_status.json` but does not generate it,
so a continuation run should be launched with `-StartHealthWatcher` when it is
expected to run unattended. The watcher periodically runs `v5_monitor.py`, keeps
`health_status.json` fresh, writes `health_watch.log`, and exits on health
`FAIL`. It can be configured to exit on `WARN` with `-HealthExitOnWarn`.

Health watcher validation:

- Python compile check passed
- active-run short timeout test refreshed monitor status and exited with the
  expected timeout code
- continuation dry-run with `-StartHealthWatcher` launched no process while
  `-Execute` was absent

### Cutover Safety

`v5_continue_after_gate.ps1` dry-run prints a recommended guarded cutover
command after metadata validation. The command includes gate re-verification,
`-Execute`, `-StopOldTraining`, detected `-OldTrainingPid`,
`-StartNextGateWatcher`, `-StartHealthWatcher`, and
`-StartThroughputWatcher`.

The execution path now refuses to launch a continuation if:

- the source trainer is running and `-StopOldTraining` is absent
- `-OldTrainingPid` is provided but does not match any detected source trainer
- any source trainer remains alive after the stop attempt

Validation performed:

- PowerShell parser check passed
- guarded cutover dry-run printed the full recommended command and launched no
  process
- wrong-PID execute test refused before launch and left the active trainer
  running

### Gate Health Freshness

`v5_gate_watch.py` supports `--refresh-health`. When enabled, each gate check
runs `v5_monitor.py` before evaluating the gate, then records the monitor
refresh result in the gate status JSON. `v5_continue_after_gate.ps1` now starts
future next-gate watchers with `--refresh-health --python <Python>`.

Validation performed:

- Python compile check passed
- active-run refreshed gate check returned PENDING as expected before iteration
  1600
- gate status JSON recorded `health_refresh.exit_code=0`
- dry-run continuation with next-gate watcher options launched no process

### Post-Gate Execute Watcher

`scripts/alpha_holdem/v5_post_gate_execute_watch.ps1` is the controlled path for
automating the gate-1600 cutover. It waits for a strict gate PASS, then invokes
`v5_continue_after_gate.ps1` without `-SkipGateCheck`, with `-Execute`,
`-StopOldTraining`, explicit `-OldTrainingPid`, `-StartNextGateWatcher`,
`-StartHealthWatcher`, and `-StartThroughputWatcher`.

Safety constraints:

- `OldTrainingPid` is required
- gate check must return PASS before cutover
- continuation script re-verifies the gate immediately before launch
- continuation script refuses wrong PID or any surviving source trainer after
  the stop attempt

Validation performed:

- PowerShell parser check passed
- pending-gate timeout probe exited without stopping PID 39172
- pending-gate timeout probe launched no continuation trainer
- production watcher was armed for gate 1600 and first reported PENDING

Gate 1600 cutover result:

- gate 1600 passed with checkpoint iteration 1600 and 5 pool snapshots
- source pool replacement was correct:
  `[13125578, 16407558, 19689242, 22971150, 26253143]`
- old trainer PID 39172 was stopped
- continuation trainer PID 42788 launched from the 1600 checkpoint
- continuation uses `--opponent-assignment per-iteration`
- optimizer state, hand counter, iteration, and fresh-from-zero lineage were
  preserved
- health watcher and refreshed gate 1700 watcher are running
- throughput watcher passed and exited

Post-cutover throughput result:

- baseline h/s mean: 374.85
- candidate h/s mean: 861.40
- h/s ratio: 2.298
- baseline `inf_bs` mean: 4.975
- candidate `inf_bs` mean: 14.300
- `inf_bs` ratio: 2.874
- collect speedup ratio: 2.161

Post-cutover operational fixes:

- `v5_gate_watch.py` now keeps a gate PENDING while pending checks remain,
  instead of exiting early on startup WARN before candidate logs/checkpoints
  exist
- the gate 1700 watcher was restarted with `--refresh-health`
- `v5_post_gate_execute_watch.ps1` now uses `Start-Process -Wait` with
  redirected cutover logs for future execute runs, avoiding stale wrapper
  processes after successful launch

Gate 1700 config validation:

- `v5_gate_watch.py` supports `--expected-opponent-assignment`
- continuation-launched future gate watchers pass
  `--expected-opponent-assignment per-iteration`
- the active 1700 watcher was restarted with the config gate
- the old 1700 watcher that lacked this check was stopped
- before the first continuation checkpoint, the config-aware gate correctly
  remains PENDING and records `opponent_assignment` as a pending checkpoint
  check

### Gate Sequence Watcher

`scripts/alpha_holdem/v5_gate_sequence_watch.py` is the active post-cutover gate
monitor. It reuses `v5_gate_watch.py` evaluation logic, writes normal per-gate
status JSON/Markdown, appends PASS gates to the launch report, then advances to
the next gate.

Active sequence:

- run: `v5_zero_l6_fixedenv_20260703_1445_after1600_periter`
- gates: 1700 through 2500, step 100
- snapshot cadence: 200
- expected K: 5
- expected opponent assignment: `per-iteration`
- refresh health before each gate check
- require current pool snapshot only on snapshot gates such as 1800, 2000, etc.

Validation performed:

- Python compile check passed
- single-pass 1700 probe returned PENDING as expected
- old single-gate watcher was stopped after the sequence watcher was confirmed
  running
