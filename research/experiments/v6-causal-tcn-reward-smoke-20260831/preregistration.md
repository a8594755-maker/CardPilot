# Causal temporal-convolution sequence reward smoke

The flat-sequence matched pilot produced a positive but highly uncertain aggregate
treatment-control contrast and only2/5 positive anchor directions, including a
large loss on source anchor0. Flat capacity is rejected. Earlier attention residuals
also failed backend stability. This final sequence-residual architecture test changes
the inductive bias rather than extending either failed endpoint.

Integrate a causal ordered-token residual into production network/trainer/loader:
project each of25 action-history tokens from20 to128 features, apply three causal
Conv1d+ReLU layers with kernel3 and dilations1,2,4 using left padding only, take the
current token, concatenate frozen normalized256-wide trunk state and seat one-hot,
then route through two seat-specific386->128->9 zero-output experts. Exactly18 new
actor parameter tensors. Add causal-sequence-adapter-only training that freezes the
source actor and updates these18 tensors plus critic. Source-reference reconstruction
zeros missing causal tensors and must preserve Standard10 behavior exactly.

After admission/regression/parity tests, run one fixed fresh v6 PPO smoke from legacy
Standard10 SHA256 91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428:
at least32768 physical hands, reset optimizer/counters, workers12/multi8,
seed20261035/worker2026103500, fixed deal stream, five fixed anchors, adaptive league,
sampled hero/selfplay0.25, lr3e-5, PPO2, target-KL0.01, advantage clip3, source
KL0.01 and entropy0.005/floor0.05. No replay, continuation or endpoint selection.

Require physical/session/model/optimizer/frozen-source scope and checkpoint-loader
audits. Freeze final and evaluate against untouched v6 source anchor0 on4096 mirrored
pairs seed20261036. Smoke passes only if raw point estimate>-20bb/100 and all health
gates pass. A pass only admits a matched scale experiment; it is not external strength.
Failure ends sequence-residual variants and redirects to centralized-critic/EMA
actor-critic work. Slumbot hands=0.
