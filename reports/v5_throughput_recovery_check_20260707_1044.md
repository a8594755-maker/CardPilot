# V5 Throughput Recovery Check - 2026-07-07 10:44 EDT

Scope: non-invasive follow-up to the 08:25 throughput regression root-cause/fix Ops row.
No trainer, watcher, Slumbot, mirror-eval, or script process was stopped, restarted, or edited.

## Current Run

- Run dir: `models/alpha_holdem_v5_from_zero/v5_zero_l6_exp004_pre001_r1_20260707`
- Trainer PID: `58680`
- Dashboard checked_at: `2026-07-07T14:43:33.072587+00:00`
- Live iter/hands: `11529` / `189,171,042`
- Checkpoint iter/hands: `11500` / `188,695,377`
- Health: `PASS`
- Dashboard effective h/s: latest `351.3`, long `345.7`

## Log Window

Parsed `latest_train.log` through iter `11531` / `189,203,855` hands.

| window | iter range | h/s mean | h/s median | h/s min | h/s max | inf_bs mean | collect mean | ppo mean |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| last30 | 11502-11531 | 406.5 | 386.0 | 261.0 | 686.0 | 11.4 | 42.5s | 6.1s |
| last10 | 11522-11531 | 372.0 | 336.0 | 261.0 | 525.0 | 12.1 | n/a | n/a |
| last5 | 11527-11531 | 392.4 | 336.0 | 272.0 | 525.0 | 12.6 | n/a | n/a |

Recent individual rows include iter `11529` at `495 h/s` and iter `11530` at `525 h/s`,
but the rolling windows remain below the pre-regression ~600 h/s expectation.

## Process / GPU Check

- No active `git.exe` process was observed in the sampled top-process list.
- No active `play_slumbot.py`, `v5_mirror_eval.py`, or EXP-009 child was observed.
- Waiting Slumbot watchers remain below active launch thresholds.
- GPU sample via `nvidia-smi`: utilization `37%`, temperature `51 C`, power `22.06 W`,
  memory `3916 / 12282 MiB`.
- Residual visible CPU consumers include `remoting_host.exe`, Codex UI/app processes, and
  the expected trainer + worker Python processes.

## Verdict

Throughput is partially recovered versus the 08:12 incident-review window
(`last30 median 323.5 h/s` then, `386.0 h/s` now), but not recovered to the older
~600 h/s baseline. Root cause remains the 08:25 confirmed multi-factor CPU contention
finding; the dominant git-churn component appears absent in this check. Continue
monitoring through the next gate and do not perform a trainer restart for this alone.
