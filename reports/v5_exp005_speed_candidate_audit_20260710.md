# V5 Throughput Audit

> Generic tail audit only; not authoritative for the EXP-005 fixed-window gate.
> Use `reports/v5_exp005_speed_diagnosis_20260710.md/json`.

- Checked at: `2026-07-10T18:54:08.567166+00:00`
- Run: `v5_zero_l6_exp004_pre001_exp002_multienv_exp003_boundedk_exp005_pergroup5_r1_20260710`
- Overall: **WARN**
- Decision: **CONTINUE_WITH_THROUGHPUT_WARN**
- Workers / hands_per_iter / minibatch: `22` / `16384` / `1024`
- Device: `cuda`

## Latest Window

- Rows: `60` iterations `31492` to `31551`
- Reported collect h/s mean: `2588.7`
- Effective h/s mean: `1426.2`
- Effective h/s p50 / p90: `1199.0` / `1928.7`
- Trainable decisions/sec mean: `6818.0`
- Inference batch size mean / p50: `69.34` / `69.3`
- Collect seconds mean: `6.95`
- PPO seconds mean: `5.37`
- PPO share mean: `0.441`

## Longer Window

- Rows: `144` iterations `31408` to `31551`
- Effective h/s mean: `1812.2`
- Inference batch size mean: `69.27`

## Batch Buckets

- Fast bucket threshold inf_bs: `18.0`
- Fast fraction: `1.0`
- Fast effective h/s mean: `1426.2` over `60` rows
- Slow effective h/s mean: `None` over `None` rows

## GPU Snapshot

- GPU snapshot unavailable: `True`

## Checks

- PASS: `sample_rows` - latest window rows 60 >= 60
- PASS: `effective_hps` - effective h/s 1426.2 >= 800.0
- WARN: `ppo_share` - PPO takes 44.1% of collect+PPO time
- PASS: `inference_batching` - mean inf_bs 69.34
- WARN: `gpu_utilization` - nvidia-smi unavailable: None

## Recommendations

- PPO time is a meaningful share of wall clock; test larger hands_per_iter or larger mini_batch_size in a separate short sweep before changing the live run.

## Notes

- reported_collect_hps is the trainer log h/s and excludes PPO time.
- effective_hps uses iteration_hands / (collect_seconds + ppo_seconds), so it is closer to wall-clock throughput.
- This is an engineering throughput audit only; it does not prove model strength, Slumbot progress, L5, or L6.
