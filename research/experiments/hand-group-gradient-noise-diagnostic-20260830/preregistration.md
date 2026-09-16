# Fixed-weight whole-hand gradient-noise diagnostic

Parent independent confirmation failed its prespecified general-improvement gate. This mechanism experiment does not promote or re-evaluate that checkpoint.

## Cohorts

- Source: original frozen Standard10, seed20260895, worker seed2026089500; fresh Adam and new local counter.
- Mature: unchanged1M final SHA256 `ddab8c71090a78346bbd9b2b425fd3676a2d6c1cd30e649fa95aab1ff06fa7a3`, seed20260896, worker seed2026089600; retain Adam moments/step6048, reset only new-experiment local counter.
- Both: physical target16384, checked at PPO boundaries (expected approximately4 updates, report overshoot).4096 decision-bearing marker hands per collection, minibatch1024,2 PPO epochs,lr3e-5,sourceKL1,advantage clip3,entropy.005/floor.05,critic_v2,all policy/value heads only,3 unchanged fixed anchors/adaptive league,25% self-play,12 workers,single rollouts,archive each iteration.1800-second guard per cohort; no automatic restart/overwrite. See exact generated commands in record and run_cohorts.py.
- Different weights, Adam/league histories and seeds make comparisons descriptive, not a randomized causal model-age experiment. All new physical terminal hands are counted; source lineage beyond the new local prefix is not claimed as fresh work.

## Probe definition

Before any minibatch update, split using the existing tested `split_complete_hand_blocks`. A marked first trajectory and optional unmarked second self-play trajectory stay together. Deterministically shuffle whole-hand indices with a private NumPy generator seed20260897;16 disjoint equal-hand groups, remainder excluded from probes only, never from actual PPO.

For selected N transitions and K groups, each group differentiates its **sum** of row losses divided by N/K. This gives equal-hand estimates while retaining the transition-weighted objective despite variable rows per hand. Advantages retain the unchanged full-batch normalization/clipping. Compute PPO,weighted source-KL,and entropy head gradients at fixed weights; construct regularized actor gradients with one entropy coefficient determined by the selected full-batch mean. No optimizer step, backward into .grad, model/RNG mutation, or production objective change. Unsupported moving-statistic/dropout/auxiliary-policy configurations fail explicitly.

Store per-group hand indices/lengths/counts and their SHA256, and float64 Gram matrices for all-actor,postflop-head and preflop-head gradients. The Gram matrices are sufficient to recompute the reported covariance and agreement statistics without retaining all raw gradient vectors.

For gradient estimates g_i, report mean squared norm, sample covariance trace S, and descriptive signal estimate ||mean(g)||^2-S/K. Noise/signal is S divided by a positive resolved signal; otherwise report null/unresolved. Also report pairwise cosine and positive-dot fractions. The units of the simple scale are decision-bearing hands per group, not physical hands or optimizer minibatch rows.

## Decision fixed before cohort execution

Admission to one bounded optimizer-batch treatment requires all-actor PPO noise/signal>1, or nonpositive/unresolved signal **with positive covariance**, in at least75% of updates in **each** cohort. An identically zero gradient is flat, not evidence of noise. This pre-execution clarification prevents a zero/zero numerical case from admitting a batch treatment. Always report the actor and individual heads too. If the gate fails, do not infer small-batch noise as the main mechanism. If it passes, choose and preregister a bounded batch treatment with explicit Adam-step/LR tradeoffs and independent poker evaluation; do not jump to paper scale.

The simple-noise-scale motivation comes from [McCandlish et al.](https://arxiv.org/html/1812.06162); its assumptions do not establish poker improvement or an optimal batch size here. Full-batch advantage normalization and adaptive league dependence limit IID interpretations. [Merrill et al.](https://arxiv.org/html/2505.23971v1) motivates empirical validation rather than treating a noise proxy as an automatic prescription. Neither paper substitutes for local evidence.

## Verification

27 tests passed before execution: whole-hand boundaries,private-RNG preservation,known Gram arithmetic,zero-versus-unresolved distinction,full-gradient weighting oracle,dropout rejection,real PPO model/Adam/RNG bitwise equivalence,existing replay and physical-accounting tests. Initial test collection needed the same local module search path already used by existing train_v5 tests; fixed before production, no training failed. Full source snapshots/hashes are retained and checked around both cohorts. Exact commands, persisted physical counters, optimizer lineage and session audits are required before finish. No strength-evaluation or Slumbot hands occur in this diagnostic.
