# EXP-002 Batched Multi-Env Rollout Design Note

Date: 2026-07-06. Scope: AlphaHoldem V5-from-zero Slumbot track.

This is a read-only implementation note for the already registered EXP-002 entry in
`reports/v5_experiment_ledger.md`. It records the code map and intended implementation
shape, but it does not land trainer code and does not launch a cutover. The live trainer
PID `56876` must not be hot-edited or restarted outside the documented gate-boundary
continuation procedure.

## Registered Baseline

- active run: `v5_zero_l6_fixedenv_20260703_1445_after4000_aprior002_r1_after4400_preprior001_r1_after4600_preprior002_call36_r1`
- baseline gate: `9100`
- baseline checkpoint hands: `149,316,834`
- baseline health: `PASS`
- workers: `22`
- hands_per_iter: `16384`
- opponent_assignment: `per-iteration`
- pool_strategy: `loss-kbest`
- throughput audit baseline: tail_60 effective h/s `596.8`, tail_240 effective h/s `455.0`, mean inf_bs `12.15`, collect mean `25.11s`, PPO mean `3.60s`, GPU utilization `14%`

## Current Code Map

- `scripts/alpha_holdem/train_v5.py`
  - shared-memory layout constants: `CARD_SIZE`, `ACTION_SIZE`, `EXTRA_SIZE`, `MASK_SIZE`, `OBS_SIZE`, `RESULT_SIZE`
  - worker loop: `worker_process_v5(...)`
  - one-env shared-memory slot per worker: `obs_buf`, `result_buf`, `status_buf`, `assigned_buf`, `request_buf`
  - one-decision handshake: worker writes one flattened observation, sets `status_buf[0] = WAITING`, polls until `READY`, then steps one env
  - main inference: `run_inference_v5(...)`
  - current inference view: `obs_np.reshape(num_workers, OBS_SIZE)` and `status_np == WAITING`
  - transition accounting: `hand_marker` field is appended as tuple index `11`, and main counts actual poker hands from that marker
  - opponent assignment: `assign_opponents()` writes one assigned opponent id per worker into `assigned_np`
  - save/gate cadence: checkpoint saves at `save_interval`, pool snapshots at `snapshot_every`
- `scripts/alpha_holdem/environment_v55.py`
  - one env object exposes `reset()`, `step(action_idx)`, `chips_committed(player)`
  - `step()` relies on `last_action_table` cached by `_get_obs()`
  - no env semantics should change for EXP-002

## Intended EXP-002 Shape

Add a selectable multi-env rollout path while preserving the old path as the default until
offline validation and gate-boundary cutover are complete.

Planned flags:

- `--rollout-envs-per-worker <int>` default `1`
- `--rollout-mode single|multi-env` default `single` or inferred from envs-per-worker

Shared-memory shape when `M = rollout_envs_per_worker`:

- `obs_np`: `(W * M * OBS_SIZE,)`
- `result_np`: `(W * M * RESULT_SIZE,)`
- `status_np`: `(W * M,)`
- `request_np`: `(W * M,)`
- `assigned_np`: either `(W,)` if opponent assignment remains per worker, or `(W * M,)` only if a later registered change explicitly needs per-env assignment. EXP-002 should preserve current per-worker/per-iteration assignment semantics, so keep `(W,)`.

Worker behavior:

1. Each worker owns `M` independent `HUNLEnvironment` instances.
2. Each env tracks its own `hands_played`, `hero_player`, `hand_buffers`, `last_actor`, and local terminal accounting.
3. The worker steps every active env to the next decision point, writes each pending request into slot `slot = worker_id * M + env_idx`, and sets `status[slot] = WAITING`.
4. The worker waits only for its pending slots to become `READY`, applies those actions, and continues cycling envs.
5. It still emits transition tuples in the existing format, including tuple index `11` as `hand_marker`.
6. Actual hand accounting remains one `hand_marker=1.0` per completed poker hand, not per player trajectory and not per env slot.

Main inference behavior:

1. `run_inference_v5` accepts `num_slots = W * M` rather than `num_workers = W`.
2. It reshapes `obs_np` as `(num_slots, OBS_SIZE)`, finds `WAITING` slots, groups by `request_model_np`, and writes `result_np[slot]`.
3. Grouping by requested model is unchanged. Under `per-iteration` assignment, almost all live slots should share one requested model, raising mean `inf_bs` toward `W*M`.
4. Metrics should log both `workers` and `rollout_envs_per_worker`, plus `num_rollout_slots`.

## Non-Negotiable Invariants

- No env_version, obs_version, action_space_version, reward semantics, policy network, PPO math, action priors, pool strategy, or official Slumbot policy change.
- Preserve fresh-from-zero lineage through `v5_continue_after_gate.ps1` semantics.
- Preserve `hand_marker` actual-hand accounting exactly.
- Preserve current opponent assignment semantics; EXP-002 is batching/scheduling only.
- Keep old one-env path selectable for rollback and equivalence testing.
- Do not edit `train_v5.py` while the live trainer PID is running.

### GAE / Trajectory Contiguity Invariant (resolved 2026-07-07)

`train_mp3.py::compute_gae` operates on the flat transition buffer and assumes each
trajectory is contiguous until a `done=1` row resets bootstrap. EXP-002 may run many envs
per worker, but it must not interleave partial trajectories from different envs.

Required implementation shape:

1. Each env slot owns a private in-progress `hand_buffers` structure.
2. No transition from that hand is appended to the worker's outgoing transition list until
   the poker hand reaches terminal state.
3. At terminal state, the worker builds one completed-hand package and appends it
   atomically to `local_transitions`.
4. Within that package, each trainable player's trajectory is a contiguous sub-block, and
   each sub-block's final transition has `done=1`.
