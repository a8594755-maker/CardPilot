# V5 Zero L6 Launch Report

Generated: 2026-07-03 13:48 EDT

Status update: **SUPERSEDED / DEPRECATED**.

This 13:46 run (`v5_zero_l6_20260703_1346`) was stopped at about 444k logged hands because the initial V5 accounting counted terminal player trajectories as hands under both-player collection. It is preserved for audit only. The active corrected run is documented in `reports/v5_zero_l6_accounted_launch.md`.

## Run

- Run id: `v5_zero_l6_20260703_1346`
- Run dir: `models/alpha_holdem_v5_from_zero/v5_zero_l6_20260703_1346`
- Trainer: `scripts/alpha_holdem/train_v5.py`
- Mode: fresh random initialization, no resume
- Target: L6, approximately +11.1 bb/100 versus Slumbot
- Total hands target: 2.7B

## Command

```powershell
python scripts\alpha_holdem\train_v5.py `
  --device cuda `
  --workers 28 `
  --hands-per-iter 16384 `
  --total-hands 2700000000 `
  --starting-stack 200 `
  --lr 3e-4 `
  --gamma 0.999 `
  --delta1 3.0 `
  --entropy-coef 0.05 `
  --entropy-floor 0.3 `
  --k-best 5 `
  --self-play-fraction 0.2 `
  --snapshot-every 200 `
  --save-interval 100 `
  --run-id v5_zero_l6_20260703_1346 `
  --run-dir models\alpha_holdem_v5_from_zero\v5_zero_l6_20260703_1346
```

## Artifacts

- `init.pt`: random-init checkpoint proving the run did not start from V4/BC/CFR
- `run_manifest.json`: run config, goal, paper reference, Slumbot target, current status
- `latest_train.log`: per-iteration training health log
- `latest.pt`: first written at save interval 100, then updated every 100 iterations
- `console.out.log` / `console.err.log`: detached process stdio

## Initial Health Check

At iteration 5:

- total hands: 82,123
- value loss: 4,148.25
- entropy: 1.237
- reward window: -0.080
- hands/sec: ~2,038
- trainable decisions/sec: ~2,899
- stderr: empty
- process state: 1 parent + 28 workers alive

This is a valid from-zero launch. Early high value loss is expected at random initialization in 200bb HUNL; the immediate gate is "not exploding and entropy not collapsing", not Slumbot performance.

## Next Gates

- Iteration 100: first `latest.pt` save.
- Iteration 200: first opponent-pool snapshot.
- 250M-500M hands: first meaningful Slumbot checkpoint candidate, unless training health fails earlier.
- Promotion requires a Slumbot 20k result clearly above the current baseline.
- L6 requires near +11.1 bb/100 versus Slumbot with a meaningful sample; formal win claim still requires 100k+ hands with 95% CI lower bound > 0.
