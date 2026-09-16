# Runtime-guard recovery 1

The original `run_training.ps1` session stopped cleanly because seed2 reached
the preregistered per-process `--max-runtime-seconds 14400` guard.  This is an
operational interruption, not a training failure and not the 4M endpoint.

Authoritative frozen recovery boundary:

- source: `recovery_sources/seed2_guard1_iter768_hands3163932_physical3619473.pt`
- source SHA256: `466b471fb404b89145e44a12e28c781ffc161f881f5b4cf4c5c3ba16fba9e77a`
- iteration: 768
- transition-bearing hands: 3,163,932
- completed physical environment hands: 3,619,473
- optimizer: preserved, 10 state entries, stored LR `1e-4`
- PPO replay: two serialized entries from iterations 767 and 768; RNG state
  present; cumulative rows 5,583,306
- assignment evidence: 769 contiguous rows; tail applies to iteration 769,
  `total_hands_before_iteration=3163932`, record SHA256
  `ffec7162a8079863b2f4a50f3d79bc5c34d238196396d42098754e17b020fdd5`
- active loss-kbest pool identity/order: `[0, 1, 2, 122, 206]`

`run_training_guard1_recovery.ps1` preserves the original training arguments,
seed, worker seed, deal-stream start, 4M physical target, optimizer, inherited
hand counter, serialized replay and assignment-provenance recovery.  It changes
only seed2's `--resume` path from the original 2M parent to the frozen guard
source.  It writes to the same seed2 output and evidence files so iteration 769
continues the existing chain.  After seed2 reaches the endpoint, it starts the
untouched staged seed3 from its frozen 2M parent using the original arguments.

No earlier hands, metrics, assignments or archives are deleted or regenerated.

