# V5 Slumbot Benchmark Contract

Generated: 2026-07-03

## Purpose

This contract defines how V5 checkpoints may be evaluated against Slumbot.
Training health alone never proves Slumbot success. A Slumbot claim must be
based on saved benchmark artifacts that can recompute bb/100 and the 95% CI
from per-hand rewards.

## Tools

- `scripts/alpha_holdem/play_slumbot.py`
  - plays one Slumbot session
  - now supports `--result-json`
  - now supports `--hand-results-jsonl`
  - writes exact per-hand rewards for CI audit
- `scripts/alpha_holdem/slumbot_ci_from_hands.py`
  - recomputes bb/100 and 95% CI from one or more per-hand JSONL files
  - reports L1-L6 milestone status from the saved hand records
  - reports L5 blockers when the formal win gate is not met
  - reports delta versus the current V4/BC-anchor baseline
  - expands glob patterns itself for Windows/PowerShell reliability
  - accepts UTF-8 with or without BOM
- `scripts/alpha_holdem/bench_v55_slumbot.ps1`
  - launches parallel Slumbot sessions
  - now writes per-session JSON and per-hand JSONL
  - now runs the exact CI summarizer after aggregation
  - now runs the V5 promotion gate evaluator after CI summary exists
- `scripts/alpha_holdem/v5_slumbot_benchmark_plan.py`
  - read-only benchmark planner; it does not call Slumbot
  - checks checkpoint metadata, from-zero lineage, health freshness, planned
    benchmark hand count, output tag collisions, and minimum training hands
  - emits the exact `bench_v55_slumbot.ps1` command only as a gated plan
- `scripts/alpha_holdem/v5_slumbot_plan_watch.py`
  - read-only watcher around the benchmark planner
  - periodically refreshes plan JSON/Markdown
  - exits READY/READY_WITH_WARNINGS when the requested stage is eligible
  - treats training-hand and missing-checkpoint waits as recoverable, but exits
    on hard metadata, health, or output-collision failures
- `scripts/alpha_holdem/v5_slumbot_promotion_gate.py`
  - consumes checkpoint metadata, `health_status.json`, CI JSON, and
    per-hand artifact references
  - outputs 20k promotion, formal L5, and formal L6 decisions
  - refuses claims if required hand artifacts are missing

## Required Artifacts

Every promotion or claim benchmark must retain:

- raw stdout log per session
- stderr log per session
- `result-json` per session
- `hand-results-jsonl` per session
- combined CI JSON from `slumbot_ci_from_hands.py`
- command line, checkpoint path, checkpoint metadata, and timestamp

Console text alone is not sufficient evidence.

## Promotion Benchmark

The first Slumbot promotion check is 20k+ hands, not a final win claim.
Before running it, generate a readiness plan:

```powershell
python scripts\alpha_holdem\v5_slumbot_benchmark_plan.py `
  --run-dir models\alpha_holdem_v5_from_zero\<run> `
  --stage promotion20k `
  --out-json models\alpha_holdem_v5_from_zero\<run>\slumbot_plan_promotion20k.json `
  --out-md models\alpha_holdem_v5_from_zero\<run>\slumbot_plan_promotion20k.md
```

Default gate for `promotion20k`:

- checkpoint must be loadable
- checkpoint metadata must be V5 fixed-env: `v5.zero`, `v55`, `9slot_v5`,
  200bb, `actual_hand_accounting=True`
- checkpoint must belong to the V5-from-zero lineage
- health must be PASS/WARN and fresh
- checkpoint training hands must be at least 250M unless an explicit
  `--allow-early` override is used
- generated output tag must not collide with retained artifacts

For long runs, the planner can be watched without starting Slumbot:

```powershell
python -u scripts\alpha_holdem\v5_slumbot_plan_watch.py `
  --run-dir models\alpha_holdem_v5_from_zero\<run> `
  --stage promotion20k `
  --poll-seconds 1800 `
  --out-json models\alpha_holdem_v5_from_zero\<run>\slumbot_plan_promotion20k.json `
  --out-md models\alpha_holdem_v5_from_zero\<run>\slumbot_plan_promotion20k.md `
  --log-path models\alpha_holdem_v5_from_zero\<run>\slumbot_plan_promotion20k_watch.log
```

This watcher must not be confused with a benchmark runner. It only emits the
command and readiness evidence.

Command pattern:

```powershell
.\scripts\alpha_holdem\bench_v55_slumbot.ps1 `
  -ModelPath models\alpha_holdem_v5_from_zero\<run>\latest.pt `
  -Tag v5_<checkpoint_tag> `
  -HandsPerSession 1700 `
  -Sessions 12
```

Promotion requires:

- checkpoint metadata is V5 fixed-env: `v5.zero`, `v55`, 200bb,
  `actual_hand_accounting=True`
- training health is PASS/WARN with no hard FAIL
- benchmark is 20k+ successful Slumbot hands
- result is clearly better than current best baseline
- no claim of "beat Slumbot" unless the 100k CI gate also passes

## Formal L5 Gate

The formal "beat Slumbot" gate requires:

