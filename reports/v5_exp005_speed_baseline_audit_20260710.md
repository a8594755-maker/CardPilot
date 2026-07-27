# V5 Throughput Audit

> Generic tail audit only; not authoritative for the EXP-005 fixed-window gate.
> Use `reports/v5_exp005_speed_diagnosis_20260710.md/json`.

- Checked at: `2026-07-10T18:54:08.443129+00:00`
- Run: `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_r1_20260709`
- Overall: **WARN**
- Decision: **CONTINUE_WITH_THROUGHPUT_WARN**
- Workers / hands_per_iter / minibatch: `22` / `16384` / `1024`
- Device: `cuda`

## Latest Window

- Rows: `1216` iterations `30236` to `31451`
- Reported collect h/s mean: `3850.2`
- Effective h/s mean: `1503.3`
- Effective h/s p50 / p90: `1534.7` / `1770.5`
- Trainable decisions/sec mean: `10181.9`
- Inference batch size mean / p50: `183.85` / `163.7`
- Collect seconds mean: `4.37`
- PPO seconds mean: `6.84`
- PPO share mean: `0.6`

## Longer Window

- Rows: `1216` iterations `30236` to `31451`
- Effective h/s mean: `1503.3`
- Inference batch size mean: `183.85`

## Batch Buckets

- Fast bucket threshold inf_bs: `18.0`
- Fast fraction: `1.0`
- Fast effective h/s mean: `1503.3` over `1216` rows
- Slow effective h/s mean: `None` over `None` rows

## GPU Snapshot

- GPU snapshot unavailable: `True`

## Checks

- PASS: `sample_rows` - latest window rows 1216 >= 60
- PASS: `effective_hps` - effective h/s 1503.3 >= 800.0
- WARN: `ppo_share` - PPO takes 60.0% of collect+PPO time
- PASS: `inference_batching` - mean inf_bs 183.85
- WARN: `gpu_utilization` - nvidia-smi unavailable: None

## Recommendations

- PPO time is a meaningful share of wall clock; test larger hands_per_iter or larger mini_batch_size in a separate short sweep before changing the live run.

## Notes

- reported_collect_hps is the trainer log h/s and excludes PPO time.
- effective_hps uses iteration_hands / (collect_seconds + ppo_seconds), so it is closer to wall-clock throughput.
- This is an engineering throughput audit only; it does not prove model strength, Slumbot progress, L5, or L6.