5. Exactly one terminal transition in the completed poker hand has `hand_marker=1.0`;
   all other transitions from the hand have `hand_marker=0.0`.
6. The main process may concatenate completed-hand packages from different workers/envs,
   but it must never concatenate incomplete per-env decision fragments.

Required assertion/test before cutover:

- Add a CPU unit/smoke assertion over a synthetic multi-env worker buffer:
  - every emitted trajectory sub-block terminates with `done=1`;
  - a new trajectory block starts only after a prior `done=1`;
  - each completed poker hand contributes exactly one `hand_marker=1.0`;
  - no transition package is emitted before terminal hand completion.
- Add a live smoke counter for the candidate path:
  `completed_hand_packages == sum(hand_marker)` over the emitted batch window.

This resolves the Fable blocker: multi-env may increase concurrency, but it must preserve
the flat-buffer GAE contract by buffering per env and emitting only completed hand
packages.

### Worker Seeding / M=1 Equivalence Gate (resolved 2026-07-07)

Chosen resolution: option (a), explicit per-worker seeds.

Required implementation shape:

1. Add a candidate-path seed plumbing parameter, e.g. `worker_seed_base`, derived from
   `args.seed`.
2. Pass deterministic `worker_seed = worker_seed_base + worker_id` into both the old
   one-env worker path and the new multi-env worker path during offline validation.
3. At worker start, seed all worker-local RNGs used by env/deal/action fallback code:
   Python `random`, NumPy, and torch if torch is imported in the worker.
4. For `M>1`, derive per-env streams deterministically, e.g.
   `env_seed = worker_seed + env_idx * 1_000_003`, so every env slot has a stable,
   non-overlapping deal stream.
5. Keep seeding explicit in the run manifest and train log for candidate runs.

Executable equivalence gate:

- Run old one-env path and candidate multi-env path with `M=1`, identical worker count,
  identical worker seeds, identical checkpoint, CPU device, epsilon `0`, and deterministic
  inference/action selection.
- Assert for at least 1,000 completed hands:
  - identical observation tensors (`card_info`, `action_info`, `extra_info`);
  - identical legal masks;
  - identical chosen actions and log/value rows at matched decision indices;
  - identical rewards, `done` positions, committed-chip bounds, and `hand_marker` count.
- Any mismatch is an EXP-002 offline validation FAIL. Do not cut over or relax this gate
  to "close enough" without re-registering the experiment.

This makes the registered M=1 equivalence gate executable without changing env semantics.

### Batching Accumulation Window (advisory blocker resolved 2026-07-07)

EXP-002 must not rely on "more slots exist" alone to create large inference batches. The
design requires both worker-side and main-side accumulation:

- Worker-side: a worker cycles all `M` env slots and writes every currently pending
  observation before it waits for any result. Status flags for the batch of slots are set
  only after their observation/request rows are written.
- Main-side: before running inference, the poll loop waits until either:
  - `waiting_slots >= inference_min_batch_slots`, or
  - `inference_batch_deadline_us` elapses since the first waiting slot was observed.
- Candidate defaults for the first scratch run: `M=16`, `inference_min_batch_slots=256`,
  `inference_batch_deadline_us=500-1000`. These are scratch-tuning values, not strength
  parameters.
- The adoption gate remains the ledger gate: candidate mean `inf_bs >= 300` and effective
  h/s ratio `>= 2.0` over the registered comparison window.

If the accumulation window causes deadlock, stale slots, action-mix drift, or h/s ratio
below gate after one tuning attempt, EXP-002 remains unlaunched/reverted per the ledger.

## Offline Validation Plan

Before cutover:

1. `python -m py_compile scripts\alpha_holdem\train_v5.py`
2. CPU smoke with old path:
   `python scripts\alpha_holdem\train_v5.py --device cpu --workers 1 --hands-per-iter 4 --total-hands 4 --ppo-epochs 1 --mini-batch-size 4 --snapshot-every 1 --save-interval 1 --run-dir tmp/exp002_single_smoke --run-id exp002_single_smoke --overwrite --max-runtime-seconds 120`
3. CPU smoke with `M=1` multi-env path; output should match the old path's structural invariants: checkpoint loads, actual hand count, status freshness, no crash.
4. CPU smoke with `M=2` or `M=4`; verify actual hands increase through `hand_marker`, no worker deadlock, no illegal action fallback spike, and no missing terminal transitions.
5. Fixed-seed trace/equivalence test for `M=1` using the explicit worker seeding plan
   above: same worker/env seed and action stream must produce identical observations,
   legal masks, actions, rewards, committed-chip bounds, `done` positions, and terminal
   accounting to the old path for at least 1,000 completed hands.
6. Scratch throughput A/B only when it will not contend with the live trainer. Do not run CUDA sweeps concurrently with PID `56876`.

After gate-boundary cutover:

1. Compare old and candidate with `v5_throughput_compare.py` using the ledger gate: h/s ratio >= `2.0`, candidate mean inf_bs >= `300`.
2. Require 3 post-cutover gate PASS results, no stderr incident, action-mix/rew100 guard bands, and no accounting or queue freshness drift.
3. Use EXP-001 mirrored eval at the next snapshot as the non-regression strength guard.
4. The next scheduled quick5k must not regress by more than `60 bb/100` versus the latest pre-change official quick screen.

## Current Status

As of the 2026-07-07 design update, the Fable launch blockers are resolved in design:
GAE trajectory contiguity is an explicit invariant/test requirement, the M=1 equivalence
gate uses explicit per-worker seeds, and the batching accumulation window is specified.
No EXP-002 trainer code has been landed, no cutover has launched, and the live run remains
on the old one-env worker path.
