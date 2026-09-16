# Corrected-contract physical training smoke

Registered after native-rules-contract-repair-20260831 completed88tests and4096
fixed oracle hands/34159decision checks. This is a NEW v6 experiment, not a
resume/reset of any legacy experiment. It cannot qualify the100k external Goal.

## Fixed configuration

Start from original Standard10 frozen weights SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.
Explicitly rebind weights to hunl_v6_pot_fraction_chips_history_v1, with fresh
Adam, fresh iteration and physical-hand counters, new run identity and seeds.
Source bytes and all earlier evidence are immutable. Do not import old replay,
pool rewards or optimizer state. Three league anchor weight sets are explicitly
rebound artifacts (Standard10, slumbot_free457d...,corrected_cfr96902a...);
they are NOT the same executed policies as under the old contract.

One full-network arm, fixed target8192 actual completed environment hands,
stop at first PPO boundary reaching the target and report overshoot. Same basic
optimization as the last representation experiment:cuda,12workers,4096legacy
collection markers,1024minibatch,LR3e-5,PPO2epochs,targetKL.01,sourceKL.01 against
the original Standard10 weights interpreted under v6,advantageclip3,entropy.005,
floor.05,GN,critic_v2,valuecoef1,stackdivisor200,separatepreflophead. All86tensors
trainable. Fixed adaptive3-anchor league,25%self-play,per-group8,single rollout,
fixeddealstream. Learner seed20260916,workerbase2026091600. Archive every update,
save latest every update;600second operational cap, no automatic restart.

Exact first command:
python research/experiments/v6-physical-training-smoke-20260831/run_smoke.py

## Evidence and smoke gate

Before launch, capture full source copies/hashes/dirty patch, test exact command
and explicit-rebinding invariants. Log actual physical accounting during the run.
At completion require clean process exit,complete monotonic physical prefix,
target reached,nonempty finite Adam state,finite changed learned weights,all86
trainable tensors,checkpoint/manifest/metrics agreement and fixed-pool session
audit. Save actual exact command,optimizer/counters,source hashes and frozen final.
Any terminal failure is preserved and analyzed, never silently retried/reset.

After freezing the final by counter alone, run the new v6 mirror CLI on source
and final against each of the3rebound anchors:64mirrored pairs per cell,
seed20260917,768total internal hands. These are untouched by this training run,
but tiny and deliberately diagnostic. Scores/CI are descriptive only; no
positive-score gate, no model selection, no100k or external admission. Require
all6cell evidence complete,hashes stable,source-vs-itself exact pair cancellation.
No Slumbot calls. On clean pipeline completion, finish this record and preregister
a substantive corrected-contract learning curve with separate held-out anchors.
