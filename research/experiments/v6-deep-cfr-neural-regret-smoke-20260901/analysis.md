# Exact-v6 bounded neural regret optimization smoke

Decision: `REJECT_OR_REVISE_EXACT_V6_NEURAL_REGRET_SMOKE`.

The run completed all eight planned root traversals without approaching the
250,000-node fail-only limit: 29,093 decision nodes, 22,667 terminal rollouts,
and maximum depth 16. Both buffers were populated (1,336 and 2,277 samples), all
four optimization losses were finite and positive, and the physical-v6
checkpoint reloaded byte-for-byte at the tensor level.

The preregistration note mistakenly stated 4,096 evaluation hands. The exact
configuration was always 256 pairs, two hands per pair, and four cells, which is
2,048 hands. All four configured cells completed on the same untouched deck
panel. This is an accounting arithmetic correction, not a configuration or
outcome change.

Thirty-two optimizer steps moved probability mass modestly away from the passive
initialization (mean TV about 0.080--0.083 on candidate decisions), but did not
flip a single greedy argmax in any evaluation cell. Losses remained high at
133.9--190.3 after the updates. Consequently, noisy anchor returns are not
interpreted as policy evidence: call-station sampled was -83.36 bb/100 with CI
[-387.97, 221.25], while every 512-hand cell had a very wide interval.

The highest-information next experiment is an offline matched optimizer-dose
control over one frozen first-iteration target buffer. It should train 32/128/512
step arms from identical passive weights and identical targets, measure held-out
target loss and argmax/TV movement on a frozen state panel, and serialize the
buffer evidence. Only if a dose reliably fits targets and changes decisions
should iterative traversal volume be increased.
