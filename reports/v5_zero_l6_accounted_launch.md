# V5 Zero L6 Accounted Launch Report

Generated: 2026-07-03 13:55 EDT

## Active Run

- Run id: `v5_zero_l6_accounted_20260703_1352`
- Run dir: `models/alpha_holdem_v5_from_zero/v5_zero_l6_accounted_20260703_1352`
- Trainer: `scripts/alpha_holdem/train_v5.py`
- Monitor: `scripts/alpha_holdem/v5_monitor.py`
- Mode: fresh random initialization, no resume
- Target: L6, approximately +11.1 bb/100 versus Slumbot
- Formal win gate: 100k+ Slumbot hands, bb/100 > 0, 95% CI lower bound > 0
- Total training target: 2.7B actual poker hands

## Why This Replaced the 13:46 Run

The earlier run `v5_zero_l6_20260703_1346` was stopped at about 444k logged hands and marked deprecated because the initial V5 accounting counted terminal player trajectories as hands. With both-player self-play collection, that can over-count actual poker hands.

The corrected run uses a per-hand marker in each worker so `total_hands` is actual poker hands. The log records terminal player trajectories separately as `terms=`.

## Launch Command

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
  --run-id v5_zero_l6_accounted_20260703_1352 `
  --run-dir models\alpha_holdem_v5_from_zero\v5_zero_l6_accounted_20260703_1352
```

## Initial Health Check

Monitor command:

```powershell
python scripts\alpha_holdem\v5_monitor.py --run-dir models\alpha_holdem_v5_from_zero\v5_zero_l6_accounted_20260703_1352
```

Initial monitor result:

- overall: PASS
- iteration: 12
- actual hands: 196,800
- terminal trajectories: 28,100 on the latest iteration
- entropy: 1.2777
- value loss: 5,427.9
- hands/sec: 1,359 actual hands/sec on latest iteration
- pool size: 0, expected before first snapshot
- stderr: empty
- process state: 1 parent + 28 worker processes

## Next Gates

- Iteration 100: first `latest.pt` save. **PASSED** at 1,640,600 actual hands.
- Iteration 200: first pool snapshot. **PASSED** at 3,281,200 actual hands.
- Health monitor should stay PASS/WARN only; FAIL requires immediate intervention.
- 250M-500M actual hands: first meaningful Slumbot milestone candidate, subject to training health.
- L6 requires near +11.1 bb/100 versus Slumbot with a meaningful sample.

## First Checkpoint Gate

Verified at 2026-07-03 14:18 EDT:

- `latest.pt` exists and loads with `torch.load`
- checkpoint version: `v5.zero`
- checkpoint run id: `v5_zero_l6_accounted_20260703_1352`
- checkpoint total hands: 1,640,600 actual poker hands
- checkpoint iteration: 100
- checkpoint pool snapshots: 0, expected before iteration 200
- checkpoint resume source: `None`
- checkpoint L6 target metadata: approximately +11.1 bb/100 vs Slumbot

Latest monitor after save:

- overall: PASS
- iteration: 104
- actual hands: 1,706,200
- entropy: 1.0180
- value loss: 1,653.2
- hands/sec: 1,835
- stderr: empty

## First Opponent-Pool Gate

Verified at 2026-07-03 14:32 EDT:

- iteration 200 checkpoint exists and loads
- checkpoint total hands: 3,281,200 actual poker hands
- checkpoint pool snapshots: 1
- first pool snapshot hand count: 3,281,200
- iteration 201+ log shows `pool=1`, so historical-opponent self-play is active

Latest monitor after pool activation:

- overall: PASS
- iteration: 203
- actual hands: 3,330,406
- entropy: 0.9264
- value loss: 4,109.8
- hands/sec: 1,214
- pool size: 1
- stderr: empty

Observation:

Throughput dropped after pool activation because inference now batches by hero and pool model separately. That is expected; monitor should track whether it remains stable rather than comparing it directly to pre-pool throughput.
