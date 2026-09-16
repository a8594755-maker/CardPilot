# Actor-head EMA terminal-policy smoke

Historical external evidence says the legacy Standard10 weights are much closer
to zero under greedy deployment (-11.4275 bb/100 on fresh 20k) than under strict
sampled execution (-48.9778 bb/100).  The prior single imitation-teacher route
was still negative at about -18.5025 bb/100, so this experiment does not revive
imitation.  It instead tests whether sampled PPO creates useful but temporally
jittery actor-head updates whose exponential average is a stronger frozen greedy
policy than the raw terminal update.

Start from the exact legacy Standard10 checkpoint SHA256
91b0c587a5a76e9a8f38217e0b304136ef298118a99b69cc743899fc4b16e428.
Run one all-policy-heads-only PPO trajectory for at least 131,072 physical v6
environment hands with fresh optimizer and counters, seed 20261042, worker seed
2026104200, fixed training deal stream, five frozen learned anchors, adaptive
league, sampled hero, self-play fraction 0.25, learning rate 3e-5, PPO epochs 2,
target KL 0.01, advantage clip 3, source KL 0.01, entropy 0.005/floor 0.05,
critic_v2, and no replay, privileged critic, sequence adapter, imitation loss,
endpoint selection, or benchmark-specific rule.

Maintain an EMA only for policy_head.* and preflop_policy_head.*.  Initialize it
bitwise from the post-migration source actor, use fixed decay 0.9, and update it
exactly once after every completed PPO update.  Serialize the EMA tensors, decay,
and update count in every checkpoint.  True resume must restore them; a missing
EMA state on a resumed EMA run is an error.  The EMA does not affect rollouts,
optimization, opponent selection, or the raw terminal model.

After training, freeze the raw endpoint and materialize a second checkpoint by
replacing exactly the four actor-head tensors with the serialized EMA tensors.
Require exact physical accounting, contiguous metrics, PASS session audit,
nonzero EMA updates, bitwise equality of every non-actor tensor between raw and
EMA, and at least one changed actor-head tensor.  Evaluate source/raw/EMA against
all five untouched anchors with 2,048 mirrored pairs per cell and common seed
20261043 (15 cells, 61,440 hands).  Admit an independent 262,144-hand EMA pilot
only if the per-deck five-anchor-average EMA-minus-raw point estimate is positive,
EMA-minus-source is positive, at least 3/5 per-anchor EMA-minus-raw points are
positive, and every evidence gate passes.  This is an internal gate only;
Slumbot hands = 0 and no endpoint is a Goal-completion candidate.
