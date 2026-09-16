# Flat-sequence production reward-training smoke

The backend-stable flattened action-sequence residual improved known-cohort teacher
fidelity but its one fixed continuation stopped at heroTV0.152080, above the0.15
development gate. No supervised endpoint is promoted. The useful architectural
signal is now tested in actual v6 PPO environment learning from the stronger frozen
Standard10 source SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.

Integrate a production flat-sequence residual into network_hybrid_h1, train_v5,
v5_mirror_eval/execution_v6 and checkpoint reconstruction. The model adds a
500->512->256 ReLU action encoder, LayerNorm on frozen 256-wide trunk state, and two
seat-specific 514->128->9 residual experts with zero-output initialization. Add a
flat-sequence-adapter-only mode that freezes every source actor tensor and trains
exactly the14 new sequence tensors plus the critic. Source-reference construction
must materialize absent sequence tensors at zero and preserve exact source behavior.

After unit/admission tests, run one fresh v6 migration from Standard10 with reset
optimizer/counters for at least32768 physical environment hands: workers12,
multi8, hands-per-iter4096, seed20261031, worker seed2026103100, lr3e-5, PPO2,
target-KL0.01, advantage clip3, source KL0.01, entropy0.005/floor0.05, sampled hero,
self-play0.25 and the same three frozen learned anchors used by the prior corrected-v6
control. No replay. Save every update and audit the terminal session.

Smoke passes only if physical accounting/session audit, source-behavior zero-init,
checkpoint reconstruction, finite optimizer/model state, frozen-source actor scope,
and full raw internal evaluation evidence pass. Evaluate the frozen endpoint versus
the frozen source on4096 fresh mirrored pairs with seed20261032. The contrast is
descriptive; pass requires its point estimate above -20bb/100, along with finite PPO
health and no gate violation. A pass only admits a separately preregistered matched
262144-hand architecture pilot. It is not external or Slumbot strength evidence.
