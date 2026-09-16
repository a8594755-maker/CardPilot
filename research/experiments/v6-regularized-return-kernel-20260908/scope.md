# Regularized trajectory-return kernel

Motivation: previous static/moving-reference work changes local policy KL or its
reference; local loss is not the same as propagating future own/opponent reference
costs through return targets. Existing weak-reference, counterfactual action ranking
and independent-critic negative/inconclusive evidence remains relevant. This kernel
does not establish that reward transformation will fix the plateau.

Primary research lead: Perolat et al., Mastering the Game of Stratego with
Model-Free Multiagent Reinforcement Learning, https://arxiv.org/abs/2206.15378 .
R-NaD motivates a reward-transform/dynamics/reference-update decomposition. This
experiment implements only the elementary on-policy zero-sum reward transformation,
NOT full DeepNash, NeuRD, V-trace, reference scheduling or paper reproduction.
Primary full-paper/code retrieval was unavailable during this bounded kernel step;
no claim of exact implementation equivalence is made.

For each chronological action by player p, add -eta*log(pi(a)/ref(a)) to p's
reward and its negative to the other player. Backward undiscounted sums include
all future shaping rewards and terminal poker payoff. All inputs/outputs use bb;
production normalized rewards require an explicit unit conversion. Reference and
rollout models are frozen for a collection batch. These inputs require both
players' actual decision log probabilities, not just hero transitions. Epsilon
behavior mixtures, replay and asynchronous policy staleness need a separately
verified estimator and cannot silently use this on-policy kernel.

Six deterministic tests cover zero coefficient, matching reference, opposite
player sign, chronological propagation, player-label symmetry, expected KL cost
and input guards. Zero poker hands and no changed model weights.

Next: inspect chronological rollout evidence and implement a complete-hand
adapter which rejects missing opponent decisions and unsupported behavior/replay.
Verify on actual retained-policy trajectories, then qualify critic/actor target
integration and exact resume before allocating a matched training pilot. Keep
one major algorithmic control. Do not manufacture missing log probabilities,
discard existing buffers, reset Adam/counters, or label kernel tests a stronger
policy. Current production source remains unchanged.
