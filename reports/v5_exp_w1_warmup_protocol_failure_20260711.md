# EXP-W1 Warmup Protocol Failure

Checked: 2026-07-11T16:40:00Z

EXP-W1 is terminal `EXP_W1_FAIL_WARMUP_GATE`. The immutable v3 design lock required at least 2% relative held-out value MSE reduction. Treatment achieved only 0.6853678% (`0.0068536781 < 0.02`). Policy logits remained bitwise unchanged, non-value model and optimizer state remained unchanged, and the value head changed as intended.

The trainer therefore executed the registered `ABORT_BEFORE_NORMAL_PPO` action. It completed zero normal PPO iterations and produced no valid treatment endpoint. The saved treatment checkpoint is preserved only as `ABORTED_WARMUP_CHECKPOINT_NO_ENDPOINT_AUTHORITY`.

Treatment fixed20M, primary100k, promotion20k, formal100k, and every Slumbot launch are forbidden. Tier-2 is frozen under `FREEZE_TIER2_NO_2_7B_INERTIA`. Official strength remains L0: 20,400 greedy-direct hands, -153.3 bb/100, 95% CI [-187.695, -118.905].

