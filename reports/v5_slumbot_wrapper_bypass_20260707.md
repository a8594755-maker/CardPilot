# V5 Slumbot Wrapper Bypass - 2026-07-07

## Scope

This is a monitoring/evaluation workflow change only. It does not change trainer
weights, trainer flags, environment semantics, policy mode, or the official greedy
Slumbot evaluation contract.

Active run at patch time:

- run_id: `v5_zero_l6_exp004_pre001_r1_20260707`
- trainer PID: `58680` (left running)
- checkpoint at restart: `11000` / `180,491,565` hands
- next official eval: `quick5k_200M`, still waiting

## Reason

The 150M quick5k incident had two wrapper-launched attempts stall with zero
hand/dump bytes while direct `play_slumbot.py` launches completed. The root cause
of that incident remains `UNKNOWN`; the wrapper is suspected, not proven.

Before `quick5k_200M`, the Slumbot benchmark watcher was changed to bypass
`bench_v55_slumbot.ps1` by default and launch direct Python child sessions.
The wrapper path is retained as rollback via `--launch-path wrapper`.

## Implementation

Patched file:

- `scripts/alpha_holdem/v5_slumbot_benchmark_watch.py`

Behavior:

- Default `--launch-path direct`.
- Direct path launches `play_slumbot.py` child processes directly with the same
  artifact names as the wrapper:
  - `bench_v55_<tag>_part{i}.json`
  - `bench_v55_<tag>_part{i}_hands.jsonl`
  - `bench_v55_<tag>_part{i}_dump.jsonl`
- Child stdout/stderr are sent to `DEVNULL` to avoid the wrapper's redirected
  file-handle path. The watcher writes its own direct launcher log.
- Child processes are set to `BelowNormal` priority on Windows unless
  `--no-direct-low-priority` is passed.
- Direct path has a zero-output stall guard:
  `--direct-stall-timeout-seconds` defaults to `600`.
- After children exit, the watcher runs the same evidence bundle builders:
  exact CI, promotion gate, dump analysis, loss report, artifact audit,
  hand review, and selector replay when eligible.

## Validation

Completed before watcher restart:

- `python -m py_compile scripts\alpha_holdem\v5_slumbot_benchmark_watch.py`:
  PASS.
- Preflight-only watcher check:
  - tag: `v5_direct_bypass_preflight_20260707`
  - status: `PREFLIGHT_ONLY_PASS`
  - checkpoint freeze: `models\bench_v55_v5_direct_bypass_preflight_20260707_checkpoint.pt`
  - preflight JSON: `models\bench_v55_v5_direct_bypass_preflight_20260707_preflight.json`
  - no Slumbot hands launched.
- Direct launcher 0-hand smoke:
  - output dir: `tmp\v5_direct_launcher_zero_hand_smoke_20260707`
  - child PID `37300` exited `0` at `BelowNormal`
  - watcher result was expected `FAIL` because hand/dump JSONL files were empty
  - no Slumbot hands launched.

No `play_slumbot.py` child process was running after validation.

## Watcher Stop/Restart

Stopped before patch:

- quick5k watcher PID `42112`
- promotion20k watcher PID `22012`
- formal100k watcher PID `22004`

Restarted after patch, all `--launch-path direct`, all `BelowNormal`:

- quick5k watcher PID `57424`
- promotion20k watcher PID `41432`
- formal100k watcher PID `27948`

Status after restart:

- `slumbot_quick5k_launch_status.json`: `WAITING`, `launch_path=direct`,
  `min_training_hands=200000000`
- `slumbot_promotion20k_launch_status.json`: `WAITING`, `launch_path=direct`,
  `min_training_hands=250000000`
- `slumbot_formal100k_launch_status.json`: `WAITING`, `launch_path=direct`,
  `min_training_hands=250000000`

No `play_slumbot.py` child was running after restart.

## Rollback

Use `--launch-path wrapper` on `v5_slumbot_benchmark_watch.py` to restore the
previous PowerShell wrapper launch behavior. Do not do this for `quick5k_200M`
unless direct path fails for a new, documented reason.
