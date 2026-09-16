# Trainable parameter scope is not the same as gradient connectivity

Zero-hand post-analysis of the current experiment,2026-09-06T00:04UTC. No new
algorithm branch, live source edit, optimizer step, checkpoint mutation, GPU
probe, Slumbot hand or allocation change. Register with this same experiment
after its controller exits, together with gradient_routes.py and the generated
gradient_route_observation.json. Exact executed command:

    python -B research/experiments/v6-full-step-size-1m-continuation-20260905/post_analysis/gradient_routes.py

## Evidence and limits

The source-bound network at network_hybrid_h1.py:585 passes h.detach() to the
separate preflop policy head. At line841, critic_v2 also detaches h before its
value head. The closed run manifest explicitly records
value_gradient_to_shared_trunk=false; this value contract is intentional and is
not a newly discovered configuration failure. The preflop detach is unconditional
when the separate head exists, including when the preflop teacher coefficient is0.

Eight direct-gradient checks on the actual Seed1 and Seed3 closed full-rate
stage1 weights confirmed the following routes. Both reconstructed models have
all86 parameter tensors marked trainable, with the unchanged architecture.

| Probe objective | Shared representation | Postflop head | Preflop head | Value head |
|---|---|---|---|---|
| Preflop policy-logit contrast |zero|zero|nonzero|zero|
| Postflop policy-logit contrast |nonzero|nonzero|zero|zero|
| Scalar value, either street |zero|zero|zero|nonzero|

These use explicitly synthetic batch-of-two network inputs, not poker states,
solver targets, stored Slumbot decisions or a PPO optimization. Gradient magnitudes
are not comparable poker-quality metrics. The check took4.641s of its own wall
time on one CPU thread. Parameters/buffers were unchanged, no parameter .grad
was populated, and source/checkpoint hashes matched again after the check.

## Consequence for interpreting this experiment

The current study remains valid as full-trainable-scope versus half-actual-LR
continuation under the SAME frozen architecture. It is not a comparison of
end-to-end representation learning from every street/objective. Nonzero body
Adam step counts establish optimizer progression, not direct preflop or critic
gradient flow. Nor does this probe measure the amount of useful body learning
in actual rollouts or prove the cause of any seat imbalance or external loss.

Shared representation changes from postflop learning can still change preflop
predictions indirectly; the preflop head itself is trainable. This is not a claim
that preflop strategy cannot learn. Do not remove detach mid-run or redefine any
past counter. Finish the fixed LR study and inspect its complete curves first.
If those results motivate an architecture hypothesis, direct preflop actor-to-body
connectivity can be evaluated later as a distinct single-change control, keeping
critic_v2 separate. This note neither selects that route nor authorizes an extra
concurrent training family. Existing critic protection has a different purpose
and should not be silently removed as part of a preflop change.