- 100,000+ successful Slumbot hands
- `bb_per_100 > 0`
- `lower_bound_bb_per_100 > 0`
- all required artifacts retained
- checkpoint evaluated without online learning or live CFR search

The authoritative computation is:

```powershell
python scripts\alpha_holdem\slumbot_ci_from_hands.py `
  models\bench_v55_<tag>_part*_hands.jsonl `
  --out-json models\bench_v55_<tag>_ci_summary.json
```

The output JSON records the exact input files consumed. This is required for
auditing a 100k+ hand claim.

## Milestone Classifier

`slumbot_ci_from_hands.py` now maps exact per-hand results onto the project
milestone ladder:

- `L0`: below current baseline band
- `L1`: `bb/100 >= -50`
- `L2`: `bb/100 >= -25`
- `L3`: `bb/100 >= -10`
- `L4`: `bb/100 > 0`, but formal CI gate may not be proven
- `L5`: `hands >= 100000`, `bb/100 > 0`, and
  `lower_bound_bb_per_100 > 0`
- `L6`: L5 plus near-paper target, default `bb/100 >= 11.1 - 2.0`

The JSON also records:

- `l5_blockers`
- `baseline_bb_per_100`
- `baseline_delta_bb_per_100`
- `baseline_point_estimate_improved`
- `baseline_ci_lower_above_baseline`

Verification performed without Slumbot API calls:

```powershell
python -m py_compile scripts\alpha_holdem\slumbot_ci_from_hands.py
```

An inline functional check covered representative deterministic samples for
L0, L1, L2, L3, L4, L5, and L6.

## Promotion Gate Evaluator

After a benchmark CI JSON exists, promotion decisions should be audited with:

```powershell
python scripts\alpha_holdem\v5_slumbot_promotion_gate.py `
  --checkpoint models\alpha_holdem_v5_from_zero\<run>\latest.pt `
  --run-dir models\alpha_holdem_v5_from_zero\<run> `
  --ci-json models\bench_v55_<tag>_ci_summary.json `
  --out-json models\bench_v55_<tag>_promotion_gate.json `
  --out-md models\bench_v55_<tag>_promotion_gate.md
```

The evaluator checks:

- checkpoint is V5 fixed-env and 200bb
- checkpoint belongs to the V5-from-zero lineage
- training health is not failed
- CI JSON is readable
- every per-hand JSONL file listed in `input_files` exists
- 20k promotion candidate status
- formal L5 claim status
- formal L6 claim status

Verification performed without Slumbot API calls:

- syntax check passed
- positive fixture produced PASS/L6 using a local V5 lineage checkpoint and
  retained hand artifact
- negative fixture with a missing per-hand artifact produced FAIL and blocked
  promotion/L5/L6 decisions even though the CI JSON claimed L6
- `bench_v55_slumbot.ps1` PowerShell parser check passed after wiring this
  evaluator into the benchmark completion flow

## L6 Gate

The L6 target is near the AlphaHoldem paper claim:

- target: approximately `+11.1 bb/100`
- still requires 100k+ hands and positive 95% CI lower bound
- result must be reported with the exact confidence interval

Do not report L6 from:

- training reward
- self-play winrate
- 2k or 20k noisy Slumbot samples
- rough CI estimates from session averages
- benchmarks missing per-hand rewards

## Current V5 Status

Current active run:

- `models/alpha_holdem_v5_from_zero/v5_zero_l6_fixedenv_20260703_1445`

Current training status, checked at 2026-07-04 04:35 EDT:

- training process is still running
- latest observed live iteration: 1526
- latest observed hands: 25,038,803
- monitor status: PASS
- latest checkpoint iteration: 1500
- checkpoint pool snapshots: 5
- current checkpoint pool hands:
  `[9843678, 13125578, 16407558, 19689242, 22971150]`
- next checkpoint/pool replacement gate: iteration 1600, expected stored pool
  snapshots 5 because latest-K is capped at K=5
- strict gate watcher is running
- non-destructive post-gate dry-run watcher is running

Current benchmark status:

- no Slumbot benchmark has been run for this V5 checkpoint line
- no L5 or L6 claim is allowed
- next Slumbot action is a promotion benchmark only after a checkpoint is selected;
  training health gates alone cannot promote a champion

Updated training status, checked at 2026-07-04 04:46 EDT:

- training process is still running, PID 39172
- latest observed live iteration: 1540
- latest observed hands: 25,268,504
- monitor status: PASS
- latest checkpoint iteration: 1500
- checkpoint hands: 24,612,143
- checkpoint pool snapshots: 5
- current checkpoint pool hands:
  `[9843678, 13125578, 16407558, 19689242, 22971150]`
- gate 1600 remains PENDING with ETA about 46 minutes
- recent throughput: 359.4 hands/sec
- latest inference batch size: 5.2

Benchmark status remains unchanged:

- no Slumbot benchmark has been run for this V5 checkpoint line
- no L5 or L6 claim is allowed
- the next valid benchmark action is after selecting a checkpoint that has
  passed training health and metadata gates
