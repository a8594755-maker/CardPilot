# Conditional next direction, before the fixed matrix

Written while the original control trainer remains live; the weak arm and
evaluation matrix have not run. This memo changes no current configuration,
budget, checkpoint selection or admission rule.

## Preserve the registered branch

If this pilot passes, independently confirm exactly its final frozen endpoints.
Do not switch to another method, choose an archive, pool discovery outcomes or
promote directly to Slumbot. If it fails, do not extend the current experiment.

## A distinct candidate if weakening the anchor fails

Current source review establishes that train_mp3_hybrid_h1.py computes
KL(reference || current), and train_v5.py loads an immutable source reference.
Both arms intentionally retain these semantics. The experiment changes the
coefficient only; it is not a NashPG reproduction and does not test moving
references or the opposite KL direction.

The latest NashPG paper is v3 (3 August2026),superseding the initially inspected
v1. It combines current-policy self-play with KL(current || reference),periodic
reference replacement and policy-gradient updates. Its practical algorithm has
no transferred exact-convergence guarantee; its reported Hold'em environment
starts at100bb,not our200bb Slumbot benchmark. This motivates a separate method
study,not a performance claim here. [NashPG v3,Algorithm4 and AppendixB](https://arxiv.org/html/2510.18183v3)

For implementation study use the latest paper's
[official repository](https://github.com/ntu-agents/nashpg),not assume the older
author repository or preprint settings remain authoritative. No upstream code,
packages or environment have been installed or executed in this experiment.

Local inference: if changing only coefficient fails, the next higher-information
branch could test the regularization **dynamics**, rather than another nearby
coefficient. First create a separately logged mathematical/implementation
contract with asymmetric distributions that distinguish KL directions, legal
mask tests, analytic/finite-difference gradients, exact reference refresh
boundaries, and checkpoint-resume continuity of reference weights and counters.
Keep default legacy behavior unchanged. Small-game fixtures would establish
implementation behavior only,not count as200bb training or establish the goal.

Then a separately preregistered200bb learned-weight study can compare static
versus periodically refreshed references at the same KL direction,with current
self-play sampling and explicitly stated network parameter sharing/scope. The
reference period must be chosen before outcomes; comparisons need matched
physical budgets and untouched frozen multi-anchor evaluation. No Slumbot hand
histories should be used as optimization targets and no hand-specific action
rules should be added. Full-network representation learning remains a separate
alternative: the earlier full-network pilot also changed LR/KL and did not isolate
scope,so its result does not settle that hypothesis.

## Scale remains empirical

The original AlphaHoldem paper reports50,000iterations,6.5billion transition
samples and roughly2.7billion hands,using8GPUs,total minibatch16384 and initial
Adam LR3e-4. Those quantities are not equivalent to our legacy marker counter.
[AlphaHoldem experimental settings,p.4693](https://ojs.aaai.org/index.php/AAAI/article/view/20394/20153)

Neither the current bounded pilot nor another paper's successful run establishes
that blind scaling here will work. Use measured completed-environment accounting,
actual throughput and reproducible learning curves to justify increases. The
unchanged goal is one frozen policy on at least100000fresh Slumbot hands with
positive bb/100 and positive95%CI lower bound.
