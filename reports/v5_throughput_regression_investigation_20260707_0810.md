# V5 Throughput Regression Investigation - 2026-07-07 08:10 EDT

## Scope

Trigger: Ops log directive `2026-07-07 08:10 | FABLE DIRECTIVE: throughput regression investigation`.

Constraints followed:
- Non-invasive investigation only.
- Trainer PID 58680 left running.
- No trainer restart, watcher restart, Slumbot launch, code edit, or parameter change.
- Main run remains `fresh_from_zero_lineage=true`.

## Active State At Check

- Run dir: `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707`
- Trainer PID: 58680, responding.
- Dashboard status: checked `2026-07-07T12:09:53Z`.
- Live: iter 11342 / 186,103,128 hands in dashboard; latest log tail reached iter 11345 / 186,152,377 hands.
- Checkpoint: iter 11300 / 185,413,831 hands.
- Health: PASS.
- Gate: `gate_11400` PENDING, recommendation remains wait for `gate_11400`.
- External eval: `quick5k_200M` WAITING on checkpoint hands >= 200,000,000; dashboard remaining checkpoint hands 14,586,169.
- Latest official Slumbot evidence: inherited 150M quick5k greedy, 5,000 hands, -94.900 bb/100, 95% CI [-124.555, -65.246], L0 quick-screen only.

## Throughput Evidence

Parsed `latest_train.log`:

| Window | Iters | h/s mean | h/s median | h/s min/max | inf_bs mean | collect mean | ppo mean |
|---|---:|---:|---:|---:|---:|---:|---:|
| last30 | 11314-11343 | 378.3 | 323.5 | 256 / 615 | 12.1 | 46.8s | 6.0s |
| last60 | 11284-11343 | 389.3 | 334.0 | 256 / 615 | 12.3 | 45.3s | 5.8s |
| last120 | 11224-11343 | 383.8 | 338.0 | 256 / 644 | 11.7 | 45.4s | 5.5s |

Recent iterations alternate between high and low throughput rather than staying flat:
- 11339: 615 h/s, inf_bs 19.2, collect 26.7s, ppo 7.5s.
- 11341: 289 h/s, inf_bs 10.2, collect 56.9s, ppo 5.0s.
- 11342: 540 h/s, inf_bs 16.6, collect 30.4s, ppo 8.4s.
- 11345: 347 h/s, inf_bs 10.3, collect 47.3s, ppo 4.1s.

Dashboard still reports effective h/s 336.1 latest / 333.3 long at the 08:09 refresh.

## Process / Contention Evidence

Five-second Python CPU sample:

| Role | Count | Core share | Machine percent |
|---|---:|---:|---:|
| trainer_main | 1 | 0.965 | 3.0% |
| trainer_child | 22 | 1.312 | 4.3% |
| watcher | 9 | 0.000 | 0.0% |

No active mirror eval, Slumbot child, EXP-009 audit, CFR, teacher, or value-target process was found. The only Slumbot-related Python matches were the three waiting watcher processes:
- quick5k watcher PID 57424.
- promotion20k watcher PID 41432.
- formal100k watcher PID 27948.

All checked trainer/watcher stderr files were 0 bytes.

System process sample showed external Codex-triggered git indexing while this investigation was running:
- Multiple `git add -A` parent/child pairs.
- Parent processes: `Codex.exe` PID 50220 and `codex.exe` PID 25872.
- Two active git children consumed about 2.0 cores over a five-second sample.
- The git PIDs observed during the investigation started around 08:11-08:12 EDT, after the 08:10 directive, and appeared to respawn.

This git activity is a plausible current contributor through CPU and filesystem contention, but it does not prove the original 08:06-08:10 regression because the observed git processes started after the directive.

## Power / Thermal / GPU Evidence

- Active power plan: High performance.
- Processor state on AC: min 100%, max 100%.
- CPU counters over three samples:
  - `% Processor Performance`: avg 197.8.
  - `% of Maximum Frequency`: avg 100.0.
  - `% Processor Time`: avg 32.9.
- CPU WMI: Intel Core i9-14900F, 24 cores / 32 logical processors, load 44%, current/max clock reported as 2000/2000 MHz.
- Thermal-zone WMI query was unavailable / timed out, so CPU thermal status is not directly proven.
- GPU via `nvidia-smi`: RTX 4070, 26% utilization, 46 C, 26.75 W / 200 W, SM clock 1815 MHz, P5.

No power-plan, CPU-frequency, GPU-thermal, or GPU-power-limit evidence explains the regression.

## Verdict

Root-cause label: UNKNOWN.

Ruled out by this check:
- Active Slumbot or mirror-eval contention.
- Leftover EXP-009 audit/CFR/value-target processes.
- Watcher CPU load.
- Trainer or watcher stderr crash.
- Windows power plan falling out of High performance.
- GPU thermal/power throttling.

Suspected contributor, not confirmed root cause:
- Codex-triggered `git add -A` / workspace indexing was active during the investigation and consumed about 2 cores. This can contribute to CPU and filesystem contention, but the observed start times are after the 08:10 directive and therefore cannot be claimed as the confirmed cause of the earlier sustained h/s regression.

Trainer-internal observation:
- The log shows strong high/low iteration alternation with `inf_bs` and `collect` time moving together. This is consistent with the known S1 rollout bottleneck and per-iteration batching instability, but it is not a new behavior-affecting finding and does not justify intervention while EXP-004 is in its judgment window.

## Next

Continue training untouched and wait for `gate_11400`. Re-check throughput after Codex git activity clears and at the next gate boundary. Do not cut over EXP-002 or any speed change while EXP-004 step 1 is still in judgment.
