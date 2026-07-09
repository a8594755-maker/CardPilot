# V5 Throughput Follow-up - 2026-07-07 12:21 EDT

Scope: non-invasive follow-up on residual low throughput in
`models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707`.

No trainer, watcher, checkpoint, script, or Slumbot process was stopped/restarted.

## Current Training State

- Trainer PID: `58680`, alive, `Normal` priority.
- Run id: `v5_zero_l6_exp004_pre001_r1_20260707`.
- Latest dashboard: live iter/hands `11645` / `191,074,603`; checkpoint iter/hands
  `11600` / `190,336,141`; health `PASS`.
- Latest gate: `gate_11700` is `PENDING`; checkpoint remains `11600`.
- EXP-004 step-1 target: `195,491,565` checkpoint hands; remaining checkpoint hands
  `5,155,424`.
- EXP-002 cutover: not eligible; EXP-004 step-1 is unjudged and `gate_11700` is not PASS.

## Throughput Window

Parsed last 80 train-log rows through iter `11647`.

- h/s mean/median/min/max: `422.26` / `360` / `204` / `732`.
- inference batch mean/median/min/max: `11.86` / `10` / `9.5` / `18.5`.
- collect seconds mean/median/min/max: `42.23` / `45.1` / `22.5` / `80.4`.
- PPO seconds mean/median/min/max: `5.99` / `5.4` / `4.0` / `9.6`.
- entropy mean/median: `1.33` / `1.34`.
- KL mean/median/max: `0.05` / `0.05` / `0.1028`.

## Non-invasive System Check

- Non-empty run `*.err*` files: none observed.
- Active Slumbot/mirror/throughput children: none observed.
- GPU (`nvidia-smi`): RTX 4070, util `26%`, memory util `18%`, temperature `55 C`,
  power draw `38.23 W` / `200 W`, memory `4087 / 12282 MB`.
- Power plan: `High performance`; AC processor min/max `100% / 100%`.
- 5-second CPU delta sample:
  - `remoting_host` PID `7500`: `6.547` CPU seconds / 5 sec, about `1.309` cores.
  - trainer parent PID `58680`: `4.641` CPU seconds / 5 sec, about `0.928` cores.
  - Codex UI PIDs together: about `0.38` cores among top renderer/main processes.
  - Trainer worker children each used about `0.04-0.07` cores in the sample.

## Verdict

Root-cause status: `SUSPECTED` for the residual throughput gap.

The current evidence supports CPU-side contention as a live contributor: Chrome Remote
Desktop `remoting_host` is actively consuming about `1.31` cores while the trainer parent
is near one saturated core and GPU utilization remains low. There was no active git,
Slumbot, mirror-eval, EXP-009, or throughput-comparison child to explain the gap.

No intervention was taken. Continue training, keep eval jobs BelowNormal, avoid git/indexing
work during gate-critical windows, and re-check after `gate_11700` or before EXP-004
judgment if throughput remains depressed.
